# Grimoire Keeper / グリモワール・キーパー

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)

**Grimoire Keeper** is a personal AI-powered URL content summarization and search system. It automatically processes web pages, extracts summaries and keywords using LLM, and enables semantic search through vector embeddings.

**グリモワール・キーパー**は、個人用のAI駆動URLコンテンツ要約・検索システムです。Webページを自動処理し、LLMを使用して要約とキーワードを抽出し、ベクトル埋め込みによるセマンティック検索を可能にします。

> **⚠️ Personal Tool Notice / 個人ツールについて**
> 
> This is a personal productivity tool designed for individual use. It is not intended for commercial use or multi-user environments. The system processes and stores web content locally and may not be suitable for enterprise or production deployments without additional security and scalability considerations.
> 
> これは個人の生産性向上のために設計された個人用ツールです。商用利用や複数ユーザー環境での使用は想定していません。システムはWebコンテンツをローカルで処理・保存するため、追加のセキュリティや拡張性の考慮なしに企業や本番環境での展開には適さない場合があります。

## ✨ Features / 機能

- 🔗 **URL Processing / URL処理**: Automatically fetch and process web page content / Webページコンテンツの自動取得・処理
- 🤖 **AI Summarization / AI要約**: Generate summaries and keywords using a configurable LLM, with hierarchical summarization for long pages / 設定可能なLLMによる要約・キーワード抽出と、長文ページの階層的な分割要約
- 🔍 **Vector Search / ベクトル検索**: Semantic search powered by Weaviate and OpenAI embeddings / WeaviateとOpenAI埋め込みによるセマンティック検索
- 📊 **Flexible Filtering / 柔軟なフィルタリング**: Search by URL, keywords, date ranges / URL、キーワード、日付範囲での検索
- 🔄 **Smart Retry Processing / スマート再処理**: Intelligent retry from last successful step for failed operations / 失敗した処理を最後の成功ステップから賢く再実行
- 🏗️ **Modular Architecture / モジュラーアーキテクチャ**: Separate API and bot services / APIとボットサービスの分離
- 🧪 **Comprehensive Testing / 包括的テスト**: Unit and integration tests included / ユニットテストと統合テストを含む

## 🚀 Quick Start / クイックスタート

### Prerequisites / 前提条件

- Python 3.13+
- Docker & Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- `bws` (Bitwarden Secrets Manager CLI) — devcontainer 使用時は自動インストール

  ```bash
  # macOS
  brew install bitwarden/tools/bws
  # Linux
  BWS_VERSION=$(curl -s https://api.github.com/repos/bitwarden/sdk-sm/releases/latest | jq -r '.tag_name')
  curl -fsSL "https://github.com/bitwarden/sdk-sm/releases/download/${BWS_VERSION}/bws-x86_64-unknown-linux-gnu-${BWS_VERSION#v}.zip" -o /tmp/bws.zip
  sudo unzip -o /tmp/bws.zip bws -d /usr/local/bin/ && sudo chmod +x /usr/local/bin/bws && rm /tmp/bws.zip
  ```

### Installation / インストール

1. **Clone the repository / リポジトリのクローン**
   ```bash
   git clone https://github.com/your-username/grimoire-keeper.git
   cd grimoire-keeper
   ```

2. **Set up environment / 環境設定**
   ```bash
   cp .env.example .env
   # 非秘密の設定値を .env に記載
   # BWS_ACCESS_TOKEN は ~/.config/bws.env に保存 (リポジトリ外)
   mkdir -p ~/.config
   echo 'BWS_ACCESS_TOKEN=your-access-token' > ~/.config/bws.env
   chmod 600 ~/.config/bws.env
   ```

   Long pages are split into partial summaries and combined hierarchically so
   that every LLM request remains within the configured context window.
   The input budget is `LLM_CONTEXT_WINDOW - LLM_MAX_OUTPUT_TOKENS`.

   長文ページは部分要約に分割して階層的に統合し、各LLMリクエストが設定した
   コンテキスト上限に収まるよう処理します。入力予算は
   `LLM_CONTEXT_WINDOW - LLM_MAX_OUTPUT_TOKENS` です。

   | Environment variable / 環境変数 | Default / デフォルト | Description / 説明 |
   |---|---:|---|
   | `LLM_CONTEXT_WINDOW` | `32768` | Model context-window size / モデルのコンテキスト上限 |
   | `LLM_MAX_OUTPUT_TOKENS` | `1024` | Tokens reserved for each response / 各レスポンス用に確保する最大トークン数 |
   | `LLM_SUMMARY_CONCURRENCY` | `3` | Maximum concurrent partial-summary requests / 部分要約の最大同時リクエスト数 |

   > **devcontainer を使う場合 / Using devcontainer:**
   > VS Code で `Ctrl+Shift+P` → "Dev Containers: Reopen in Container" を実行すると
   > bws CLI のインストールと依存関係のセットアップが自動で行われます。

3. **Install dependencies / 依存関係のインストール**
   ```bash
   uv sync --all-packages
   ```

4. **Check the local LLM / ローカルLLMの確認**
   ```bash
   curl --fail-with-body http://localhost:8080/v1/models
   ```

   The default Compose configuration connects from the worker container to the
   host LLM at `http://host.docker.internal:8080/v1`. When the worker runs
   directly on the host, use `LLM_API_BASE=http://localhost:8080/v1`. The LLM
   must listen on an address reachable from Docker, not only `127.0.0.1`.

   デフォルトのCompose構成では、workerコンテナからホスト上のLLMへ
   `http://host.docker.internal:8080/v1` で接続します。workerをホスト上で直接
   実行する場合は `LLM_API_BASE=http://localhost:8080/v1` を使用します。LLMは
   `127.0.0.1` だけでなく、Dockerから到達可能なアドレスでlistenしてください。

5. **Start all services (recommended) / 全サービスの起動（推奨）**
   ```bash
   bash scripts/start.sh -d
   ```

   This starts Web, API, the singleton Job Worker, and Weaviate with secrets
   injected by Bitwarden Secrets Manager. Do not scale the worker beyond one
   process for the same SQLite database.

   Bitwarden Secrets Managerからシークレットを注入し、Web、API、単一のJob Worker、
   Weaviateを起動します。同じSQLiteデータベースに対してworkerを複数起動しないでください。

6. **Verify all services / 全サービスの動作確認**
   ```bash
   # API readiness (also checks SQLite and Weaviate)
   curl --fail-with-body http://localhost:8000/api/v1/health/ready

   # Job Worker container health
   docker compose -f docker-compose.prod.yml ps worker

   # Weaviate readiness
   curl --fail-with-body http://localhost:8089/v1/.well-known/ready

   # Local LLM (when using the default local configuration)
   curl --fail-with-body http://localhost:8080/v1/models

   # Web UI
   # Open http://localhost:8001 in a browser
   ```

7. **Process a URL and search / URLを処理して検索**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/process-url" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://example.com", "memo": "Quick Start check"}'

   # Replace {page_id} with the page_id returned above and wait for completion.
   curl "http://localhost:8000/api/v1/process-status/{page_id}"

   curl -X POST "http://localhost:8000/api/v1/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "example domain", "limit": 5}'
   ```

   The registration request returns `202 Accepted`. Repeat the status request
   until processing is completed, then run the search.

   URL登録は `202 Accepted` を返します。処理が完了するまで状態確認を繰り返してから、
   検索を実行してください。

### Manual development startup / 開発環境での個別起動

To run services individually, initialize the database and start each command in
a separate terminal. Set the worker-only credentials (`JINA_API_KEY`,
`OPENAI_API_KEY`, and, for a cloud LLM, `LLM_API_KEY`) securely in the worker's
environment before starting it.

サービスを個別に実行する場合は、データベースを初期化し、各コマンドを別ターミナルで
起動します。worker起動前に、worker専用の認証情報（`JINA_API_KEY`、
`OPENAI_API_KEY`、クラウドLLM利用時は `LLM_API_KEY`）を安全に環境へ設定してください。

```bash
# Terminal 1: Weaviate
docker compose -f docker-compose.prod.yml up -d weaviate

# Initialize once Weaviate is ready
uv run python scripts/init_database.py init

# Terminal 2: API
bash scripts/dev.sh

# Terminal 3: exactly one Job Worker
uv run --package grimoire-api python -m grimoire_api.worker
```

### Jobs remain queued / ジョブが queued のままの場合

The API only enqueues work. If the Job Worker is not running, processing remains
`queued`. Check the worker state and logs, then verify its required credentials
and its connections to Weaviate and the LLM:

APIはジョブをキューへ登録するだけです。Job Workerが起動していない場合、処理は
`queued` のまま進みません。workerの状態とログを確認し、必須の認証情報、Weaviate、
LLMへの接続を確認してください。

```bash
docker compose -f docker-compose.prod.yml ps worker
docker compose -f docker-compose.prod.yml logs --tail=100 worker
docker compose -f docker-compose.prod.yml config | grep -A1 LLM_API_BASE
```

See [Development](docs/development.md#docker-からローカル-llm-へ接続できない場合) for
container-side LLM checks and detailed troubleshooting.

コンテナ内からのLLM疎通確認と詳細な診断方法は
[Development](docs/development.md#docker-からローカル-llm-へ接続できない場合)を参照してください。

## 📖 Usage / 使用方法

### Process a URL / URLの処理

```bash
curl -X POST "http://localhost:8000/api/v1/process-url" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "memo": "Interesting article"}'
```

The API persists a job and immediately returns `202 Accepted` with `page_id` and
`job_id`. A dedicated worker process executes queued jobs.
API はジョブを永続化し、`page_id` と `job_id` を含む `202 Accepted` を即座に返します。
キューに入ったジョブは専用 worker プロセスが処理します。

### Search content / コンテンツの検索

```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "limit": 5}'
```

### Check processing status / 処理状況の確認

```bash
curl -X GET "http://localhost:8000/api/v1/process-status/{page_id}"
```

### Retry failed processing / 失敗した処理の再実行

```bash
# Retry a specific page / 特定のページを再処理
curl -X POST "http://localhost:8000/api/v1/retry/{page_id}"

# Retry all failed pages / 失敗した全ページを再処理
curl -X POST "http://localhost:8000/api/v1/retry-failed"
```

## 🏗️ Architecture / アーキテクチャ

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Browser/Web  │  │  Slack Bot   │  │  API Client  │
│   Web UI     │  │              │  │              │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       └─────────────────┼─────────────────┘
                         ▼
                 ┌───────────────┐
                 │ FastAPI API   │
                 │ request layer │
                 └───────┬───────┘
                         ▼
                 ┌───────────────┐
                 │    SQLite     │
                 │ pages / jobs │
                 │ logs / repair│
                 └───────┬───────┘
                  persistent queue
                         ▼
                 ┌───────────────┐
                 │  Job Worker   │
                 │ (one per DB)  │
                 └───────┬───────┘
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   Jina AI Reader   LLM via LiteLLM   JSON Cache
          └──────────────┬──────────────┘
                         ▼
                 ┌───────────────┐
                 │   Weaviate    │
                 │ Page / Chunk  │
                 └───────────────┘
```

### Components / コンポーネント

- **Web UI**: Nginx-served browser interface for URL registration and search / URL登録・検索用のNginx Web UI
- **Slack Bot**: Slack interface that calls the FastAPI backend / FastAPIバックエンドを利用するSlackインターフェース
- **FastAPI Backend**: Request validation and REST APIs for processing, search, retry, and repair management / URL処理・検索・再試行・修復管理のREST API
- **Job Worker**: Dedicated singleton process that claims persistent jobs and resumes interrupted work after startup / 永続ジョブを取得し、起動時に中断処理を復旧する専用の単一プロセス
- **JSON Cache**: Replaceable raw Jina response artifacts used for reprocessing / 再処理に利用する交換可能なJina生レスポンス成果物
- **External APIs**: Jina AI Reader, a LiteLLM-compatible LLM provider, and OpenAI embeddings / Jina AI Reader、LiteLLM互換LLMプロバイダー、OpenAI埋め込み

### Data stores / データストア

SQLite is the source of truth and contains these tables:
SQLiteは正本として以下のテーブルを保持します。

- `pages`: URL, memo, summary, keywords, processing status, and last successful step / URL、メモ、要約、キーワード、処理状態、最終成功ステップ
- `jobs`: Persistent `initial`, `retry`, and `reprocess` jobs and their current steps / 永続化された初回・再試行・再処理ジョブと現在ステップ
- `process_logs`: Per-page processing and failure history / ページ単位の処理・失敗履歴
- `repair_cases`: Detected repair reasons and `pending` / `resolved` state / 修復理由と未解決・解決済み状態
- `schema_migrations`: Applied SQLite schema versions / 適用済みSQLiteスキーマバージョン

Weaviate is a rebuildable search index with two collections:
Weaviateは再構築可能な検索索引として2つのコレクションを保持します。

- `GrimoirePage`: One representative object per page with title, memo, summary, keywords, `title_vector`, and `memo_vector` / ページごとの代表情報とタイトル・メモ用ベクトル
- `GrimoireContentChunk`: Body chunks with `content_vector` / `content_vector`を持つ本文チャンク

### Process model / プロセスモデル

API processes serve reads and validate mutations. URL-processing mutations only
persist and enqueue jobs; they do not execute the processing pipeline inline. API
processes may therefore be started with multiple Uvicorn workers or replicas. Job
execution belongs exclusively to the dedicated `worker` service. Run exactly one
worker process against a SQLite database.

API プロセスは読み取りAPIの提供と更新リクエストの検証を行います。URL処理の更新は
永続化とジョブ登録までを担当し、処理パイプラインをインライン実行しません。そのため、
複数の Uvicorn worker や replica で起動できます。ジョブを実行するのは専用 `worker`
サービスだけです。同じ SQLite データベースに対する worker プロセスは必ず1つにしてください。

### URL registration and processing / URL登録と処理

1. `POST /api/v1/process-url` returns the existing `page_id` for a duplicate URL.
   For a new URL, it atomically creates a `pages` row, an initial `process_logs`
   row, and a queued `jobs` row, then returns `202 Accepted` with `page_id` and
   `job_id` without running the pipeline inline.
2. The worker atomically claims the oldest queued job. On startup it returns
   interrupted `running` jobs to the queue, so work survives API and worker restarts.
3. The worker downloads content through Jina, stores the raw response in
   `data/json/{page_id}.json`, generates a summary and keywords through LiteLLM,
   and writes page and chunk objects to Weaviate.
4. SQLite records each successful pipeline step (`downloaded`, `llm_processed`,
   `vectorized`, `completed`). Retry and reprocess jobs start from the selected or
   last safe step instead of repeating completed work.

`POST /api/v1/process-url` は重複URLなら既存の `page_id` を返し、新規URLならページ・
開始ログ・永続ジョブを同一トランザクションで作成して `202 Accepted` を返します。workerは
キューの古いジョブから取得し、Jina取得、JSON保存、LLM要約、Weaviate登録を順に実行します。
成功ステップはSQLiteへ記録され、再起動や再試行では完了済み工程を安全にスキップできます。

### Search flow / 検索フロー

`POST /api/v1/search` selects the Weaviate collection from `vector_name`:
`title_vector` and `memo_vector` query `GrimoirePage`, while `content_vector`
queries `GrimoireContentChunk`. Candidate `pageId` values are loaded from SQLite,
which supplies the response metadata and applies URL, keyword, date, and excluded
keyword filters. Keyword search queries the `keywords` property in `GrimoirePage`.

`POST /api/v1/search` は `vector_name` に応じて検索先を選択します。タイトル・メモ検索は
`GrimoirePage`、本文検索は `GrimoireContentChunk` を利用し、候補ページのメタデータ取得と
URL・キーワード・日付・除外キーワードのフィルターはSQLiteを正本として行います。

## 🛠️ Development / 開発

### Project Structure / プロジェクト構造

```
grimoire-keeper/
├── apps/
│   ├── api/
│   │   ├── src/grimoire_api/  # FastAPI, worker, services, repositories
│   │   └── tests/             # API unit and integration tests
│   ├── bot/
│   │   ├── src/grimoire_bot/  # Slack bot
│   │   └── tests/             # Bot unit tests
│   └── web/                    # Nginx config and static Web UI
├── shared/
│   ├── src/grimoire_shared/   # Shared OpenTelemetry instrumentation
│   └── tests/                 # Shared package tests
├── tools/
│   ├── search_regression/     # Search-result snapshot comparison
│   └── weaviate_1_38_migration/ # Weaviate migration and validation
├── docs/                      # Documentation / ドキュメント
└── scripts/                   # Development, deployment, and DB utilities
```

### Development Workflow / 開発ワークフロー

1. **Environment Setup / 環境構築**
   ```bash
   # Start devcontainer or local environment
   # devcontainerまたはローカル環境の起動
   cp .env.example .env
   uv sync --all-packages
   ```

2. **Code Quality / コード品質**
   ```bash
   uv run ruff check .      # Linting / リント
   uv run ruff format .     # Formatting / フォーマット
   uv run mypy .            # Type checking / 型チェック
   uv run pytest           # Testing / テスト
   ```

3. **Running Services / サービスの実行**
   ```bash
   # Infrastructure / インフラ
   docker compose -f docker-compose.prod.yml up -d weaviate

   # Application / アプリケーション (bws run がシークレットを自動注入)
   bash scripts/dev.sh
   ```

### Testing / テスト

```bash
# Unit tests / ユニットテスト
uv run pytest apps/api/tests/unit/ -v

# Integration tests / 統合テスト
uv run pytest apps/api/tests/integration/ -v

# API coverage / API カバレッジ (fail-under: 80%)
uv run pytest apps/api/tests/unit/ -v --cov=grimoire_api --cov-report=html --cov-fail-under=80

# Bot coverage / Bot カバレッジ (fail-under: 65%)
uv run pytest apps/bot/tests/ -v --cov=grimoire_bot --cov-report=html --cov-fail-under=65

# Shared coverage / Shared カバレッジ (fail-under: 90%)
uv run pytest shared/tests/ -v --cov=grimoire_shared --cov-report=html --cov-fail-under=90
```

Coverage sources are the production packages `grimoire_api`, `grimoire_bot`, and
`grimoire_shared`; tests are excluded from the denominator. Hand-written production
code, including SQLite migrations, remains in scope.

カバレッジの対象は実装パッケージ `grimoire_api`、`grimoire_bot`、
`grimoire_shared` で、tests は分母から除外します。SQLite マイグレーションを含む
手書きの本番コードは計測対象に残します。

SQLiteスキーマを変更する場合は、バージョン番号、移行テスト、デプロイ前バックアップ、
ロールバックを含む[開発ガイドのSQLiteスキーマ変更手順](docs/development.md#sqliteスキーマの変更)
に従ってください。

## 🔧 Troubleshooting / トラブルシューティング

**Weaviate 接続エラー**
```bash
docker compose -f docker-compose.prod.yml ps weaviate       # 状態確認
docker compose -f docker-compose.prod.yml restart weaviate  # 再起動
```

**データベースエラー**
```bash
uv run python scripts/init_database.py check  # 状態確認
uv run python scripts/init_database.py reset  # リセット (全データ削除)
uv run python scripts/db_cli.py               # SQLite 直接操作
```

**API キーエラー**
```bash
cat ~/.config/bws.env  # BWS_ACCESS_TOKEN 確認
bws secret list        # Bitwarden からシークレット取得テスト
```

## 📊 API Reference / API リファレンス

### Endpoints / エンドポイント

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/process-url` | Process a URL and extract content / URLを処理してコンテンツを抽出 |
| `POST` | `/api/v1/search` | Search processed content / 処理済みコンテンツを検索 |
| `GET` | `/api/v1/process-status/{id}` | Check processing status / 処理状況を確認 |
| `POST` | `/api/v1/retry/{id}` | Retry failed processing for specific page / 特定ページの失敗処理を再実行 |
| `POST` | `/api/v1/reprocess/{id}` | Reprocess any page from a selected step / 任意ページを指定ステップから再処理 |
| `POST` | `/api/v1/retry-failed` | Retry all failed pages / 失敗した全ページを再実行 |
| `GET` | `/api/v1/repairs` | List repair cases / 修復ケース一覧 |
| `POST` | `/api/v1/repairs/import` | Import a repair report / 修復レポート取込 |
| `POST` | `/api/v1/repairs/scan` | Scan pages for repair cases / 修復対象ページのスキャン |
| `GET` | `/api/v1/pages` | List pages with status filtering / ステータスフィルタ付きページ一覧 |
| `GET` | `/api/v1/pages/{id}` | Get page details with error info / エラー情報付きページ詳細 |
| `GET` | `/api/v1/pages/{id}/repair` | Get page repair details / ページ修復詳細 |
| `PATCH` | `/api/v1/pages/{id}/url` | Correct a page URL / ページURL修正 |
| `GET` | `/api/v1/health` | Backward-compatible readiness check / 後方互換のReadinessチェック |
| `GET` | `/api/v1/health/ready` | Dependency readiness check / 依存サービスのReadinessチェック |
| `GET` | `/api/v1/health/live` | API process liveness check / APIプロセスのLivenessチェック |

### Request/Response Examples / リクエスト・レスポンス例

**Process URL / URL処理**
```json
POST /api/v1/process-url
{
  "url": "https://example.com",
  "memo": "Optional memo / オプションのメモ"
}

Response:
{
  "status": "queued",
  "page_id": 123,
  "job_id": 456,
  "message": "URL processing queued"
}
```

**Search / 検索**
```json
POST /api/v1/search
{
  "query": "machine learning",
  "limit": 5
}

Response:
{
  "results": [
    {
      "page_id": 123,
      "chunk_id": 0,
      "url": "https://example.com",
      "title": "ML Article",
      "memo": "Interesting article",
      "content": "Machine learning is a field of artificial intelligence...",
      "summary": "Article about machine learning...",
      "keywords": ["machine learning", "AI"],
      "created_at": "2026-01-15T09:30:00Z",
      "score": 0.95
    }
  ],
  "total": 1,
  "query": "machine learning"
}
```

## ⚙️ Configuration / 設定

### Secret Management / シークレット管理

API keys are managed by Bitwarden Secrets Manager. Only `BWS_ACCESS_TOKEN` needs to be set locally.
APIキーはBitwarden Secrets Managerで管理します。ローカルには`BWS_ACCESS_TOKEN`のみ設定が必要です。

```bash
# Bitwarden Secrets Manager
BWS_ACCESS_TOKEN=your-access-token

# Services / サービス
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
DATABASE_PATH=./grimoire.db
```

### Docker Compose

The project includes `docker-compose.prod.yml` for running Web, API, the Job
Worker, Weaviate, and the optional Slack bot:
プロジェクトにはWeb、API、Job Worker、Weaviate、任意のSlack botを実行するための
`docker-compose.prod.yml`が含まれています：

```bash
bash scripts/start.sh -d
```

## 🤝 Contributing / 貢献

This is a personal project, but contributions are welcome! / これは個人プロジェクトですが、貢献を歓迎します！

1. Fork the repository / リポジトリをフォーク
2. Create a feature branch / フィーチャーブランチを作成 (`git checkout -b feature/amazing-feature`)
3. Commit your changes / 変更をコミット (`git commit -m 'Add amazing feature'`)
4. Push to the branch / ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. Open a Pull Request / プルリクエストを開く

### Development Guidelines / 開発ガイドライン

- Follow PEP 8 style guide / PEP 8スタイルガイドに従う
- Add type hints to all functions / 全関数に型ヒントを追加
- Write tests for new features / 新機能にテストを書く
- Update documentation as needed / 必要に応じてドキュメントを更新
- Use conventional commit messages / 従来のコミットメッセージを使用

## 📄 License / ライセンス

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
このプロジェクトはMITライセンスの下でライセンスされています - 詳細は[LICENSE](LICENSE)ファイルを参照してください。

## 🙏 Acknowledgments / 謝辞

- [Jina AI Reader](https://jina.ai/) for content extraction / コンテンツ抽出
- [Weaviate](https://weaviate.io/) for vector search / ベクトル検索
- [Google Gemini](https://ai.google.dev/) for LLM processing / LLM処理
- [OpenAI](https://openai.com/) for embeddings / 埋め込み

## 📚 Documentation / ドキュメント

- [API Reference / APIリファレンス](docs/api-reference.md) — エンドポイント詳細とリトライ処理
- [Slack Bot Usage / Slack Bot使用方法](docs/slack-bot-usage.md)
- [CLAUDE.md](CLAUDE.md) — 開発ガイド・アーキテクチャ詳細 (Claude Code 向け)

## 🐛 Issues & Support / 問題とサポート

If you encounter any issues or have questions:
問題が発生した場合や質問がある場合：

1. Check the [documentation / ドキュメントを確認](docs/)
2. Search existing [issues / 既存の問題を検索](https://github.com/your-username/grimoire-keeper/issues)
3. Create a new issue with detailed information / 詳細情報を含む新しい問題を作成

---

**Made with ❤️ for personal productivity / 個人の生産性向上のために❤️で作成**
