# Development Guide

This guide covers the development setup, workflow, and best practices for contributing to Grimoire Keeper.

## Prerequisites

- **Python 3.13+**: Required for all components
- **Docker & Docker Compose**: For running Weaviate
- **uv**: Python package manager (recommended)
- **Git**: Version control

### API Keys Required

- **OpenAI API Key**: For embeddings (`text-embedding-ada-002`)
- **Google API Key**: For Gemini LLM (`gemini-2.5-flash-lite`)
- **Jina AI API Key**: For content extraction
- **Bitwarden Secrets Manager Access Token**: For secret management (`BWS_ACCESS_TOKEN`)

## Quick Setup

### 1. Clone and Setup Environment

```bash
# Clone repository
git clone https://github.com/your-org/grimoire-keeper.git
cd grimoire-keeper

# Copy environment template
cp .env.example .env

# Edit .env with non-secret settings (WEAVIATE_HOST, DATABASE_PATH, etc.)
nano .env
```

### 1a. Setup Bitwarden Secrets Manager

APIキーなどの秘密情報はBitwarden Secrets Managerで管理します。

1. [Bitwarden Secrets Manager](https://bitwarden.com/products/secrets-manager/) でプロジェクト `grimoire-keeper` を作成
2. 以下のシークレットを登録（名前は `GRIMOIRE_KEEPER_` プレフィックス付きで登録）:
   - `GRIMOIRE_KEEPER_OPENAI_API_KEY`
   - `GRIMOIRE_KEEPER_GOOGLE_API_KEY`
   - `GRIMOIRE_KEEPER_JINA_API_KEY`
   - `GRIMOIRE_KEEPER_SLACK_BOT_TOKEN`
   - `GRIMOIRE_KEEPER_SLACK_SIGNING_SECRET`
   - `GRIMOIRE_KEEPER_SLACK_APP_TOKEN`
3. マシンアカウントを作成してアクセストークンを発行
4. 発行したトークンを環境変数に設定:
   ```bash
   export BWS_ACCESS_TOKEN=your-access-token
   # または .env に追記
   echo 'BWS_ACCESS_TOKEN=your-access-token' >> .env
   ```

### 2. Install Dependencies

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

### 3. Start Services

```bash
# Load secrets from Bitwarden Secrets Manager
source scripts/load_secrets.sh

# Start Weaviate
docker-compose up -d weaviate

# Initialize database
python scripts/init_database.py init

# Start API server
uv run --package grimoire-api uvicorn grimoire_api.main:app --reload
```

### 4. Verify Setup

```bash
# Check API health
curl http://localhost:8000/health

# Test URL processing
curl -X POST "http://localhost:8000/api/v1/process-url" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "memo": "Test"}'
```

## Development Workflow

### Project Structure

```
grimoire-keeper/
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── src/grimoire_api/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── bot/                 # Slack bot (future)
├── shared/                  # Shared utilities
├── docs/                    # Documentation
├── scripts/                 # Utility scripts
├── .devcontainer/          # Dev container config
├── docker-compose.yml      # Services configuration
└── pyproject.toml          # Workspace configuration
```

### Development Commands

```bash
# Code quality checks
uv run ruff check .          # Linting
uv run ruff format .         # Code formatting
uv run mypy .                # Type checking

# Testing
uv run pytest               # All tests
uv run pytest apps/api/tests/unit/     # Unit tests only
uv run pytest apps/api/tests/integration/  # Integration tests only
uv run pytest --cov=apps --cov-report=html  # With coverage

# Database operations
python scripts/init_database.py init    # Initialize database
python scripts/db_cli.py               # Database CLI tool
```

### Secret Management Scripts

| Script | 使うタイミング | 使い方 |
|--------|------------|--------|
| `scripts/load_secrets.sh` | 開発環境でアプリを手動起動する前 | `source scripts/load_secrets.sh` |
| `scripts/start.sh` | サーバで本番起動するとき | `bash scripts/start.sh -d` |

`load_secrets.sh` は単体では使わず、`source` で呼び出すことで現在のシェルセッションに環境変数を展開します。`start.sh` は内部で `load_secrets.sh` を呼び出した後に `docker compose up` を実行します。

### Running Services

#### Recommended: Mixed Execution
- **Infrastructure**: Docker containers
- **Application**: Local development server

```bash
# Start infrastructure
docker-compose up -d weaviate

# Start API (with hot reload)
uv run --package grimoire-api uvicorn grimoire_api.main:app --reload --host 0.0.0.0 --port 8000
```

#### Alternative: Full Docker
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api
```

## Code Quality Standards

### Linting and Formatting

We use **ruff** for both linting and formatting:

```bash
# Check for issues
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check . --fix

# Format code
uv run ruff format .
```

### Type Checking

All code must include type hints and pass mypy checks:

```bash
# Run type checker
uv run mypy .

# Check specific file
uv run mypy apps/api/src/grimoire_api/services/llm_service.py
```

### Testing Requirements

- **Unit tests**: Required for all new functions/classes
- **Integration tests**: Required for API endpoints
- **Coverage**: Aim for >80% code coverage

```bash
# Run tests with coverage
uv run pytest --cov=apps --cov-report=term-missing

# Run specific test file
uv run pytest apps/api/tests/unit/services/test_llm_service.py -v

# Run tests matching pattern
uv run pytest -k "test_process_url" -v
```

## Development Environment Options

### Option 1: Dev Container (Recommended)

Use the provided dev container for consistent environment:

```bash
# Open in VS Code with dev container extension
code .

# Or use GitHub Codespaces
```

The dev container includes:
- Python 3.13
- All required tools (uv, ruff, mypy, pytest)
- VS Code extensions
- Docker-in-Docker for services

### Option 2: Local Development

Install tools locally:

```bash
# Install Python 3.13
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project
uv sync

# Install pre-commit hooks (optional)
uv run pre-commit install
```

## Configuration

### Secret Management

APIキーなどの秘密情報はBitwarden Secrets Managerで管理します。各環境で `BWS_ACCESS_TOKEN` のみを設定すれば、起動スクリプトが自動的にシークレットを取得して環境変数に展開します。

```
秘密情報 (Bitwarden Secrets Manager)
  GRIMOIRE_KEEPER_OPENAI_API_KEY
  GRIMOIRE_KEEPER_GOOGLE_API_KEY
  GRIMOIRE_KEEPER_JINA_API_KEY
  GRIMOIRE_KEEPER_SLACK_BOT_TOKEN
  GRIMOIRE_KEEPER_SLACK_SIGNING_SECRET
  GRIMOIRE_KEEPER_SLACK_APP_TOKEN

設定値 (.env)
  BWS_ACCESS_TOKEN=...
  WEAVIATE_HOST=localhost
  WEAVIATE_PORT=8080
  DATABASE_PATH=./grimoire.db
  BACKEND_API_URL=http://api:8000
  OTEL_*=...
```

### Environment Variables (.env)

`.env` には秘密でない設定値のみを記載します:

```bash
# Bitwarden Secrets Manager
BWS_ACCESS_TOKEN=your-access-token

# Services
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
DATABASE_PATH=./grimoire.db
BACKEND_API_URL=http://api:8000
```

### Development vs Production

```bash
# Development
DATABASE_PATH=./dev_grimoire.db
WEAVIATE_HOST=localhost

# Production
DATABASE_PATH=/data/grimoire.db
WEAVIATE_HOST=weaviate
```

## Debugging

### API Debugging

```bash
# Start with debug logging
LOG_LEVEL=DEBUG uv run --package grimoire-api uvicorn grimoire_api.main:app --reload

# Use debugger in VS Code
# Set breakpoints and use F5 to start debugging
```

### Database Debugging

```bash
# Use database CLI
python scripts/db_cli.py

# Direct SQLite access
sqlite3 grimoire.db
.tables
SELECT * FROM pages LIMIT 5;
```

### Weaviate Debugging

```bash
# Check Weaviate status
curl http://localhost:8080/v1/meta

# Browse data
curl http://localhost:8080/v1/objects?class=GrimoireChunk&limit=5
```

## Adding New Features

### 1. Create Feature Branch

```bash
git checkout -b feature/new-feature-name
```

### 2. Implement Feature

Follow the existing patterns:

```python
# Add service in apps/api/src/grimoire_api/services/
class NewService:
    async def new_method(self) -> dict:
        """New functionality."""
        pass

# Add repository if needed
class NewRepository:
    async def create_item(self, data: dict) -> int:
        """Data access method."""
        pass

# Add API endpoint in apps/api/src/grimoire_api/routers/
@router.post("/new-endpoint")
async def new_endpoint(request: NewRequest) -> NewResponse:
    """New API endpoint."""
    pass
```

### 3. Add Tests

```python
# Unit test
class TestNewService:
    async def test_new_method(self):
        service = NewService()
        result = await service.new_method()
        assert result["status"] == "success"

# Integration test
class TestNewEndpoint:
    def test_new_endpoint(self, client):
        response = client.post("/new-endpoint", json={...})
        assert response.status_code == 200
```

### 4. Update Documentation

- Update API reference if adding endpoints
- Update architecture docs if changing structure
- Add docstrings to all new functions

### 5. Submit Pull Request

```bash
# Run all checks
uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest

# Commit and push
git add .
git commit -m "feat: add new feature"
git push origin feature/new-feature-name
```

## Common Development Tasks

### Adding a New API Endpoint

1. **Define models** in `models/request.py` and `models/response.py`
2. **Implement service** in `services/`
3. **Add repository methods** if needed in `repositories/`
4. **Create router** in `routers/`
5. **Register router** in `main.py`
6. **Add tests** in `tests/`

### Adding External Service Integration

1. **Create client class** in `services/`
2. **Add configuration** in `config.py`
3. **Handle errors** with custom exceptions
4. **Add health check** integration
5. **Mock in tests** for reliability

### Database Schema Changes

1. **Update SQL** in `scripts/init_database.py`
2. **Update models** in `models/database.py`
3. **Update repositories** with new methods
4. **Add migration script** if needed
5. **Update tests** with new schema

## Troubleshooting

### Common Issues

**Import errors:**
```bash
# Ensure you're in the right environment
uv run python -c "import grimoire_api; print('OK')"
```

**Database locked:**
```bash
# Stop all processes using the database
pkill -f grimoire
rm grimoire.db-wal grimoire.db-shm  # Remove WAL files
```

**Weaviate connection errors:**
```bash
# Check if Weaviate is running
docker-compose ps weaviate
curl http://localhost:8080/v1/meta
```

**API key errors:**
```bash
# Verify environment variables
python -c "from grimoire_api.config import settings; print(settings.OPENAI_API_KEY[:10])"
```

### Getting Help

1. Check the [troubleshooting guide](troubleshooting.md)
2. Review existing [issues](https://github.com/your-org/grimoire-keeper/issues)
3. Create a new issue with:
   - Error message
   - Steps to reproduce
   - Environment details
   - Relevant logs

## Performance Considerations

### Development Performance

- Use `--reload` only in development
- Consider using `pytest-xdist` for parallel testing
- Use database transactions for bulk operations
- Profile slow operations with `cProfile`

### Resource Usage

- Monitor memory usage during development
- Use appropriate chunk sizes for large documents
- Implement pagination for large result sets
- Consider caching for frequently accessed data

---

Happy coding! 🚀