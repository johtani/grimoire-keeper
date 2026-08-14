#!/bin/bash

set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${TOOLS_DIR}/../.." && pwd)"
COMPOSE_FILE="${TOOLS_DIR}/docker-compose.yml"
MIGRATION_DIR="${PROJECT_ROOT}/data/migration"
CONTAINER_MIGRATION_DIR="/migration"
PYTHON_BIN="/app/.venv/bin/python"
DEFAULT_QUERIES="${MIGRATION_DIR}/search_queries.json"
DEFAULT_BEFORE="${MIGRATION_DIR}/search-before-1.33.1.json"
DEFAULT_AFTER="${MIGRATION_DIR}/search-after-1.38.8.json"

# The tools compose file intentionally shares the production project name.
# Never remove the production services as "orphans" from this wrapper.
export COMPOSE_IGNORE_ORPHANS=true

load_bws_token() {
    if [ -z "${BWS_ACCESS_TOKEN:-}" ]; then
        local bws_env="${HOME}/.config/bws.env"
        if [ -f "${bws_env}" ]; then
            # shellcheck source=/dev/null
            source "${bws_env}"
            export BWS_ACCESS_TOKEN
        fi
    fi
}

require_host_tools() {
    cd "${PROJECT_ROOT}"
    if [ ! -f .env ]; then
        echo "ERROR: ${PROJECT_ROOT}/.env が見つかりません" >&2
        exit 1
    fi
    for command_name in docker bws git; do
        if ! command -v "${command_name}" > /dev/null; then
            echo "ERROR: ${command_name} コマンドが必要です" >&2
            exit 1
        fi
    done
    load_bws_token
    if [ -z "${BWS_ACCESS_TOKEN:-}" ]; then
        echo "ERROR: BWS_ACCESS_TOKEN が必要です" >&2
        exit 1
    fi
    docker compose version > /dev/null
    if [ -n "$(git status --porcelain)" ]; then
        echo "ERROR: 作業ツリーに未コミットの変更があります" >&2
        exit 1
    fi
}

run_tool() {
    export MIGRATION_UID="${MIGRATION_UID:-$(id -u)}"
    export MIGRATION_GID="${MIGRATION_GID:-$(id -g)}"
    bws run -- docker compose --project-directory "${PROJECT_ROOT}" \
        -f "${COMPOSE_FILE}" run --rm migration-tools "$@"
}

require_prepared() {
    if [ ! -f "${DEFAULT_QUERIES}" ]; then
        echo "ERROR: ${DEFAULT_QUERIES} がありません。先に prepare を実行してください" >&2
        exit 1
    fi
}

prepare() {
    require_host_tools
    mkdir -p "${MIGRATION_DIR}"
    if [ ! -f "${DEFAULT_QUERIES}" ]; then
        cp "${PROJECT_ROOT}/tools/search_regression/queries.example.json" \
            "${DEFAULT_QUERIES}"
        echo "代表クエリを編集してください: ${DEFAULT_QUERIES}"
    fi
    bws run -- docker compose --project-directory "${PROJECT_ROOT}" \
        -f "${COMPOSE_FILE}" build migration-tools
    run_tool "${PYTHON_BIN}" -m tools.weaviate_1_38_migration.self_check
    echo "移行ツールコンテナのPython依存を確認しました"
}

capture() {
    local label="$1"
    local output="$2"
    require_host_tools
    require_prepared
    run_tool "${PYTHON_BIN}" -m tools.search_regression.snapshot capture \
        --api-url http://host.docker.internal:8000 \
        --queries "${CONTAINER_MIGRATION_DIR}/search_queries.json" \
        --label "${label}" \
        --output "${CONTAINER_MIGRATION_DIR}/${output}"
}

preflight() {
    require_host_tools
    require_prepared
    if [ ! -f "${DEFAULT_BEFORE}" ]; then
        echo "ERROR: ${DEFAULT_BEFORE} がありません。先に capture-before を実行してください" >&2
        exit 1
    fi
    # SQLite WAL/SHM files may be owned by the root API container.
    MIGRATION_UID=0 MIGRATION_GID=0 run_tool \
        "${PYTHON_BIN}" -m tools.weaviate_1_38_migration.preflight \
        --containerized \
        --data-root /opt/grimoire-keeper-data \
        --database /data/grimoire.db \
        --json-path /app/apps/api/data/json \
        --queries "${CONTAINER_MIGRATION_DIR}/search_queries.json" \
        --baseline "${CONTAINER_MIGRATION_DIR}/search-before-1.33.1.json" \
        --api-health-url http://host.docker.internal:8000/api/v1/health \
        --weaviate-ready-url http://host.docker.internal:8089/v1/.well-known/ready \
        --output "${CONTAINER_MIGRATION_DIR}/preflight.json"
}

dry_run() {
    require_host_tools
    # The production API runs as root and may own SQLite's WAL/SHM files.
    # SQLite mode=ro prevents SQL writes while root permits WAL locking.
    MIGRATION_UID=0 MIGRATION_GID=0 run_tool \
        "${PYTHON_BIN}" /app/scripts/reindex_weaviate.py --dry-run \
        --repair-pending-output /migration/repair-pending.json
}

check_counts() {
    require_host_tools
    MIGRATION_UID=0 MIGRATION_GID=0 run_tool \
        "${PYTHON_BIN}" -m tools.weaviate_1_38_migration.check_counts \
        --repair-pending-report /migration/repair-pending.json
}

compare() {
    require_host_tools
    require_prepared
    if [ ! -f "${DEFAULT_BEFORE}" ] || [ ! -f "${DEFAULT_AFTER}" ]; then
        echo "ERROR: 移行前後の検索スナップショットが必要です" >&2
        exit 1
    fi
    local threshold="${SEARCH_OVERLAP_THRESHOLD:-0.8}"
    run_tool "${PYTHON_BIN}" -m tools.search_regression.snapshot compare \
        --before "${CONTAINER_MIGRATION_DIR}/search-before-1.33.1.json" \
        --after "${CONTAINER_MIGRATION_DIR}/search-after-1.38.8.json" \
        --output "${CONTAINER_MIGRATION_DIR}/search-comparison.json" \
        --fail-below-overlap "${threshold}"
}

rollback_check() {
    local rollback_info="$1"
    require_host_tools
    if [ ! -f "${rollback_info}" ]; then
        echo "ERROR: ロールバック情報が見つかりません: ${rollback_info}" >&2
        exit 1
    fi
    local api_commit
    api_commit="$(sed -n 's/^api_commit=//p' "${rollback_info}")"
    if [ -z "${api_commit}" ] || [ "${api_commit}" = "unknown" ]; then
        echo "ERROR: ロールバック対象コミットが記録されていません" >&2
        exit 1
    fi
    git -C "${PROJECT_ROOT}" cat-file -e "${api_commit}^{commit}"
    run_tool "${PYTHON_BIN}" -m tools.weaviate_1_38_migration.rollback_check \
        --containerized \
        --verified-api-commit "${api_commit}" \
        --rollback-info "${rollback_info}" \
        --output "${CONTAINER_MIGRATION_DIR}/rollback-readiness.json"
}

usage() {
    cat <<'EOF'
Usage: bash tools/weaviate_1_38_migration/run.sh <command> [arguments]

Commands:
  prepare                 Build the tools image and create the query file
  capture-before          Capture search results from the current API
  preflight               Run read-only checks before stopping services
  dry-run                 Show reindex targets without writing to Weaviate
  check-counts            Compare SQLite and Weaviate collection counts
  capture-after           Capture search results from the migrated API
  compare                 Compare before/after search snapshots
  rollback-check <path>   Verify rollback assets and checksum
EOF
}

case "${1:-}" in
    prepare)
        prepare
        ;;
    capture-before)
        capture before-1.33.1 search-before-1.33.1.json
        ;;
    preflight)
        preflight
        ;;
    dry-run)
        dry_run
        ;;
    check-counts)
        check_counts
        ;;
    capture-after)
        capture after-1.38.8 search-after-1.38.8.json
        ;;
    compare)
        compare
        ;;
    rollback-check)
        if [ "$#" -ne 2 ]; then
            usage >&2
            exit 2
        fi
        rollback_check "$2"
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
