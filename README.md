# Grimoire Keeper

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)

**Grimoire Keeper** is an AI-powered URL content summarization and search system. It automatically processes web pages, extracts summaries and keywords using LLM, and enables semantic search through vector embeddings.

## ✨ Features

- 🔗 **URL Processing**: Automatically fetch and process web page content
- 🤖 **AI Summarization**: Generate summaries and extract keywords using Google Gemini
- 🔍 **Vector Search**: Semantic search powered by Weaviate and OpenAI embeddings
- 📊 **Flexible Filtering**: Search by URL, keywords, date ranges
- 🏗️ **Modular Architecture**: Separate API and bot services
- 🧪 **Comprehensive Testing**: Unit and integration tests included

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- Docker & Docker Compose
- OpenAI API Key (for embeddings)
- Google API Key (for Gemini LLM)
- Jina AI API Key (for content extraction)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/grimoire-keeper.git
   cd grimoire-keeper
   ```

2. **Set up environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Install dependencies**
   ```bash
   uv sync
   ```

4. **Start Weaviate**
   ```bash
   docker-compose up -d weaviate
   ```

5. **Initialize database**
   ```bash
   python scripts/init_database.py init
   ```

6. **Start the API**
   ```bash
   uv run --package grimoire-api uvicorn grimoire_api.main:app --reload
   ```

## 📖 Usage

### Process a URL

```bash
curl -X POST "http://localhost:8000/api/v1/process-url" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "memo": "Interesting article"}'
```

### Search content

```bash
curl -X GET "http://localhost:8000/api/v1/search?query=machine%20learning&limit=5"
```

### Check processing status

```bash
curl -X GET "http://localhost:8000/api/v1/process-status/{page_id}"
```

## 🏗️ Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │───▶│  FastAPI    │───▶│  Weaviate   │
│             │    │     API     │    │ (Vector DB) │
└─────────────┘    └─────────────┘    └─────────────┘
                           │
                           ▼
                   ┌─────────────┐
                   │   SQLite    │
                   │ (Metadata)  │
                   └─────────────┘
```

### Components

- **FastAPI Backend**: RESTful API for URL processing and search
- **Weaviate**: Vector database for semantic search
- **SQLite**: Metadata storage and processing logs
- **External APIs**: Jina AI Reader, Google Gemini, OpenAI Embeddings

## 🛠️ Development

### Project Structure

```
grimoire-keeper/
├── apps/
│   ├── api/           # FastAPI backend
│   └── bot/           # Slack bot (future)
├── shared/            # Shared utilities
├── docs/              # Documentation
├── scripts/           # Utility scripts
└── tests/             # Test files
```

### Development Workflow

1. **Environment Setup**
   ```bash
   # Start devcontainer or local environment
   cp .env.example .env
   uv sync
   ```

2. **Code Quality**
   ```bash
   uv run ruff check .      # Linting
   uv run ruff format .     # Formatting
   uv run mypy .            # Type checking
   uv run pytest           # Testing
   ```

3. **Running Services**
   ```bash
   # Infrastructure
   docker-compose up -d weaviate
   
   # Application
   uv run --package grimoire-api uvicorn grimoire_api.main:app --reload
   ```

### Testing

```bash
# Unit tests
uv run pytest apps/api/tests/unit/ -v

# Integration tests
uv run pytest apps/api/tests/integration/ -v

# All tests with coverage
uv run pytest --cov=apps --cov-report=html
```

## 📊 API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/process-url` | Process a URL and extract content |
| `GET` | `/api/v1/search` | Search processed content |
| `GET` | `/api/v1/process-status/{id}` | Check processing status |
| `GET` | `/api/v1/health` | Health check |

### Request/Response Examples

**Process URL**
```json
POST /api/v1/process-url
{
  "url": "https://example.com",
  "memo": "Optional memo"
}

Response:
{
  "status": "processing",
  "page_id": 123,
  "message": "URL processing started"
}
```

**Search**
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

## ⚙️ Configuration

### Environment Variables

```bash
# API Keys
OPENAI_API_KEY=sk-...          # For embeddings
GOOGLE_API_KEY=...             # For Gemini LLM
JINA_API_KEY=...               # For content extraction

# Services
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
DATABASE_PATH=./grimoire.db

# Optional
JSON_STORAGE_PATH=./data/json  # Raw content storage
```

### Docker Compose

The project includes a `docker-compose.yml` for running Weaviate:

```bash
docker-compose up -d weaviate
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Add type hints to all functions
- Write tests for new features
- Update documentation as needed
- Use conventional commit messages

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Jina AI Reader](https://jina.ai/) for content extraction
- [Weaviate](https://weaviate.io/) for vector search
- [Google Gemini](https://ai.google.dev/) for LLM processing
- [OpenAI](https://openai.com/) for embeddings

## 📚 Documentation

For detailed documentation, see the [docs/](docs/) directory:

- [Backend Architecture](docs/backend-architecture.md)
- [API Flow](docs/backend-api-flow.md)
- [Processing Pipeline](docs/download-process.md)

## 🐛 Issues & Support

If you encounter any issues or have questions:

1. Check the [documentation](docs/)
2. Search existing [issues](https://github.com/your-org/grimoire-keeper/issues)
3. Create a new issue with detailed information

---

**Made with ❤️ by the Grimoire Keeper Team**