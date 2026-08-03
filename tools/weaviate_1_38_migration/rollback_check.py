#!/usr/bin/env python3
"""Verify that recorded Weaviate migration rollback assets are usable."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from tools.weaviate_1_38_migration.preflight import _has_bws_token


@dataclass(frozen=True)
class Check:
    """One rollback readiness result."""

    name: str
    status: str
    detail: str


def load_rollback_info(path: Path) -> dict[str, str]:
    """Load the key-value rollback record created by the migration script."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"could not read rollback info {path}: {exc}") from exc
    values = {
        key.strip(): value.strip()
        for line in lines
        if "=" in line
        for key, _, value in [line.partition("=")]
        if key.strip()
    }
    required = {
        "api_commit",
        "weaviate_image",
        "weaviate_data",
        "sqlite_json_backup",
        "sqlite_json_backup_sha256",
    }
    missing = sorted(required - values.keys())
    if missing:
        raise ValueError(f"rollback info is missing keys: {', '.join(missing)}")
    return values


def _is_nonempty_directory(path: Path) -> bool:
    return path.is_dir() and next(path.iterdir(), None) is not None


def _check_backup(path: Path) -> tuple[bool, str]:
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            names = archive.getnames()
    except (OSError, tarfile.TarError) as exc:
        return False, f"unreadable archive: {exc}"
    has_database = any(
        name == "database" or name.startswith("database/") for name in names
    )
    has_json = any(name == "json" or name.startswith("json/") for name in names)
    return has_database and has_json, "contains database and json entries"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_rollback_check(info_path: Path, repo_root: Path) -> list[Check]:
    """Verify rollback inputs without stopping services or restoring data."""
    checks: list[Check] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append(Check(name, "PASS" if passed else "FAIL", detail))

    try:
        info = load_rollback_info(info_path)
        add("rollback info", True, str(info_path))
    except ValueError as exc:
        add("rollback info", False, str(exc))
        return checks

    commit = info["api_commit"]
    if commit == "unknown" or not commit:
        add("old API commit", False, "commit was not recorded")
    else:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        add("old API commit", result.returncode == 0, commit)

    image = info["weaviate_image"]
    add("old Weaviate image", bool(image), image or "image was not recorded")

    old_data = Path(info["weaviate_data"])
    add("old Weaviate data", _is_nonempty_directory(old_data), str(old_data))

    backup = Path(info["sqlite_json_backup"])
    backup_ok, backup_detail = _check_backup(backup)
    add("SQLite and JSON backup", backup_ok, f"{backup}: {backup_detail}")
    try:
        actual_checksum = _sha256(backup)
        expected_checksum = info["sqlite_json_backup_sha256"]
        add(
            "backup checksum",
            actual_checksum == expected_checksum,
            f"sha256={actual_checksum}",
        )
    except OSError as exc:
        add("backup checksum", False, str(exc))

    add("docker command", shutil.which("docker") is not None, "docker must be on PATH")
    try:
        compose = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            check=False,
        )
        add("docker compose", compose.returncode == 0, "docker compose version")
    except OSError as exc:
        add("docker compose", False, str(exc))
    add("bws command", shutil.which("bws") is not None, "bws must be on PATH")
    add("BWS access token", _has_bws_token(), "environment or ~/.config/bws.env")
    add("repository .env", (repo_root / ".env").is_file(), str(repo_root / ".env"))
    return checks


def _write_report(path: Path, checks: list[Check]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "ready": all(check.status == "PASS" for check in checks),
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
        description="Check rollback assets without restoring them."
    )
    parser.add_argument("--rollback-info", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        checks = run_rollback_check(args.rollback_info, args.repo_root)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
    if args.output:
        _write_report(args.output, checks)
        print(f"Report: {args.output}")
    return 0 if checks and all(check.status == "PASS" for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
