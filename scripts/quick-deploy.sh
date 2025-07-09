#!/bin/bash

set -e

echo "🚀 Grimoire Keeper クイックデプロイ"

# 環境チェック
if ! command -v docker &> /dev/null; then
    echo "❌ Dockerがインストールされていません"
    echo "sudo apt install docker.io docker-compose-v2"
    exit 1
fi

# 環境変数チェック
if [ ! -f .env ]; then
    echo "📝 環境変数ファイルを作成します"
    cp .env.example .env
    echo "⚠️  .envファイルを編集してAPIキーを設定してください"
    echo "   必要なキー: OPENAI_API_KEY, GOOGLE_API_KEY, JINA_API_KEY"
    echo "   Slack用: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SLACK_APP_TOKEN"
    exit 1
fi

# デプロイ実行
echo "🔨 デプロイ開始..."
./scripts/deploy.sh

echo ""
echo "🎉 デプロイ完了！"
echo ""
echo "📋 次のステップ:"
echo "1. Slack Appを設定 (DEPLOY.md参照)"
echo "2. ngrokでローカル公開 (開発時)"
echo "3. 本番環境ではSSL証明書設定"
echo ""
echo "🔗 アクセス先:"
echo "  API: http://localhost:8000"
echo "  Weaviate: http://localhost:8080"
echo ""
echo "📊 ステータス確認:"
echo "  docker-compose -f docker-compose.prod.yml ps"