# 開発ワークフロー

## Git ブランチ運用
### 修正作業開始時の必須手順
1. `git checkout main` でmainブランチに切り替え
2. `git pull origin main` で最新状態を取得（リモートがある場合）
3. 修正内容に応じた新しいブランチを作成:
   - 新機能: `git checkout -b feature/機能名`
   - バグ修正: `git checkout -b fix/修正内容`
   - リファクタリング: `git checkout -b refactor/改善内容`
   - ドキュメント: `git checkout -b docs/更新内容`
4. 修正作業を実施
5. `git add .` と `git commit -m "説明"` でコミット

### 重要
- **mainブランチで直接作業しない**
- **必ず新しいブランチを作成してから修正を開始**

## 環境構築手順
1. devcontainer起動
2. `cp .env.example .env` で環境変数設定
3. `uv sync` で依存関係同期

## 開発パターン
- **推奨**: 混合実行
  - インフラ: `docker compose up -d weaviate`
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