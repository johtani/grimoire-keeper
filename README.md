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
- 🤖 **AI Summarization / AI要約**: Generate summaries and extract keywords using Google Gemini / Google Geminiを使用した要約とキーワード抽出
- 🔍 **Vector Search / ベクトル検索**: Semantic search powered by Weaviate and OpenAI embeddings / WeaviateとOpenAI埋め込みによるセマンティック検索
- 📊 **Flexible Filtering / 柔軟なフィルタリング**: Search by URL, keywords, date ranges / URL、キーワード、日付範囲での検索
- 🏗️ **Modular Architecture / モジュラーアーキテクチャ**: Separate API and bot services / APIとボットサービスの分離
- 🧪 **Comprehensive Testing / 包括的テスト**: Unit and integration tests included / ユニットテストと統合テストを含む

## 🚀 Quick Start / クイックスタート

### Prerequisites / 前提条件

- Python 3.13+
- Docker & Docker Compose
- OpenAI API Key (for embeddings / 埋め込み用)
- Google API Key (for Gemini LLM / Gemini LLM用)
- Jina AI API Key (for content extraction / コンテンツ抽出用)

### Installation / インストール

1. **Clone the repository / リポジトリのクローン**
   ```bash
   git clone https://github.com/your-username/grimoire-keeper.git
   cd grimoire-keeper
   ```

2. **Set up environment / 環境設定**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys / APIキーを.envに設定
   ```

3. **Install dependencies / 依存関係のインストール**
   ```bash
   uv sync
   ```

4. **Start Weaviate / Weaviateの起動**
   ```bash
   docker compose up -d weaviate
   ```

5. **Initialize database / データベースの初期化**
   ```bash
   python scripts/init_database.py init
   ```

6. **Start the API / APIの起動**
   ```bash
   uv run --package grimoire-api uvicorn grimoire_api.main:app --reload
   ```

## 📖 Usage / 使用方法

### Process a URL / URLの処理

```bash
curl -X POST "http://localhost:8000/api/v1/process-url" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "memo": "Interesting article"}'
```

### Search content / コンテンツの検索

```bash
curl -X GET "http://localhost:8000/api/v1/search?query=machine%20learning&limit=5"
```

### Check processing status / 処理状況の確認

```bash
curl -X GET "http://localhost:8000/api/v1/process-status/{page_id}"
```

## 🏗️ Architecture / アーキテクチャ

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │───▶│  FastAPI    │───▶│  Weaviate   │
│ クライアント │    │     API     │    │ (Vector DB) │
└─────────────┘    └─────────────┘    └─────────────┘
                           │
                           ▼
                   ┌─────────────┐
                   │   SQLite    │
                   │ (Metadata)  │
                   └─────────────┘
```

### Components / コンポーネント

- **FastAPI Backend**: RESTful API for URL processing and search / URL処理と検索のためのRESTful API
- **Weaviate**: Vector database for semantic search / セマンティック検索用ベクトルデータベース
- **SQLite**: Metadata storage and processing logs / メタデータ保存と処理ログ
- **External APIs**: Jina AI Reader, Google Gemini, OpenAI Embeddings / 外部API

## 🛠️ Development / 開発

### Project Structure / プロジェクト構造

```
grimoire-keeper/
├── apps/
│   ├── api/           # FastAPI backend / FastAPIバックエンド
│   └── bot/           # Slack bot (future) / Slackボット（将来）
├── shared/            # Shared utilities / 共有ユーティリティ
├── docs/              # Documentation / ドキュメント
├── scripts/           # Utility scripts / ユーティリティスクリプト
└── tests/             # Test files / テストファイル
```

### Development Workflow / 開発ワークフロー

1. **Environment Setup / 環境構築**
   ```bash
   # Start devcontainer or local environment
   # devcontainerまたはローカル環境の起動
   cp .env.example .env
   uv sync
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
   docker compose up -d weaviate
   
   # Application / アプリケーション
   uv run --package grimoire-api uvicorn grimoire_api.main:app --reload
   ```

### Testing / テスト

```bash
# Unit tests / ユニットテスト
uv run pytest apps/api/tests/unit/ -v

# Integration tests / 統合テスト
uv run pytest apps/api/tests/integration/ -v

# All tests with coverage / カバレッジ付き全テスト
uv run pytest --cov=apps --cov-report=html
```

## 📊 API Reference / API リファレンス

### Endpoints / エンドポイント

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/process-url` | Process a URL and extract content / URLを処理してコンテンツを抽出 |
| `GET` | `/api/v1/search` | Search processed content / 処理済みコンテンツを検索 |
| `GET` | `/api/v1/process-status/{id}` | Check processing status / 処理状況を確認 |
| `GET` | `/api/v1/health` | Health check / ヘルスチェック |

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
  "status": "processing",
  "page_id": 123,
  "message": "URL processing started"
}
```

**Search / 検索**
```json
GET /api/v1/search?query=machine%20learning&limit=5

Response:
{
  "results": [
    {
      "page_id": 123,
      "url": "https://example.com",
      "title": "ML Article",
      "summary": "Article about machine learning...",
      "keywords": ["machine learning", "AI"],
      "score": 0.95
    }
  ]
}
```

## ⚙️ Configuration / 設定

### Environment Variables / 環境変数

```bash
# API Keys / APIキー
OPENAI_API_KEY=sk-...          # For embeddings / 埋め込み用
GOOGLE_API_KEY=...             # For Gemini LLM / Gemini LLM用
JINA_API_KEY=...               # For content extraction / コンテンツ抽出用

# Services / サービス
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
DATABASE_PATH=./grimoire.db

# Optional / オプション
JSON_STORAGE_PATH=./data/json  # Raw content storage / 生コンテンツ保存
```

### Docker Compose

The project includes a `docker-compose.yml` for running Weaviate:
プロジェクトにはWeaviate実行用の`docker-compose.yml`が含まれています：

```bash
docker compose up -d weaviate
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

For detailed documentation, see the [docs/](docs/) directory:
詳細なドキュメントについては、[docs/](docs/)ディレクトリを参照してください：

- [Backend Architecture / バックエンドアーキテクチャ](docs/architecture.md)
- [API Reference / APIリファレンス](docs/api-reference.md)
- [Development Guide / 開発ガイド](docs/development.md)

## 🐛 Issues & Support / 問題とサポート

If you encounter any issues or have questions:
問題が発生した場合や質問がある場合：

1. Check the [documentation / ドキュメントを確認](docs/)
2. Search existing [issues / 既存の問題を検索](https://github.com/your-username/grimoire-keeper/issues)
3. Create a new issue with detailed information / 詳細情報を含む新しい問題を作成

---

**Made with ❤️ for personal productivity / 個人の生産性向上のために❤️で作成**