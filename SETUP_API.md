# Grimoire Keeper API サービス起動手順

## 前提条件
- Docker Desktop がインストール済み
- VS Code + Dev Containers 拡張機能がインストール済み

## 1. 環境構築

### 1.1 devcontainer起動
```bash
# VS Codeでプロジェクトを開く
code .

# コマンドパレット (Ctrl+Shift+P) で以下を実行
# "Dev Containers: Reopen in Container"
```

### 1.2 環境変数設定
```bash
# .envファイルを作成
cp .env.example .env

# 必要なAPIキーを設定 (.envファイルを編集)
# - OPENAI_API_KEY: OpenAI APIキー (必須)
# - GOOGLE_API_KEY: Google Gemini APIキー (必須) 
# - JINA_API_KEY: Jina AI Reader APIキー (必須)
```

### 1.3 依存関係同期
```bash
uv sync
```

## 2. データベース初期化

### 2.1 データベーステーブル作成
```bash
# データベース初期化スクリプト実行
uv run python -c "
import asyncio
from apps.api.src.grimoire_api.repositories.database import DatabaseConnection

async def init_db():
    db = DatabaseConnection()
    await db.initialize_tables()
    print('Database initialized successfully!')

asyncio.run(init_db())
"
```

## 3. Weaviate起動

### 3.1 Weaviateコンテナ起動
```bash
# Weaviateをバックグラウンドで起動
docker-compose up -d weaviate
```

### 3.2 Weaviate接続確認
```bash
# Weaviateが起動したか確認
curl http://localhost:8080/v1/meta
```

## 4. APIサービス起動

### 4.1 開発サーバー起動
```bash
# FastAPI開発サーバーを起動
uv run --package grimoire-api uvicorn grimoire_api.main:app --reload --host 0.0.0.0 --port 8000
```

### 4.2 API動作確認
```bash
# ヘルスチェック
curl http://localhost:8000/api/v1/health

# APIドキュメント確認
# ブラウザで http://localhost:8000/docs を開く
```

## 5. 動作テスト

### 5.1 URL処理テスト
```bash
# サンプルURL処理
curl -X POST "http://localhost:8000/api/v1/process-url" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "memo": "テストページ"
  }'
```

### 5.2 検索テスト
```bash
# ベクトル検索テスト
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "テスト",
    "limit": 5
  }'
```

## 6. トラブルシューティング

### 6.1 よくある問題

**データベースエラー**
```bash
# データベースファイルの権限確認
ls -la grimoire.db

# データベース再初期化
rm grimoire.db
# 手順2.1を再実行
```

**Weaviate接続エラー**
```bash
# Weaviateコンテナ状態確認
docker-compose ps weaviate

# Weaviate再起動
docker-compose restart weaviate
```

**APIキーエラー**
```bash
# 環境変数確認
cat .env

# APIキーが正しく設定されているか確認
```

### 6.2 ログ確認
```bash
# APIサーバーログ
# コンソール出力を確認

# Weaviateログ
docker-compose logs weaviate
```

## 7. 開発時の推奨コマンド

### 7.1 コード品質チェック
```bash
# リント・フォーマット
uv run ruff check .
uv run ruff format .

# 型チェック
uv run mypy apps/api/src/

# テスト実行
uv run pytest
```

### 7.2 サービス管理
```bash
# 全サービス起動
docker-compose up -d

# 全サービス停止
docker-compose down

# ログ確認
docker-compose logs -f
```

## 8. 本番環境への準備

### 8.1 環境変数設定
- 本番用APIキーの設定
- データベースパスの調整
- Weaviate URLの設定

### 8.2 セキュリティ設定
- CORS設定の調整
- 認証機能の追加検討
- HTTPS設定

---

## 参考情報

- **API仕様**: http://localhost:8000/docs
- **プロジェクト構成**: [README.md](./README.md)
- **開発ワークフロー**: [.amazonq/rules/development-workflow.md](./.amazonq/rules/development-workflow.md)