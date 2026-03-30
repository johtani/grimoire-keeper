#!/bin/bash
# Bitwarden Secrets Managerからシークレットを取得して環境変数に展開するスクリプト
# 使用方法: source scripts/load_secrets.sh

# sourceでも直接実行でも正しく動作する終了関数
_bws_fail() {
  echo "$1" >&2
  # sourceされている場合はreturn、直接実行の場合はexit
  return 1 2>/dev/null || exit 1
}

if [ -z "${BWS_ACCESS_TOKEN}" ]; then
  _bws_fail "Error: BWS_ACCESS_TOKEN is not set" || return
fi

if ! command -v bws &> /dev/null; then
  _bws_fail "Error: bws CLI is not installed. Run .devcontainer/setup.sh or install manually." || return
fi

echo "Loading secrets from Bitwarden Secrets Manager..."

# bwsからシークレットを一括取得（エラーは標準エラーに表示）
bws_output=$(bws secret list --output env) || {
  _bws_fail "Error: bws secret list failed. BWS_ACCESS_TOKENが有効か確認してください。" || return
}

# GRIMOIRE_KEEPER_プレフィックスのシークレットのみ除去してexport
loaded=0
while IFS= read -r line; do
  case "$line" in
    GRIMOIRE_KEEPER_*)
      export "${line#GRIMOIRE_KEEPER_}"
      loaded=$((loaded + 1))
      ;;
  esac
done <<< "$bws_output"

if [ "$loaded" -eq 0 ]; then
  _bws_fail "Error: GRIMOIRE_KEEPER_ プレフィックスのシークレットが1件も見つかりませんでした。Bitwardenにシークレットが登録されているか確認してください。" || return
fi

# 必須変数が実際にロードされたか確認
missing=()
for var in OPENAI_API_KEY GOOGLE_API_KEY JINA_API_KEY; do
  [ -n "${!var}" ] || missing+=("$var")
done

if [ ${#missing[@]} -gt 0 ]; then
  _bws_fail "Error: 以下の必須シークレットがロードされませんでした: ${missing[*]}" || return
fi

echo "Secrets loaded successfully. ($loaded secrets)"
