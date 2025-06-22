# 🚀 Grimoire Keeper クイックスタート

## 最小限の手順で起動

### 1. 環境準備
```bash
# devcontainer起動後
cp .env.example .env
# .envファイルを編集してAPIキーを設定

uv sync
```

### 2. 段階的起動
```bash
# Step 1: SQLiteデータベース初期化
uv run python scripts/init_database.py sqlite

# Step 2: Weaviate起動
docker-compose up -d weaviate

# Step 3: Weaviateスキーマ初期化
uv run python scripts/init_database.py init

# Step 4: API起動
uv run --package grimoire-api uvicorn grimoire_api.main:app --reload --host 0.0.0.0
```

### 3. 動作確認
```bash
# ヘルスチェック
curl http://localhost:8000/api/v1/health

# APIドキュメント
# http://localhost:8000/docs
```

## トラブル時
```bash
# 状態確認
uv run python scripts/init_database.py check
docker-compose ps weaviate

# リセット
uv run python scripts/init_database.py reset
docker-compose restart weaviate

# データベース直接確認
uv run python scripts/db_cli.py
```

詳細は [SETUP_API.md](./SETUP_API.md) を参照してください。