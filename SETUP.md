# Grimoire Keeper 開発環境セットアップ

## 開発フロー概要

1. **devcontainer**: コード編集・テスト・デバッグ用
2. **コンテナ**: 各サービスの動作確認用
3. **統合テスト**: 全サービス連携確認

## 1. 初期セットアップ

```bash
# 1. devcontainer起動
# VSCode: Ctrl+Shift+P → "Dev Containers: Reopen in Container"

# 2. プロジェクト初期化（自動実行済み）
uv --version  # Python 3.13 + uv確認

# 3. 環境変数設定
cp .env.example .env
# .envファイルを編集してAPIキーを設定
```

## 2. 開発時の動作確認パターン

### パターンA: devcontainer内で直接実行
```bash
# 依存関係同期
uv sync

# Weaviateのみコンテナで起動
docker-compose up -d weaviate

# devcontainer内でアプリ実行
uv run --package grimoire-api uvicorn grimoire_api.main:app --reload --host 0.0.0.0
uv run --package grimoire-bot python -m grimoire_bot.main
```

### パターンB: 全てコンテナで実行
```bash
# 全サービス起動
docker-compose up

# または段階的起動
docker-compose up -d weaviate
docker-compose up -d api
docker-compose up bot
```

### パターンC: 混合実行（推奨）
```bash
# インフラ系はコンテナ
docker-compose up -d weaviate

# 開発中のサービスはdevcontainer内
# API開発時
uv run --package grimoire-api uvicorn grimoire_api.main:app --reload

# Bot開発時  
uv run --package grimoire-bot python -m grimoire_bot.main
```

## 3. テスト実行

```bash
# コード品質チェック
uv run ruff check .
uv run ruff format .
uv run mypy .

# 単体テスト
uv run pytest apps/api/tests/
uv run pytest apps/bot/tests/

# 統合テスト（全サービス起動後）
uv run pytest tests/integration/
```

## 4. 動作確認

```bash
# API確認
curl http://localhost:8000/api/v1/health

# Weaviate確認
curl http://localhost:8080/v1/meta

# ログ確認
docker-compose logs api
docker-compose logs bot
```