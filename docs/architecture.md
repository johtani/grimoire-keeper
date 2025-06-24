# Architecture Overview

## System Architecture

Grimoire Keeper follows a modular, service-oriented architecture designed for scalability and maintainability.

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
                           │
                           ▼
                   ┌─────────────┐
                   │ File System │
                   │ (JSON Data) │
                   └─────────────┘
```

## Core Components

### 1. FastAPI Backend (`apps/api/`)

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
- **Schema**: `GrimoireChunk` collection
- **Benefits**: Scalable vector search, metadata filtering

### 3. External Services Integration

#### Jina AI Reader
- **Purpose**: Web content extraction
- **Output**: Structured markdown content
- **Features**: Image summarization, clean text extraction

#### Google Gemini (via LiteLLM)
- **Purpose**: Content summarization and keyword extraction
- **Model**: `gemini-1.5-flash`
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
    
    async def vector_search(self, query: str, filters: dict = None):
        # Semantic search with optional filtering
    
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

## Data Flow

### 1. URL Processing Pipeline
```
URL Input → Jina AI Reader → Content Extraction
    ↓
SQLite Storage ← JSON File Storage
    ↓
Gemini LLM → Summary/Keywords Generation
    ↓
Weaviate → Vector Storage + Chunking
    ↓
Completion Status Update
```

### 2. Search Pipeline
```
Search Query → Weaviate Vector Search
    ↓
Result Ranking → Metadata Enrichment
    ↓
Response Formatting → Client Response
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
- **Vector Search**: Purpose-built for semantic search
- **Scalability**: Horizontal scaling capabilities
- **Integration**: Native OpenAI embeddings support
- **Flexibility**: Rich query capabilities and filtering

This architecture provides a solid foundation for the current requirements while maintaining flexibility for future enhancements and scaling needs.