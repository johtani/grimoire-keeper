#!/bin/bash
# サーバー起動ラッパースクリプト
# Bitwarden Secrets Managerからシークレットを取得してdocker composeを起動する
# 使用方法: bash scripts/start.sh [docker compose options]

set -e

# BWS_ACCESS_TOKEN が未設定の場合は ~/.config/bws.env から読み込む
if [ -z "${BWS_ACCESS_TOKEN}" ]; then
  BWS_ENV="${HOME}/.config/bws.env"
  if [ -f "$BWS_ENV" ]; then
    # shellcheck source=/dev/null
    source "$BWS_ENV"
    export BWS_ACCESS_TOKEN
  fi
fi

if [ -z "${BWS_ACCESS_TOKEN}" ]; then
  echo "Error: BWS_ACCESS_TOKEN is not set. ~/.config/bws.env に設定してください。" >&2
  exit 1
fi

if ! command -v bws &> /dev/null; then
  echo "Error: bws CLI is not installed. Run .devcontainer/setup.sh or install manually." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting services with secrets from Bitwarden Secrets Manager..."
bws run -- docker compose -f "${SCRIPT_DIR}/../docker-compose.prod.yml" up "$@"
