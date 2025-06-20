# 開発ワークフロー

## 環境構築手順
1. devcontainer起動
2. `cp .env.example .env` で環境変数設定
3. `uv sync` で依存関係同期

## 開発パターン
- **推奨**: 混合実行
  - インフラ: `docker-compose up -d weaviate`
  - アプリ: `uv run --package grimoire-api uvicorn grimoire_api.main:app --reload`

## コード品質チェック
```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest
```

## 新機能追加時
1. 該当アプリディレクトリで作業
2. 共通機能は `shared/` に配置
3. テスト追加必須
4. ruffでフォーマット