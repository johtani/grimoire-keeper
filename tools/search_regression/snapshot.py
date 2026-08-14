#!/usr/bin/env python3
"""Capture and compare representative API search results."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SNAPSHOT_SCHEMA_VERSION = 1
Query = dict[str, Any]
JsonObject = dict[str, Any]
RequestJson = Callable[[str, Any, float], JsonObject]


def _bounded_ratio(value: str) -> float:
    ratio = float(value)
    if not 0 <= ratio <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return ratio


def load_queries(path: Path) -> list[Query]:
    """Load and validate representative search queries."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read query file {path}: {exc}") from exc

    if not isinstance(document, dict) or not isinstance(document.get("queries"), list):
        raise ValueError("query file must contain a 'queries' array")

    queries: list[Query] = []
    names: set[str] = set()
    for index, raw_query in enumerate(document["queries"], start=1):
        if not isinstance(raw_query, dict):
            raise ValueError(f"query #{index} must be an object")

        name = raw_query.get("name")
        query_type = raw_query.get("type")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"query #{index} must have a non-empty name")
        if name in names:
            raise ValueError(f"duplicate query name: {name}")
        if query_type not in {"vector", "keywords"}:
            raise ValueError(f"query '{name}' has unsupported type: {query_type}")

        limit = raw_query.get("limit", 5)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError(f"query '{name}' limit must be a positive integer")

        query = dict(raw_query)
        query["name"] = name.strip()
        query["limit"] = limit
        if query_type == "vector":
            text = query.get("query")
            vector_name = query.get("vector_name", "content_vector")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"vector query '{name}' must have non-empty query text"
                )
            if vector_name not in {"title_vector", "memo_vector", "content_vector"}:
                raise ValueError(
                    f"vector query '{name}' has unsupported vector_name: {vector_name}"
                )
            query["query"] = text.strip()
            query["vector_name"] = vector_name
        else:
            keywords = query.get("keywords")
            if (
                not isinstance(keywords, list)
                or not keywords
                or not all(
                    isinstance(keyword, str) and keyword.strip() for keyword in keywords
                )
            ):
                raise ValueError(
                    f"keyword query '{name}' must have a non-empty keywords array"
                )
            query["keywords"] = [keyword.strip() for keyword in keywords]

        names.add(query["name"])
        queries.append(query)

    if not queries:
        raise ValueError("query file must contain at least one query")
    return queries


def request_json(url: str, payload: Any, timeout: float) -> JsonObject:
    """POST JSON to the API and return a decoded object."""
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            document = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"API returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"could not connect to {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API returned invalid JSON for {url}") from exc

    if not isinstance(document, dict):
        raise RuntimeError(f"API returned a non-object JSON response for {url}")
    return document


def capture_snapshot(
    queries: list[Query],
    api_url: str,
    label: str,
    timeout: float,
    requester: RequestJson = request_json,
) -> JsonObject:
    """Execute all representative queries and return a migration snapshot."""
    base_url = api_url.rstrip("/")
    captured_queries: list[JsonObject] = []
    for query in queries:
        query_type = query["type"]
        if query_type == "vector":
            endpoint = f"{base_url}/api/v1/search"
            payload = {
                key: value
                for key, value in query.items()
                if key not in {"name", "type"}
            }
        else:
            endpoint = f"{base_url}/api/v1/search/keywords?limit={query['limit']}"
            payload = query["keywords"]

        response = requester(endpoint, payload, timeout)
        results = response.get("results")
        if not isinstance(results, list):
            raise RuntimeError(f"query '{query['name']}' response has no results array")
        captured_queries.append(
            {
                "name": query["name"],
                "type": query_type,
                "request": query,
                "response": response,
            }
        )

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "label": label,
        "captured_at": datetime.now(UTC).isoformat(),
        "api_url": base_url,
        "queries": captured_queries,
    }


def _result_key(result: Any) -> str:
    if not isinstance(result, dict):
        raise ValueError("search result must be an object")
    page_id = result.get("page_id")
    chunk_id = result.get("chunk_id", 0)
    if page_id is not None:
        return f"page:{page_id}:chunk:{chunk_id}"
    url = result.get("url")
    if isinstance(url, str) and url:
        return f"url:{url}:chunk:{chunk_id}"
    raise ValueError("search result must contain page_id or url")


def _page_result_key(result: Any) -> str:
    """Return a page-level key for results that are not chunk-oriented."""
    if not isinstance(result, dict):
        raise ValueError("search result must be an object")
    page_id = result.get("page_id")
    if page_id is not None:
        return f"page:{page_id}"
    url = result.get("url")
    if isinstance(url, str) and url:
        return f"url:{url}"
    raise ValueError("search result must contain page_id or url")


def _comparison_keys(results: list[Any], query_type: Any) -> list[str]:
    """Build ordered comparison keys, deduplicating page-level keyword results."""
    if query_type != "keywords":
        return [_result_key(result) for result in results]

    # The legacy index returned one keyword hit per chunk, while the new index
    # returns one representative object per page. Compare their logical pages.
    return list(dict.fromkeys(_page_result_key(result) for result in results))


def _snapshot_queries(snapshot: JsonObject, label: str) -> dict[str, JsonObject]:
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"{label} snapshot has unsupported schema_version")
    raw_queries = snapshot.get("queries")
    if not isinstance(raw_queries, list):
        raise ValueError(f"{label} snapshot has no queries array")
    indexed: dict[str, JsonObject] = {}
    for query in raw_queries:
        if not isinstance(query, dict) or not isinstance(query.get("name"), str):
            raise ValueError(f"{label} snapshot contains an invalid query")
        if query["name"] in indexed:
            raise ValueError(f"{label} snapshot has duplicate query: {query['name']}")
        indexed[query["name"]] = query
    return indexed


def compare_snapshots(before: JsonObject, after: JsonObject) -> JsonObject:
    """Compare search result membership and rank between two snapshots."""
    before_queries = _snapshot_queries(before, "before")
    after_queries = _snapshot_queries(after, "after")
    if before_queries.keys() != after_queries.keys():
        missing = sorted(before_queries.keys() - after_queries.keys())
        added = sorted(after_queries.keys() - before_queries.keys())
        raise ValueError(f"query sets differ: missing={missing}, added={added}")

    comparisons: list[JsonObject] = []
    for name, before_query in before_queries.items():
        after_query = after_queries[name]
        if before_query.get("request") != after_query.get("request"):
            raise ValueError(f"query '{name}' request differs between snapshots")
        before_response = before_query.get("response")
        after_response = after_query.get("response")
        if not isinstance(before_response, dict) or not isinstance(
            after_response, dict
        ):
            raise ValueError(f"query '{name}' has an invalid response")
        before_results = before_response.get("results", [])
        after_results = after_response.get("results", [])
        if not isinstance(before_results, list) or not isinstance(after_results, list):
            raise ValueError(f"query '{name}' has invalid results")

        request = before_query.get("request")
        query_type = request.get("type") if isinstance(request, dict) else None
        before_keys = _comparison_keys(before_results, query_type)
        after_keys = _comparison_keys(after_results, query_type)
        before_set = set(before_keys)
        after_set = set(after_keys)
        shared = before_set & after_set
        overlap_ratio = len(shared) / len(before_set) if before_set else 1.0
        rank_changes = [
            {
                "result": key,
                "before_rank": before_keys.index(key) + 1,
                "after_rank": after_keys.index(key) + 1,
            }
            for key in before_keys
            if key in shared and before_keys.index(key) != after_keys.index(key)
        ]
        comparisons.append(
            {
                "name": name,
                "comparison_unit": "page" if query_type == "keywords" else "chunk",
                "before_total": before_response.get("total", len(before_results)),
                "after_total": after_response.get("total", len(after_results)),
                "before_results": before_keys,
                "after_results": after_keys,
                "missing_results": [key for key in before_keys if key not in after_set],
                "added_results": [key for key in after_keys if key not in before_set],
                "rank_changes": rank_changes,
                "overlap_ratio": round(overlap_ratio, 4),
                "top_result_unchanged": bool(before_keys)
                and bool(after_keys)
                and before_keys[0] == after_keys[0],
            }
        )

    ratios = [comparison["overlap_ratio"] for comparison in comparisons]
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "compared_at": datetime.now(UTC).isoformat(),
        "before_label": before.get("label"),
        "after_label": after.get("label"),
        "summary": {
            "query_count": len(comparisons),
            "minimum_overlap_ratio": min(ratios, default=1.0),
            "unchanged_top_result_count": sum(
                bool(comparison["top_result_unchanged"]) for comparison in comparisons
            ),
        },
        "queries": comparisons,
    }


def _read_json_object(path: Path) -> JsonObject:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read JSON file {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"JSON file {path} must contain an object")
    return document


def _write_json(path: Path, document: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and compare representative API search results."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture", help="capture search results")
    capture.add_argument("--queries", required=True, type=Path)
    capture.add_argument("--output", required=True, type=Path)
    capture.add_argument("--api-url", default="http://localhost:8000")
    capture.add_argument("--label", required=True)
    capture.add_argument("--timeout", type=float, default=30.0)

    compare = subparsers.add_parser("compare", help="compare two snapshots")
    compare.add_argument("--before", required=True, type=Path)
    compare.add_argument("--after", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)
    compare.add_argument("--fail-below-overlap", type=_bounded_ratio)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "capture":
            if args.timeout <= 0:
                raise ValueError("timeout must be greater than zero")
            snapshot = capture_snapshot(
                load_queries(args.queries), args.api_url, args.label, args.timeout
            )
            _write_json(args.output, snapshot)
            print(f"Captured {len(snapshot['queries'])} queries to {args.output}")
            return 0

        comparison = compare_snapshots(
            _read_json_object(args.before), _read_json_object(args.after)
        )
        _write_json(args.output, comparison)
        summary = comparison["summary"]
        print(
            f"Compared {summary['query_count']} queries: "
            f"minimum_overlap_ratio={summary['minimum_overlap_ratio']}, "
            f"unchanged_top_results={summary['unchanged_top_result_count']}"
        )
        threshold = args.fail_below_overlap
        if threshold is not None and summary["minimum_overlap_ratio"] < threshold:
            print(f"ERROR: minimum overlap ratio is below {threshold}", file=sys.stderr)
            return 1
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
