#!/bin/bash
# 開発用APIサーバー起動スクリプト
# SQLite-backed API serverを起動する
# 使用方法: bash scripts/dev.sh

set -e

echo "Starting SQLite-backed development API server..."
exec uv run --package grimoire-api uvicorn grimoire_api.main:app --reload --host 0.0.0.0 --port 8000
