#!/bin/bash

# システムパッケージの更新とsqlite3のインストール
sudo apt-get update
sudo apt-get install -y sqlite3 unzip

# bws (Bitwarden Secrets Manager CLI) のインストール
BWS_VERSION=$(curl -s https://api.github.com/repos/bitwarden/sdk-sm/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
curl -fsSL "https://github.com/bitwarden/sdk-sm/releases/download/${BWS_VERSION}/bws-x86_64-unknown-linux-gnu-${BWS_VERSION#v}.zip" -o /tmp/bws.zip
sudo unzip -o /tmp/bws.zip bws -d /usr/local/bin/
sudo chmod +x /usr/local/bin/bws
rm /tmp/bws.zip

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