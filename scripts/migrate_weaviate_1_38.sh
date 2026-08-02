#!/bin/bash

set -e

COMPOSE_FILE="docker-compose.prod.yml"
DATA_ROOT="/opt/grimoire-keeper-data"
OLD_WEAVIATE_DATA="${DATA_ROOT}/weaviate"
NEW_WEAVIATE_DATA="${DATA_ROOT}/weaviate-1.38.8"
BACKUP_ROOT="${DATA_ROOT}/backups"
MIGRATION_MARKER="${NEW_WEAVIATE_DATA}/.grimoire-migration-ready"
BACKUP_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_ROOT}/pre-weaviate-1.38.8-${BACKUP_TIMESTAMP}.tar.gz"
ROLLBACK_INFO="${BACKUP_ROOT}/pre-weaviate-1.38.8-${BACKUP_TIMESTAMP}.txt"

export WEAVIATE_IMAGE="cr.weaviate.io/semitechnologies/weaviate:1.38.8"
export WEAVIATE_DATA_PATH="${NEW_WEAVIATE_DATA}"

if [ ! -f .env ]; then
    echo "ERROR: .envファイルが見つかりません"
    exit 1
fi

if [ -z "${BWS_ACCESS_TOKEN}" ]; then
    BWS_ENV="${HOME}/.config/bws.env"
    if [ -f "${BWS_ENV}" ]; then
        # shellcheck source=/dev/null
        source "${BWS_ENV}"
        export BWS_ACCESS_TOKEN
    fi
fi

if [ -z "${BWS_ACCESS_TOKEN}" ] || ! command -v bws &> /dev/null; then
    echo "ERROR: bws CLI と BWS_ACCESS_TOKEN が必要です"
    exit 1
fi

if [ ! -d "${OLD_WEAVIATE_DATA}" ]; then
    echo "ERROR: 旧Weaviateデータが見つかりません: ${OLD_WEAVIATE_DATA}"
    exit 1
fi

if [ -f "${MIGRATION_MARKER}" ]; then
    echo "ERROR: 検証済みマーカーが既に存在します: ${MIGRATION_MARKER}"
    echo "再実行する場合は新環境の状態を確認してから手動で削除してください"
    exit 1
fi

sudo mkdir -p "${NEW_WEAVIATE_DATA}" "${BACKUP_ROOT}"
sudo chown -R "${USER}:${USER}" "${NEW_WEAVIATE_DATA}" "${BACKUP_ROOT}"

OLD_API_COMMIT="$(docker compose -f "${COMPOSE_FILE}" exec -T api \
    printenv GIT_COMMIT 2>/dev/null || echo unknown)"
{
    echo "api_commit=${OLD_API_COMMIT}"
    echo "weaviate_image=cr.weaviate.io/semitechnologies/weaviate:1.33.1"
    echo "weaviate_data=${OLD_WEAVIATE_DATA}"
    echo "sqlite_json_backup=${BACKUP_FILE}"
} > "${ROLLBACK_INFO}"

echo "旧サービスを停止します。旧Weaviateデータは変更しません。"
docker compose -f "${COMPOSE_FILE}" down

echo "SQLiteとJina JSONをバックアップします: ${BACKUP_FILE}"
tar -C "${DATA_ROOT}" -czf "${BACKUP_FILE}" database json

echo "Weaviate 1.38.8 と再インデックス用APIイメージを準備します。"
bws run -- docker compose -f "${COMPOSE_FILE}" pull weaviate
bws run -- docker compose -f "${COMPOSE_FILE}" build api
bws run -- docker compose -f "${COMPOSE_FILE}" up -d weaviate

echo "Weaviate readinessを待機します。"
for attempt in $(seq 1 60); do
    if curl -fsS http://localhost:8089/v1/.well-known/ready > /dev/null; then
        break
    fi
    if [ "${attempt}" -eq 60 ]; then
        echo "ERROR: Weaviate 1.38.8 がreadyになりませんでした"
        exit 1
    fi
    sleep 2
done

echo "再インデックス対象を確認します。"
bws run -- docker compose -f "${COMPOSE_FILE}" run --rm --no-deps api \
    uv run python ../../scripts/reindex_weaviate.py --dry-run

echo "空のWeaviate 1.38.8へ再インデックスします。"
bws run -- docker compose -f "${COMPOSE_FILE}" run --rm --no-deps api \
    uv run python ../../scripts/reindex_weaviate.py

echo "再構築したコレクション件数を検証します。"
bws run -- docker compose -f "${COMPOSE_FILE}" run --rm --no-deps api \
    uv run python ../../scripts/check_weaviate_migration.py

touch "${MIGRATION_MARKER}"
echo "検証済みマーカーを作成しました: ${MIGRATION_MARKER}"
echo "バックアップ: ${BACKUP_FILE}"
echo "ロールバック情報: ${ROLLBACK_INFO}"
echo "代表検索を確認後、bash scripts/deploy.sh でAPIを切り替えてください。"
