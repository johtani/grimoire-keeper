#!/bin/bash
# サーバー起動ラッパースクリプト
# Bitwarden Secrets Managerからシークレットを取得してdocker composeを起動する
# 使用方法: bash scripts/start.sh [docker compose options]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# シークレットを環境変数に展開
source "${SCRIPT_DIR}/load_secrets.sh"

# docker composeを起動
echo "Starting services..."
docker compose -f "${SCRIPT_DIR}/../docker-compose.prod.yml" up "$@"
