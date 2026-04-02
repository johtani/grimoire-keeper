#!/bin/bash

# システムパッケージの更新とsqlite3のインストール
sudo apt-get update
sudo apt-get install -y sqlite3 unzip jq

# bws (Bitwarden Secrets Manager CLI) のインストール
BWS_VERSION=$(curl -s https://api.github.com/repos/bitwarden/sdk-sm/releases/latest | jq -r '.tag_name')
if [ -z "$BWS_VERSION" ] || [ "$BWS_VERSION" = "null" ]; then
  echo "Warning: bwsのバージョン取得に失敗しました。bwsのインストールをスキップします。" >&2
else
  # アーキテクチャを検出
  ARCH=$(uname -m)
  case "$ARCH" in
    x86_64)   BWS_ARCH="x86_64-unknown-linux-gnu" ;;
    aarch64)  BWS_ARCH="aarch64-unknown-linux-gnu" ;;
    *)
      echo "Warning: 未対応のアーキテクチャ ($ARCH)。bwsのインストールをスキップします。" >&2
      BWS_ARCH=""
      ;;
  esac

  if [ -n "$BWS_ARCH" ]; then
    curl -fsSL "https://github.com/bitwarden/sdk-sm/releases/download/${BWS_VERSION}/bws-${BWS_ARCH}-${BWS_VERSION#v}.zip" -o /tmp/bws.zip
    sudo unzip -o /tmp/bws.zip bws -d /usr/local/bin/
    sudo chmod +x /usr/local/bin/bws
    rm /tmp/bws.zip
    echo "bws ${BWS_VERSION} (${BWS_ARCH}) をインストールしました。"
  fi
fi

# GitHub CLI (gh) のインストール
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt-get update && sudo apt-get install -y gh

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