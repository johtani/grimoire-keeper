#!/bin/bash
# 開発用APIサーバー起動スクリプト
# Bitwarden Secrets Managerからシークレットを取得してuvicornを起動する
# 使用方法: bash scripts/dev.sh [uvicorn options]

set -e

if [ -z "${BWS_ACCESS_TOKEN}" ]; then
  echo "Error: BWS_ACCESS_TOKEN is not set" >&2
  exit 1
fi

if ! command -v bws &> /dev/null; then
  echo "Error: bws CLI is not installed. Run .devcontainer/setup.sh or install manually." >&2
  exit 1
fi

echo "Starting development server with secrets from Bitwarden Secrets Manager..."
bws run -- bash -c '
  export OPENAI_API_KEY="${GRIMOIRE_KEEPER_OPENAI_API_KEY}"
  export GOOGLE_API_KEY="${GRIMOIRE_KEEPER_GOOGLE_API_KEY}"
  export JINA_API_KEY="${GRIMOIRE_KEEPER_JINA_API_KEY}"
  exec uv run --package grimoire-api uvicorn grimoire_api.main:app --reload "$@"
' -- "$@"
