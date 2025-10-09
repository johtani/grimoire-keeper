#!/bin/bash

set -e

echo "🚀 Grimoire Keeper デプロイ開始"

# 環境変数チェック
if [ ! -f .env ]; then
    echo "❌ .envファイルが見つかりません"
    echo "cp .env.example .env を実行してAPIキーを設定してください"
    exit 1
fi

# 必要なAPIキーチェック
source .env
if [ -z "$OPENAI_API_KEY" ] || [ -z "$GOOGLE_API_KEY" ] || [ -z "$JINA_API_KEY" ]; then
    echo "❌ バックエンド用APIキーが設定されていません"
    echo "OPENAI_API_KEY, GOOGLE_API_KEY, JINA_API_KEYを.envに設定してください"
    exit 1
fi

# Slack Bot用APIキーチェック
if [ -z "$SLACK_BOT_TOKEN" ] || [ -z "$SLACK_SIGNING_SECRET" ] || [ -z "$SLACK_APP_TOKEN" ]; then
    echo "❌ Slack Bot用APIキーが設定されていません"
    echo "SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SLACK_APP_TOKENを.envに設定してください"
    exit 1
fi

# データディレクトリ作成
echo "📁 データディレクトリ作成中..."
sudo mkdir -p /opt/grimoire-keeper-data/{database,json,weaviate}
sudo chown -R $USER:$USER /opt/grimoire-keeper-data

# 既存コンテナ停止・削除
echo "🛑 既存サービス停止中..."
docker compose -f docker-compose.prod.yml down

# イメージビルド
echo "🔨 イメージビルド中..."
docker compose -f docker-compose.prod.yml build --no-cache

# サービス起動
echo "🚀 サービス起動中..."
docker compose -f docker-compose.prod.yml up -d

# ヘルスチェック
echo "🔍 サービス起動確認中..."
sleep 10

# Weaviate確認
if curl -f http://localhost:8089/v1/meta >/dev/null 2>&1; then
    echo "✅ Weaviate起動完了"
else
    echo "❌ Weaviate起動失敗"
    exit 1
fi

# データベース・スキーマ初期化
echo "🔧 データベース・スキーマ初期化中..."
docker compose -f docker-compose.prod.yml exec -T api python scripts/init_database.py init
if [ $? -eq 0 ]; then
    echo "✅ データベース・スキーマ初期化完了"
else
    echo "❌ データベース・スキーマ初期化失敗"
    exit 1
fi

# API確認
if curl -f http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    echo "✅ API起動完了"
else
    echo "❌ API起動失敗"
    exit 1
fi

# Slack Bot確認
if docker compose -f docker-compose.prod.yml ps bot | grep -q "Up"; then
    echo "✅ Slack Bot起動完了"
else
    echo "❌ Slack Bot起動失敗"
    exit 1
fi

echo "🎉 デプロイ完了！"
echo "API: http://localhost:8000"
echo "Weaviate: http://localhost:8089"
echo "Slack Bot: コンテナ内で実行中"
echo ""
echo "ログ確認:"
echo "  全体: docker compose -f docker-compose.prod.yml logs -f"
echo "  API: docker compose -f docker-compose.prod.yml logs -f api"
echo "  Bot: docker compose -f docker-compose.prod.yml logs -f bot"