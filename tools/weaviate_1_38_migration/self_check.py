"""Verify imports required by the Dockerized migration tools."""

import weaviate

from tools.search_regression import snapshot


def main() -> int:
    """Report that the migration tool dependencies are importable."""
    print(
        "Migration tool imports OK: "
        f"weaviate={weaviate.__version__}, "
        f"snapshot_schema={snapshot.SNAPSHOT_SCHEMA_VERSION}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
