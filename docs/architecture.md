# Architecture Overview

## System Architecture

Grimoire Keeper follows a modular, service-oriented architecture designed for scalability and maintainability.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Web UI     │───▶│  FastAPI    │───▶│  Weaviate   │
│ (Static)    │    │     API     │    │ (Vector DB) │
└─────────────┘    └─────────────┘    └─────────────┘
       │                   │
       │                   ▼
       │           ┌─────────────┐
       │           │   SQLite    │
       │           │ (Metadata)  │
       │           └─────────────┘
       │                   │
       │                   ▼
       │           ┌─────────────┐
       │           │ File System │
       │           │ (JSON Data) │
       │           └─────────────┘
       │
       ▼
┌─────────────┐
│ Slack Bot   │
│ (Optional)  │
└─────────────┘
```

## Core Components

### 1. Web UI (`apps/web/`)

Static HTML/CSS/JavaScript frontend providing search and management interfaces.

**Key Features:**
- Vector search with configurable target vectors
- Advanced filtering (date range, URL, keywords)
- Page management and status monitoring
- Real-time API integration

**Components:**
```
apps/web/static/
├── index.html           # Search interface
├── pages.html           # Page management
├── css/
│   └── style.css        # Styling
└── js/
    ├── search.js        # Search functionality
    ├── pages.js         # Page management
    └── api.js           # API client
```

### 2. FastAPI Backend (`apps/api/`)

The main application server providing RESTful APIs for URL processing and search functionality.

**Key Features:**
- Asynchronous request handling
- Automatic API documentation (OpenAPI/Swagger)
- Pydantic data validation
- Comprehensive error handling

**Directory Structure:**
```
apps/api/src/grimoire_api/
├── main.py              # FastAPI application
├── config.py            # Configuration management
├── models/              # Data models
├── services/            # Business logic
├── repositories/        # Data access layer
├── utils/               # Utilities
└── routers/             # API endpoints
    ├── search.py        # Search endpoints
    ├── pages.py         # Page management
    └── process.py       # URL processing
```

### 2. Data Storage Layer

#### SQLite Database
- **Purpose**: Metadata storage and processing logs
- **Tables**: `pages`, `process_logs`
- **Benefits**: Lightweight, serverless, ACID compliance

#### File System (JSON)
- **Purpose**: Raw content storage from Jina AI Reader
- **Location**: `data/json/{page_id}.json`
- **Benefits**: Full content preservation, debugging capability

#### Weaviate Vector Database
- **Purpose**: Semantic search and vector storage
- **Schema**: `GrimoireChunk` collection with named vectors
- **Vectors**: `content_vector`, `title_vector`, `memo_vector`
- **Features**: Multi-vector search, summary filtering (`isSummary` flag)
- **Benefits**: Scalable vector search, metadata filtering

### 3. External Services Integration

#### Jina AI Reader
- **Purpose**: Web content extraction
- **Output**: Structured markdown content
- **Features**: Image summarization, clean text extraction

#### Google Gemini (via LiteLLM)
- **Purpose**: Content summarization and keyword extraction
- **Model**: `gemini-2.5-flash-lite`
- **Output**: JSON with summary and 20 keywords

#### OpenAI Embeddings
- **Purpose**: Vector generation for semantic search
- **Integration**: Through Weaviate's `text2vec-openai`
- **Model**: `text-embedding-ada-002`

## Service Layer Architecture

### URL Processing Service
```python
class UrlProcessorService:
    """Orchestrates the complete URL processing pipeline"""
    
    async def process_url(self, url: str, memo: str = None):
        # 1. Create processing log
        # 2. Extract content (Jina AI)
        # 3. Generate summary/keywords (Gemini)
        # 4. Vectorize and store (Weaviate)
        # 5. Update completion status
```

### Search Service
```python
class SearchService:
    """Handles vector and keyword search operations"""
    
    async def vector_search(self, query: str, vector_name: str = "content_vector", filters: dict = None):
        # Multi-vector semantic search with optional filtering
        # Supports content_vector, title_vector, memo_vector
    
    async def keyword_search(self, keywords: list[str]):
        # Exact keyword matching
```

### Repository Pattern
```python
class PageRepository:
    """Data access layer for page metadata"""
    
class LogRepository:
    """Data access layer for processing logs"""
    
class FileRepository:
    """File system operations for JSON storage"""
```

### 3. Slack Bot (`apps/bot/`)

Optional Slack integration for URL processing and search.

**Key Features:**
- URL processing via slash commands
- Search using `title_vector` for relevant results
- Real-time status updates

## User Interfaces

### 1. Web Search Interface
```
┌─────────────────────────────────────┐
│ 🔍 Grimoire Search                  │
├─────────────────────────────────────┤
│ Query: [___________________] [検索]  │
│ Vector: [content_vector ▼]          │
│ Filters:                            │
│   Date: [2024-01-01] ～ [2024-12-31]│
│   URL: [________________]           │
│   Keywords: [___________]           │
├─────────────────────────────────────┤
│ Results with relevance scores       │
└─────────────────────────────────────┘
```

### 2. Page Management Interface
```
┌─────────────────────────────────────┐
│ 📄 Pages Management                 │
├─────────────────────────────────────┤
│ Status filtering and real-time      │
│ processing status monitoring        │
└─────────────────────────────────────┘
```

## Data Flow

### 1. URL Processing Pipeline
```
URL Input → Jina AI Reader → Content Extraction
    ↓
SQLite Storage ← JSON File Storage
    ↓
Gemini LLM → Summary/Keywords Generation
    ↓
Weaviate → Multi-Vector Storage + Chunking
    ↓
Named Vectors (content/title/memo) + Summary Flag
    ↓
Completion Status Update
```

### 2. Web Search Pipeline
```
Web UI → Search Form (Vector Selection + Filters)
    ↓
FastAPI → Multi-Vector Search (content/title/memo)
    ↓
Weaviate → Filtered Results (isSummary for title/memo)
    ↓
Web UI → Formatted Results Display
```

### 3. Slack Bot Pipeline
```
Slack Command → Bot Handler
    ↓
FastAPI → Title Vector Search
    ↓
Slack Response → Formatted Results
```

## Scalability Considerations

### Current Architecture Benefits
- **Stateless API**: Easy horizontal scaling
- **Async Processing**: High concurrency support
- **Modular Design**: Independent component scaling
- **External Services**: Offloaded heavy computation

### Future Scaling Options
- **Database**: Migrate to PostgreSQL for larger datasets
- **Caching**: Add Redis for frequently accessed data
- **Queue System**: Add Celery/RQ for background processing
- **Load Balancing**: Multiple API instances behind load balancer

## Security Architecture

### API Security
- Input validation with Pydantic
- SQL injection prevention through parameterized queries
- Rate limiting (configurable)
- CORS configuration

### Data Security
- API keys stored in environment variables
- No sensitive data in logs
- File system permissions for JSON storage
- Weaviate access control

### External API Security
- Secure API key management
- Request timeout configuration
- Error message sanitization
- Retry logic with exponential backoff

## Error Handling Strategy

### Layered Error Handling
1. **Input Validation**: Pydantic models
2. **Service Layer**: Custom exceptions
3. **Repository Layer**: Database error handling
4. **API Layer**: HTTP status codes and error responses

### Error Recovery
- Graceful degradation for external service failures
- Retry mechanisms for transient errors
- Comprehensive logging for debugging
- Status tracking for long-running operations

## Monitoring and Observability

### Logging Strategy
- Structured logging with JSON format
- Different log levels (DEBUG, INFO, WARNING, ERROR)
- Request/response logging
- Performance metrics logging

### Health Checks
- API health endpoint (`/health`)
- Database connectivity check
- External service availability check
- Weaviate cluster status

### Metrics Collection
- Processing pipeline metrics
- API response times
- Error rates and types
- Resource utilization

## Deployment Architecture

### Container Services
```yaml
services:
  web:           # Static file server (nginx)
    ports: 8001:80
  api:           # FastAPI backend
    ports: 8000:8000
  bot:           # Slack bot (optional)
  weaviate:      # Vector database
    ports: 8089:8080
```

### Service Communication
- **Web UI**: Direct API calls to `http://api:8000`
- **Slack Bot**: API calls to `http://api:8000`
- **API**: Direct Weaviate connection

## Technology Choices Rationale

### Python 3.13
- **Async/await**: Native asynchronous programming
- **Type Hints**: Better code quality and IDE support
- **Rich Ecosystem**: Extensive library support

### FastAPI
- **Performance**: High-performance async framework
- **Documentation**: Automatic API documentation
- **Validation**: Built-in request/response validation
- **Standards**: OpenAPI and JSON Schema compliance

### SQLite
- **Simplicity**: No server setup required
- **Reliability**: ACID compliance and durability
- **Performance**: Fast for read-heavy workloads
- **Portability**: Single file database

### Weaviate
- **Multi-Vector Search**: Named vectors for different content types
- **Advanced Filtering**: Summary flags and metadata filtering
- **Scalability**: Horizontal scaling capabilities
- **Integration**: Native OpenAI embeddings support
- **Flexibility**: Rich query capabilities and filtering

### Static Web UI
- **Simplicity**: No server-side rendering complexity
- **Performance**: Fast loading and minimal resource usage
- **Deployment**: Easy nginx-based static file serving
- **Maintenance**: Minimal backend dependencies for UI

This architecture provides a solid foundation for the current requirements while maintaining flexibility for future enhancements and scaling needs.