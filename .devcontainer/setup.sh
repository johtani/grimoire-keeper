#!/bin/bash

# システムパッケージの更新とsqlite3のインストール
sudo apt-get update
sudo apt-get install -y sqlite3

# uvのインストール
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# プロジェクトの初期化（Python 3.13）
uv init --name grimoire-keeper --no-readme --python 3.13

# 開発用依存関係の追加
uv add --dev pytest pytest-asyncio pytest-cov ruff mypy pre-commit

# ディレクトリ構造の作成
mkdir -p apps/bot/src/grimoire_bot apps/bot/tests
mkdir -p apps/api/src/grimoire_api apps/api/tests  
mkdir -p shared/src/grimoire_shared shared/tests
mkdir -p scripts

echo "Development environment setup completed!"