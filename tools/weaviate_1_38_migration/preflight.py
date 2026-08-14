#!/usr/bin/env python3
"""Run read-only checks before the Weaviate 1.38 migration."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sqlite3
import subprocess
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from tools.search_regression.snapshot import load_queries

GIB = 1024**3


@dataclass(frozen=True)
class Check:
    """One preflight check result."""

    name: str
    status: str
    detail: str


def _nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return number


def _directory_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def _is_nonempty_directory(path: Path) -> bool:
    return path.is_dir() and next(path.iterdir(), None) is not None


def _url_is_ready(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310
            return 200 <= response.status < 300, f"HTTP {response.status}"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except URLError as exc:
        return False, f"connection failed: {exc.reason}"


def _has_bws_token() -> bool:
    if os.environ.get("BWS_ACCESS_TOKEN"):
        return True
    env_file = Path.home() / ".config" / "bws.env"
    try:
        return any(
            line.strip().startswith("BWS_ACCESS_TOKEN=")
            and bool(line.partition("=")[2].strip())
            for line in env_file.read_text(encoding="utf-8").splitlines()
        )
    except OSError:
        return False


def _load_snapshot(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read baseline {path}: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("baseline has an unsupported schema_version")
    return document


def _baseline_matches_queries(
    baseline: dict[str, Any], queries: list[dict[str, Any]]
) -> bool:
    captured = baseline.get("queries")
    if not isinstance(captured, list):
        return False
    requests = {
        entry.get("name"): entry.get("request")
        for entry in captured
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    return requests == {query["name"]: query for query in queries}


def _baseline_has_results(baseline: dict[str, Any]) -> bool:
    captured = baseline.get("queries")
    if not isinstance(captured, list) or not captured:
        return False
    for entry in captured:
        if not isinstance(entry, dict):
            return False
        response = entry.get("response")
        if not isinstance(response, dict):
            return False
        results = response.get("results")
        if not isinstance(results, list) or not results:
            return False
    return True


def _check_sqlite_and_json(database_path: Path, json_path: Path) -> list[Check]:
    """Check the source SQLite schema and completed-page JSON coverage."""
    checks: list[Check] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append(Check(name, "PASS" if passed else "FAIL", detail))

    if not database_path.is_file():
        add("SQLite database file", False, str(database_path))
        return checks
    add("SQLite database file", True, str(database_path))

    required_columns = {
        "id",
        "url",
        "title",
        "memo",
        "summary",
        "keywords",
        "weaviate_id",
        "last_success_step",
        "created_at",
        "updated_at",
    }
    try:
        database_uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(database_uri, uri=True)) as connection:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(pages)").fetchall()
            }
            missing_columns = sorted(required_columns - columns)
            add(
                "SQLite pages schema",
                not missing_columns,
                (
                    "required columns are present"
                    if not missing_columns
                    else f"missing columns: {', '.join(missing_columns)}"
                ),
            )
            if missing_columns:
                return checks

            if "status" in columns:
                schema = "current (status column)"
                completed_condition = "status = 'succeeded'"
            else:
                schema = "legacy (without status column)"
                completed_condition = (
                    "last_success_step = 'completed' "
                    "OR (summary IS NOT NULL AND weaviate_id IS NOT NULL)"
                )
            add("SQLite schema compatibility", True, schema)
            completed_pages = {
                int(row[0]): str(row[1])
                for row in connection.execute(
                    f"SELECT id, title FROM pages WHERE {completed_condition}"
                ).fetchall()
            }
            add(
                "completed SQLite pages",
                True,
                f"{len(completed_pages)} pages can be selected",
            )
    except (OSError, sqlite3.Error) as exc:
        add("SQLite readable", False, str(exc))
        return checks

    missing_json = sorted(
        page_id
        for page_id in completed_pages
        if not (json_path / f"{page_id}.json").is_file()
    )
    preview = ", ".join(str(page_id) for page_id in missing_json[:10])
    detail = (
        f"all {len(completed_pages)} completed pages have JSON"
        if not missing_json
        else f"missing {len(missing_json)} JSON files; page IDs: {preview}"
    )
    add("completed page JSON coverage", not missing_json, detail)
    if missing_json:
        checks[-1] = Check(checks[-1].name, "WARN", checks[-1].detail)

    invalid_json: list[int] = []
    for page_id in completed_pages:
        source_path = json_path / f"{page_id}.json"
        if not source_path.is_file():
            continue
        try:
            source = json.loads(source_path.read_text(encoding="utf-8"))
            data = source.get("data") if isinstance(source, dict) else None
            content = data.get("content") if isinstance(data, dict) else None
            jina_title = data.get("title") if isinstance(data, dict) else None
            http_status = data.get("httpStatus") if isinstance(data, dict) else None
            source_statuses = (
                source.get("code") if isinstance(source, dict) else None,
                http_status,
            )
            source_failed = any(
                isinstance(status_value, int)
                and not isinstance(status_value, bool)
                and status_value >= 400
                for status_value in source_statuses
            )
            if (
                source_failed
                or not isinstance(content, str)
                or not content.strip()
                or not isinstance(jina_title, str)
                or not jina_title.strip()
            ):
                invalid_json.append(page_id)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            invalid_json.append(page_id)
    preview = ", ".join(str(page_id) for page_id in invalid_json[:10])
    detail = (
        "all available completed-page JSON files contain usable title and content"
        if not invalid_json
        else f"invalid {len(invalid_json)} JSON files; page IDs: {preview}"
    )
    add("completed page JSON validity", not invalid_json, detail)
    if invalid_json:
        checks[-1] = Check(checks[-1].name, "WARN", checks[-1].detail)
    return checks


def _checks_pass(checks: list[Check]) -> bool:
    return all(check.status != "FAIL" for check in checks)


def run_preflight(
    repo_root: Path,
    data_root: Path,
    queries_path: Path,
    baseline_path: Path,
    minimum_free_gb: float,
    api_health_url: str,
    weaviate_ready_url: str,
    url_checker: Callable[[str], tuple[bool, str]] = _url_is_ready,
    check_host_environment: bool = True,
    database_path: Path | None = None,
    json_path: Path | None = None,
) -> list[Check]:
    """Run checks without changing services or migration data."""
    checks: list[Check] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append(Check(name, "PASS" if passed else "FAIL", detail))

    if check_host_environment:
        add("repository .env", (repo_root / ".env").is_file(), str(repo_root / ".env"))
        add("bws command", shutil.which("bws") is not None, "bws must be on PATH")
        add("BWS access token", _has_bws_token(), "environment or ~/.config/bws.env")
        add(
            "docker command",
            shutil.which("docker") is not None,
            "docker must be on PATH",
        )

        try:
            compose = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                check=False,
            )
            add("docker compose", compose.returncode == 0, "docker compose version")
        except OSError as exc:
            add("docker compose", False, str(exc))

        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            add(
                "clean worktree",
                status.returncode == 0 and not status.stdout.strip(),
                "git status",
            )
        except OSError as exc:
            add("clean worktree", False, str(exc))

    old_data = data_root / "weaviate"
    new_data = data_root / "weaviate-1.38.8"
    marker = new_data / ".grimoire-migration-ready"
    database = data_root / "database"
    json_data = data_root / "json"
    add("old Weaviate data", _is_nonempty_directory(old_data), str(old_data))
    add("SQLite data", _is_nonempty_directory(database), str(database))
    add("Jina JSON data", _is_nonempty_directory(json_data), str(json_data))
    new_is_safe = not new_data.exists() or (
        new_data.is_dir() and not _is_nonempty_directory(new_data)
    )
    add("empty new Weaviate data", new_is_safe, str(new_data))
    add("migration marker absent", not marker.exists(), str(marker))
    checks.extend(
        _check_sqlite_and_json(
            database_path or database / "grimoire.db",
            json_path or json_data,
        )
    )

    try:
        source_bytes = sum(
            _directory_size(path)
            for path in (old_data, database, json_data)
            if path.is_dir()
        )
        free_bytes = shutil.disk_usage(data_root).free
        required_bytes = max(int(minimum_free_gb * GIB), int(source_bytes * 1.25))
        add(
            "free disk space",
            free_bytes >= required_bytes,
            f"free={free_bytes / GIB:.2f}GiB required={required_bytes / GIB:.2f}GiB",
        )
    except OSError as exc:
        add("free disk space", False, str(exc))

    try:
        queries = load_queries(queries_path)
        add("representative queries", True, f"{len(queries)} queries in {queries_path}")
        baseline = _load_snapshot(baseline_path)
        add(
            "search baseline",
            _baseline_matches_queries(baseline, queries),
            f"query definitions match {baseline_path}",
        )
        add(
            "search baseline results",
            _baseline_has_results(baseline),
            "every representative query returned at least one result",
        )
    except ValueError as exc:
        add("representative queries and baseline", False, str(exc))

    api_ready, api_detail = url_checker(api_health_url)
    add("current API readiness", api_ready, api_detail)
    weaviate_ready, weaviate_detail = url_checker(weaviate_ready_url)
    add("current Weaviate readiness", weaviate_ready, weaviate_detail)
    return checks


def _write_report(path: Path, checks: list[Check]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "passed": _checks_pass(checks),
                "checks": [asdict(check) for check in checks],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only migration preflight checks."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--data-root", type=Path, default=Path("/opt/grimoire-keeper-data")
    )
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--json-path", type=Path)
    parser.add_argument("--minimum-free-gb", type=_nonnegative_float, default=5.0)
    parser.add_argument(
        "--api-health-url", default="http://localhost:8000/api/v1/health"
    )
    parser.add_argument(
        "--weaviate-ready-url", default="http://localhost:8089/v1/.well-known/ready"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--containerized",
        action="store_true",
        help="skip host checks already performed by the Docker wrapper",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    checks = run_preflight(
        args.repo_root,
        args.data_root,
        args.queries,
        args.baseline,
        args.minimum_free_gb,
        args.api_health_url,
        args.weaviate_ready_url,
        check_host_environment=not args.containerized,
        database_path=args.database,
        json_path=args.json_path,
    )
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
    if args.output:
        _write_report(args.output, checks)
        print(f"Report: {args.output}")
    return 0 if _checks_pass(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
