#!/bin/bash
# Bitwarden Secrets Managerからシークレットを取得して環境変数に展開するスクリプト
# 使用方法: source scripts/load_secrets.sh

set -e

if [ -z "${BWS_ACCESS_TOKEN}" ]; then
  echo "Error: BWS_ACCESS_TOKEN is not set" >&2
  exit 1
fi

if ! command -v bws &> /dev/null; then
  echo "Error: bws CLI is not installed. Run: curl -fsSL https://github.com/bitwarden/sdk-sm/releases/latest/download/bws-x86_64-unknown-linux-gnu.zip | ..." >&2
  exit 1
fi

echo "Loading secrets from Bitwarden Secrets Manager..."

# bwsからシークレットを一括取得し、GRIMOIRE_KEEPER_プレフィックスのものだけ除去してexport
while IFS= read -r line; do
  case "$line" in
    GRIMOIRE_KEEPER_*) export "${line#GRIMOIRE_KEEPER_}" ;;
  esac
done < <(bws secret list --output env 2>/dev/null)

echo "Secrets loaded successfully."
