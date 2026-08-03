#!/bin/bash

set -e

DATA_ROOT="/opt/grimoire-keeper-data"
OLD_WEAVIATE_DATA="${DATA_ROOT}/weaviate"
NEW_WEAVIATE_DATA="${DATA_ROOT}/weaviate-1.38.8"
MIGRATION_MARKER="${NEW_WEAVIATE_DATA}/.grimoire-migration-ready"

export WEAVIATE_IMAGE="${WEAVIATE_IMAGE:-cr.weaviate.io/semitechnologies/weaviate:1.38.8}"
export WEAVIATE_DATA_PATH="${WEAVIATE_DATA_PATH:-${NEW_WEAVIATE_DATA}}"

echo "Grimoire Keeper デプロイ開始"

# .envファイル確認（非秘密の設定値用）
if [ ! -f .env ]; then
    echo "ERROR: .envファイルが見つかりません"
    echo "cp .env.example .env を実行して設定値を記載してください"
    exit 1
fi

# BWS_ACCESS_TOKEN を ~/.config/bws.env から読み込む
if [ -z "${BWS_ACCESS_TOKEN}" ]; then
  BWS_ENV="${HOME}/.config/bws.env"
  if [ -f "$BWS_ENV" ]; then
    # shellcheck source=/dev/null
    source "$BWS_ENV"
    export BWS_ACCESS_TOKEN
  fi
fi

if [ -z "${BWS_ACCESS_TOKEN}" ]; then
    echo "ERROR: BWS_ACCESS_TOKEN is not set. ~/.config/bws.env に設定してください。"
    exit 1
fi

if ! command -v bws &> /dev/null; then
    echo "ERROR: bws CLI is not installed." >&2
    exit 1
fi

# データディレクトリ作成
echo "データディレクトリ作成中..."
sudo mkdir -p "${DATA_ROOT}/database" "${DATA_ROOT}/json" \
    "${NEW_WEAVIATE_DATA}" "${DATA_ROOT}/backups"
sudo chown -R "${USER}:${USER}" "${DATA_ROOT}/database" "${DATA_ROOT}/json" \
    "${NEW_WEAVIATE_DATA}" "${DATA_ROOT}/backups"

# 旧データがある環境では、検証済みの新環境なしに空のWeaviateへ切り替えない。
if [ "${WEAVIATE_DATA_PATH}" = "${NEW_WEAVIATE_DATA}" ] && \
   [ -d "${OLD_WEAVIATE_DATA}" ] && \
   [ -n "$(find "${OLD_WEAVIATE_DATA}" -mindepth 1 -print -quit)" ] && \
   [ ! -f "${MIGRATION_MARKER}" ]; then
    echo "ERROR: Weaviate 1.38.8 の再インデックスが未検証です"
    echo "先に bash tools/weaviate_1_38_migration/migrate.sh を実行してください"
    exit 1
fi

# 既存コンテナ停止・削除
echo "既存サービス停止中..."
docker compose -f docker-compose.prod.yml down

# ビルド情報を環境変数にセット
export GIT_COMMIT=$(git rev-parse --short HEAD)
export BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "ビルド情報: commit=${GIT_COMMIT}, date=${BUILD_DATE}"

# イメージビルド
echo "イメージビルド中..."
bws run -- docker compose -f docker-compose.prod.yml build --no-cache

# サービス起動
echo "サービス起動中..."
bws run -- docker compose -f docker-compose.prod.yml up -d

# ヘルスチェック
echo "サービス起動確認中..."
sleep 10

# Weaviate確認
if curl -f http://localhost:8089/v1/.well-known/ready >/dev/null 2>&1; then
    echo "OK: Weaviate起動完了"
else
    echo "ERROR: Weaviate起動失敗"
    exit 1
fi

# データベース・スキーマ初期化
echo "データベース・スキーマ初期化中..."
docker compose -f docker-compose.prod.yml exec -T api uv run python ../../scripts/init_database.py init
if [ $? -eq 0 ]; then
    echo "OK: データベース・スキーマ初期化完了"
else
    echo "ERROR: データベース・スキーマ初期化失敗"
    exit 1
fi

# API確認
if curl -f http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    echo "OK: API起動完了"
else
    echo "ERROR: API起動失敗"
    exit 1
fi

# Slack Bot確認
if docker compose -f docker-compose.prod.yml ps bot | grep -q "Up"; then
    echo "OK: Slack Bot起動完了"
else
    echo "ERROR: Slack Bot起動失敗"
    exit 1
fi

echo "デプロイ完了！"
echo "Web UI: http://localhost:8001"
echo "API: http://localhost:8000"
echo "Weaviate: http://localhost:8089"
echo ""
echo "ログ確認:"
echo "  全体: docker compose -f docker-compose.prod.yml logs -f"
echo "  API: docker compose -f docker-compose.prod.yml logs -f api"
echo "  Bot: docker compose -f docker-compose.prod.yml logs -f bot"
