#!/bin/bash
# 開発用 API サーバー起動スクリプト
# API のみを起動する。BWS、Weaviate、job worker は別途起動する。
# 使用方法: bash scripts/dev.sh

set -e

echo "Starting development API server (worker and BWS are not started)..."
exec uv run --package grimoire-api uvicorn grimoire_api.main:app --reload --host 0.0.0.0 --port 8000
