# AGENTS.md

このファイルは、リポジトリ内のコードを扱う Codex (Codex.ai/code) への案内です。

## プロジェクト概要

**Grimoire Keeper** は個人向けの AI による URL コンテンツ要約・セマンティック検索システムです。Jina AI Reader でウェブページを取得し、LLM (LiteLLM 経由、デフォルトはローカル LLM の `openai/qwen3-35b`) で要約し、Weaviate にベクトル埋め込みを保存し、FastAPI バックエンドで検索・取得を提供します。

## よく使うコマンド

すべてのコマンドは `uv` (Python パッケージマネージャ) を使用します。`/workspace` から実行してください。

```bash
# チェックアウト後に依存関係を同期 (全ワークスペースメンバーをインストール)
uv sync --all-packages

# リント & 型チェック
uv run ruff check .
uv run ruff format .
uv run mypy .          # apps/api/tests と apps/bot/tests は除外。Bot 本体と shared は対象

# 全テストを実行 (API、Bot、shared が対象)
uv run pytest

# API ユニットテストを実行
uv run pytest apps/api/tests/unit/ -v

# インテグレーションテストを実行 (Weaviate の起動が必要)
uv run pytest apps/api/tests/integration/ -v

# 単一テストファイルを実行
uv run pytest apps/api/tests/unit/services/test_vectorizer.py -v

# サービス別のカバレッジコマンドは docs/development.md を参照

# API を起動 (API のみ。BWS の展開と worker 起動は別途行う)
bash scripts/dev.sh

# ジョブ worker を別ターミナルで起動
uv run --package grimoire-api python -m grimoire_api.worker

# Weaviate を起動 (インテグレーションテストと API に必要)
docker compose -f docker-compose.prod.yml up -d weaviate

# データベーススキーマを初期化
uv run python scripts/init_database.py init
```

## アーキテクチャ

### サービス構成

```
apps/api/   — FastAPI バックエンド (メインアプリケーション)
apps/bot/   — Slack ボット
apps/web/   — Nginx 静的 Web UI
shared/     — サービス間で共有する OpenTelemetry インストルメンテーション
```

Docker Compose サービスのポート: API `8000`、Weaviate `8089→8080`、Web `8001→80`

### URL 処理パイプライン

1. `POST /api/v1/process-url` — 同期処理: 重複チェック、`Page` レコード作成、ID を返却
2. 独立した単一 **Job Worker** が SQLite の永続キューを claim して非同期で実行:
   - **Jina Client** が Jina AI Reader API 経由でページコンテンツを取得
   - **LLM Service** が LiteLLM 経由で LLM を呼び出し → 要約 + 20 キーワードを JSON で返却 (デフォルトは `openai/qwen3-35b`、`LLM_MODEL` 環境変数で変更可能)
   - **ChunkingService** がコンテンツを分割 (Chonkie 使用)、**VectorizerService** がページ代表データを `GrimoirePage` (`title_vector`、`memo_vector`) に、本文チャンクを `GrimoireContentChunk` (`content_vector`) に保存。両 collection は `pageId` で対応付ける
3. 各ステップで `Page` の `last_success_step` を更新してスマートリトライに対応

処理ステート: `NULL → downloaded → llm_processed → vectorized → completed`

### リトライ機構

`RetryService` が `last_success_step` から処理を再開し、完了済みのステージをスキップします。ベクトル化のみ失敗した場合に再取得・再要約を避けられます。

### データストレージ

- **SQLite** (`DATABASE_PATH`): `pages` テーブル (URL, title, summary, keywords, weaviate_id, last_success_step) と `process_logs` テーブル
- **Weaviate** (`WEAVIATE_HOST:WEAVIATE_PORT`): `GrimoirePage` — `pageId`, URL, title, memo, summary, keywords, createdAt と `title_vector` / `memo_vector`; `GrimoireContentChunk` — `pageId`, `chunkId`, content と `content_vector`。Vectorizer と再インデックスは両方、検索は指定 vector 側、repair の登録確認は `GrimoirePage`、削除 cleanup は両方を対象とする
- **JSON ファイル** (`JSON_STORAGE_PATH`): Jina の生コンテンツをページごとにキャッシュ (`data/json/{page_id}.json`)

### SQLiteスキーマ変更の規約

- スキーマ変更は `apps/api/src/grimoire_api/repositories/migrations.py` の `MIGRATIONS` 末尾に新しい連番として追加する
- リリース済みのマイグレーションは変更・並べ替え・削除せず、`LATEST_SCHEMA_VERSION` と期待スキーマ検証を同時に更新する
- DDL、データ変換、履歴追加は同じトランザクションで実行し、例外文字列によるエラーの握りつぶしや手動DDLを行わない
- 新規DB、対応する各旧バージョン、再実行、データ保持、ロールバック、未知・破損・将来スキーマの拒否をユニットテストに含める
- 本番移行前にSQLiteをバックアップし、旧コードへ戻す場合はDBも同じ時点へ復元する
- 詳細は `docs/development.md` の「SQLiteスキーマの変更」を参照する

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

環境変数は `.env` (テスト時は `.env.test`) から読み込まれます。`.env` には非秘密の
設定値だけを置き、シークレットをコミットしないでください。開発時の API と worker の
起動、BWS、必要な API キー、埋め込みモデル変更時の再インデックスについては
`docs/development.md` を参照してください。`scripts/dev.sh` 自体は BWS を呼び出しません。

## テストの注意事項

- `pyproject.toml` の `[tool.pytest.ini_options]` で API、Bot、shared のテストを収集し、`asyncio_mode = auto`、`ENV_FILE=.env.test` を設定
- ユニットテストは外部依存をモック化; インテグレーションテストは Weaviate の起動が必要
- `.env.test` にはユニットテストに十分なダミー API キーが含まれる
- サービス別のテスト・カバレッジコマンドは `docs/development.md` を参照

## Git ワークフロー

- **main へ直接コミットしない** — 必ずフィーチャーブランチを作成して PR 経由でマージする
- ブランチ命名: `feat/issue-<番号>-<短い説明>` / `fix/issue-<番号>-<短い説明>`
- コミットメッセージは conventional commit 形式 (`feat:`, `fix:`, `refactor:` など) + 日本語説明
- `/plan-issue <Issue URL>` で Issue 分析 → 計画 → ブランチ作成
- `/ship` で lint → テスト → コミット → PR 作成

## コミット前チェック (必須)

コミット前に **必ず** 以下を実行してすべてパスすること:

```bash
uv run ruff format .
uv run ruff check .
uv run pytest apps/api/tests/unit/ -v
```

エラーがあれば修正してからコミットする。自動修正: `uv run ruff check --fix .`

## テスト方針

- テストを実行するときは **全ユニットテストを実行する** (特定モジュールのみ実行しない)
  ```bash
  uv run pytest apps/api/tests/unit/ -v
  ```
- インテグレーションテストは Weaviate の起動が必要 (`docker compose -f docker-compose.prod.yml up -d weaviate`)
- 変更に関連するテストがない場合は新規作成する

## ワークスペース構成

`apps/api`、`apps/bot`、`shared` をメンバーとする `uv` ワークスペースです。ルートの `pyproject.toml` で共有の開発依存関係 (pytest, ruff, mypy) を定義しています。サービス間の共通機能は `shared/` に配置してください。
