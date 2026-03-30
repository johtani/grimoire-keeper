# CLAUDE.md

このファイルは、リポジトリ内のコードを扱う Claude Code (claude.ai/code) への案内です。

## プロジェクト概要

**Grimoire Keeper** は個人向けの AI による URL コンテンツ要約・セマンティック検索システムです。Jina AI Reader でウェブページを取得し、Google Gemini (LiteLLM 経由) で要約し、Weaviate にベクトル埋め込みを保存し、FastAPI バックエンドで検索・取得を提供します。

## よく使うコマンド

すべてのコマンドは `uv` (Python パッケージマネージャ) を使用します。`/workspace` から実行してください。

```bash
# チェックアウト後に依存関係を同期
uv sync

# リント & 型チェック
uv run ruff check .
uv run ruff format .
uv run mypy .          # mypy 設定により apps/bot と apps/api/tests は除外

# 全テストを実行 (pytest.ini により apps/api/tests のみ対象)
uv run pytest

# ユニットテストのみ実行
uv run pytest apps/api/tests/unit/ -v

# インテグレーションテストを実行 (Weaviate の起動が必要)
uv run pytest apps/api/tests/integration/ -v

# 単一テストファイルを実行
uv run pytest apps/api/tests/unit/services/test_vectorizer.py -v

# カバレッジ付きで実行
uv run pytest --cov=apps --cov-report=html --cov-report=term-missing

# API を起動 (bws run がシークレットを自動注入)
bash scripts/dev.sh

# Weaviate を起動 (インテグレーションテストと API に必要)
docker compose up -d weaviate

# データベーススキーマを初期化
uv run python scripts/init_database.py init
```

## アーキテクチャ

### サービス構成

```
apps/api/   — FastAPI バックエンド (メインアプリケーション)
apps/bot/   — Slack ボット (将来実装)
apps/web/   — Nginx 静的 Web UI
shared/     — サービス間で共有する OpenTelemetry インストルメンテーション
```

Docker Compose サービスのポート: API `8000`、Weaviate `8089→8080`、Web `8001→80`

### URL 処理パイプライン

1. `POST /api/v1/process-url` — 同期処理: 重複チェック、`Page` レコード作成、ID を返却
2. バックグラウンドタスクが非同期で実行:
   - **Jina Client** が Jina AI Reader API 経由でページコンテンツを取得
   - **LLM Service** が Gemini (gemini-2.5-flash-lite via LiteLLM) を呼び出し → 要約 + 20 キーワードを JSON で返却
   - **ChunkingService** がコンテンツを分割 (Chonkie 使用)、**VectorizerService** がチャンクを Weaviate コレクション `GrimoireChunk` に 3 つの名前付きベクトルで保存: `content_vector`、`title_vector`、`memo_vector` (要約チャンクは `isSummary=true` でフラグ付け)
3. 各ステップで `Page` の `last_success_step` を更新してスマートリトライに対応

処理ステート: `NULL → downloaded → llm_processed → vectorized → completed`

### リトライ機構

`RetryService` が `last_success_step` から処理を再開し、完了済みのステージをスキップします。ベクトル化のみ失敗した場合に再取得・再要約を避けられます。

### データストレージ

- **SQLite** (`DATABASE_PATH`): `pages` テーブル (URL, title, summary, keywords, weaviate_id, last_success_step) と `process_logs` テーブル
- **Weaviate** (`WEAVIATE_HOST:WEAVIATE_PORT`): `GrimoireChunk` コレクション — セマンティック検索用ベクトルチャンク
- **JSON ファイル** (`JSON_STORAGE_PATH`): Jina の生コンテンツをページごとにキャッシュ (`data/json/{page_id}.json`)

### 重要ファイル

| パス | 役割 |
|------|------|
| `apps/api/src/grimoire_api/config.py` | Pydantic `Settings` — 全環境変数; モジュールレベルの `settings` シングルトン; 起動時に `validate_required_vars()` を呼び出し |
| `apps/api/src/grimoire_api/main.py` | FastAPI アプリ、lifespan、ルーター登録 |
| `apps/api/src/grimoire_api/services/` | コアビジネスロジック (url_processor, llm, chunking_service, vectorizer, search, retry) |
| `apps/api/src/grimoire_api/repositories/` | データアクセス層 (SQLite + ファイルストレージ) |
| `apps/api/src/grimoire_api/routers/` | FastAPI ルーター (process, search, pages, retry, health) |
| `apps/api/src/grimoire_api/models/` | SQLAlchemy/Pydantic モデルとリクエスト/レスポンススキーマ |

## 設定とシークレット

環境変数は `.env` (テスト時は `.env.test`) から読み込まれます。必要な API キー:
- `JINA_API_KEY` — Jina AI Reader
- `GOOGLE_API_KEY` — Google Gemini
- `OPENAI_API_KEY` — Weaviate text2vec-openai 埋め込み (`text-embedding-ada-002`)

`.env` には `BWS_ACCESS_TOKEN` のみを保存し、その他のシークレットは起動時に `bws run` が Bitwarden Secrets Manager から取得してサブプロセスに注入します (キーのプレフィックスは `GRIMOIRE_KEEPER_`)。開発は `scripts/dev.sh`、本番は `scripts/start.sh` を使用します。

## テストの注意事項

- `pytest.ini` (独立ファイル) で `testpaths = apps/api/tests`、`asyncio_mode = auto`、`ENV_FILE=.env.test` を設定
- ユニットテストは外部依存をモック化; インテグレーションテストは Weaviate の起動が必要
- `.env.test` にはユニットテストに十分なダミー API キーが含まれる
- カバレッジは `apps/` ディレクトリのみ対象

## ワークスペース構成

`apps/api`、`apps/bot`、`shared` をメンバーとする `uv` ワークスペースです。ルートの `pyproject.toml` で共有の開発依存関係 (pytest, ruff, mypy) を定義しています。サービス間の共通機能は `shared/` に配置してください。
