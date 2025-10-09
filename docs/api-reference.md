# API Reference

Complete reference for the Grimoire Keeper REST API.

## Base URL

```
http://localhost:8000
```

## Authentication

Currently, no authentication is required. API keys for external services are configured server-side.

## Endpoints

### Health Check

#### `GET /health`

Check the health status of the API and its dependencies.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-01T12:00:00Z",
  "services": {
    "database": "healthy",
    "weaviate": "healthy",
    "jina_ai": "healthy"
  }
}
```

**Status Codes:**
- `200 OK`: All services are healthy
- `503 Service Unavailable`: One or more services are unhealthy

---

### URL Processing

#### `POST /api/v1/process-url`

Process a URL to extract content, generate summary/keywords, and store in vector database.

**Request Body:**
```json
{
  "url": "https://example.com/article",
  "memo": "Optional user memo about this URL"
}
```

**Parameters:**
- `url` (string, required): Valid HTTP/HTTPS URL to process
- `memo` (string, optional): User-provided memo or note

**Response:**
```json
{
  "status": "processing",
  "page_id": 123,
  "message": "URL processing started"
}
```

**Status Codes:**
- `200 OK`: Processing started successfully
- `400 Bad Request`: Invalid URL format
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Processing error

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/process-url" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "memo": "Interesting ML article"
  }'
```

---

### Processing Status

#### `GET /api/v1/process-status/{page_id}`

Check the processing status of a specific URL.

**Parameters:**
- `page_id` (integer, required): Page ID returned from process-url

**Response:**
```json
{
  "status": "completed",
  "message": "Processing completed successfully",
  "page": {
    "id": 123,
    "url": "https://example.com/article",
    "title": "Machine Learning Basics",
    "memo": "Interesting ML article",
    "summary": "This article covers the fundamentals of machine learning...",
    "keywords": ["machine learning", "AI", "algorithms", "data science"],
    "created_at": "2025-01-01T12:00:00Z"
  }
}
```

**Status Values:**
- `processing`: Still being processed
- `completed`: Successfully completed
- `failed`: Processing failed
- `not_found`: Page ID not found

**Status Codes:**
- `200 OK`: Status retrieved successfully
- `404 Not Found`: Page ID not found

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/process-status/123"
```

---

### Search

#### `POST /api/v1/search`

Search processed content using vector similarity or keyword matching.

**Query Parameters:**
- `query` (string, required): Search query text
- `limit` (integer, optional, default=5): Maximum number of results
- `search_type` (string, optional, default="vector"): Search type ("vector" or "keyword")
- `url_filter` (string, optional): Filter by URL substring
- `keywords_filter` (array, optional): Filter by specific keywords
- `date_from` (string, optional): Filter by date range (ISO format)
- `date_to` (string, optional): Filter by date range (ISO format)

**Response:**
```json
{
  "results": [
    {
      "page_id": 123,
      "chunk_id": 0,
      "url": "https://example.com/article",
      "title": "Machine Learning Basics",
      "memo": "Interesting ML article",
      "content": "Machine learning is a subset of artificial intelligence...",
      "summary": "This article covers the fundamentals of machine learning...",
      "keywords": ["machine learning", "AI", "algorithms"],
      "created_at": "2025-01-01T12:00:00Z",
      "score": 0.95
    }
  ],
  "total": 1,
  "query": "machine learning",
  "search_type": "vector"
}
```

**Status Codes:**
- `200 OK`: Search completed successfully
- `400 Bad Request`: Invalid query parameters
- `500 Internal Server Error`: Search error

**Examples:**

Vector search:
```bash
curl -X GET "http://localhost:8000/api/v1/search?query=machine%20learning&limit=10"
```

Keyword search:
```bash
curl -X GET "http://localhost:8000/api/v1/search?query=AI&search_type=keyword&limit=5"
```

Filtered search:
```bash
curl -X GET "http://localhost:8000/api/v1/search?query=python&url_filter=github.com&date_from=2024-01-01"
```

---

### Page Details

#### `GET /api/v1/pages/{page_id}`

Get detailed information about a specific page, including error details for failed pages.

**Parameters:**
- `page_id` (integer, required): Page ID

**Response:**
```json
{
  "id": 123,
  "url": "https://example.com/article",
  "title": "Machine Learning Basics",
  "memo": "Interesting ML article",
  "summary": "This article covers the fundamentals of machine learning...",
  "keywords": ["machine learning", "AI", "algorithms", "data science"],
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-01T12:05:00Z",
  "weaviate_id": "uuid-string",
  "error_message": null
}
```

**For Failed Pages:**
```json
{
  "id": 124,
  "url": "https://example.com/failed-article",
  "title": "Processing...",
  "memo": "Test article",
  "summary": null,
  "keywords": [],
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-01T12:05:00Z",
  "weaviate_id": null,
  "error_message": "Failed to extract content: HTTP 404 Not Found"
}
```

**Status Codes:**
- `200 OK`: Page found and returned
- `404 Not Found`: Page not found

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/pages/123"
```

---

### List Pages

#### `GET /api/v1/pages`

List all processed pages with pagination and status filtering.

**Query Parameters:**
- `limit` (integer, optional, default=20): Number of pages per request
- `offset` (integer, optional, default=0): Number of pages to skip
- `sort` (string, optional, default="created_at"): Sort field
- `order` (string, optional, default="desc"): Sort order ("asc" or "desc")
- `status` (string, optional, default="all"): Filter by processing status

**Status Filter Values:**
- `all`: Show all pages
- `completed`: Show only successfully processed pages
- `processing`: Show pages currently being processed
- `failed`: Show pages that failed processing

**Response:**
```json
{
  "pages": [
    {
      "id": 123,
      "url": "https://example.com/article",
      "title": "Machine Learning Basics",
      "memo": "Interesting ML article",
      "summary": "This article covers the fundamentals...",
      "keywords": ["machine learning", "AI"],
      "status": "completed",
      "created_at": "2025-01-01T12:00:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0,
  "status_filter": "all"
}
```

**Status Codes:**
- `200 OK`: Pages retrieved successfully

**Examples:**
```bash
# List all pages
curl -X GET "http://localhost:8000/api/v1/pages?limit=10&offset=0&sort=title&order=asc"

# List only failed pages
curl -X GET "http://localhost:8000/api/v1/pages?status=failed"

# List completed pages
curl -X GET "http://localhost:8000/api/v1/pages?status=completed&limit=50"
```

---

### Retry Processing

#### `POST /api/v1/retry/{page_id}`

Retry processing for a specific failed page, resuming from the last successful step.

**Parameters:**
- `page_id` (integer, required): Page ID to retry

**Response:**
```json
{
  "status": "retry_started",
  "page_id": 123,
  "restart_from": "llm_processing",
  "message": "Retry processing started from LLM step"
}
```

**Restart Points:**
- `download`: Start from content extraction (Jina AI)
- `llm_processing`: Start from summary/keywords generation (Gemini)
- `vectorization`: Start from vector storage (Weaviate)
- `already_completed`: Page is already successfully processed

**Status Codes:**
- `200 OK`: Retry started successfully
- `404 Not Found`: Page not found
- `400 Bad Request`: Page is not in failed state
- `500 Internal Server Error`: Retry initiation error

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/retry/123"
```

---

#### `POST /api/v1/retry-failed`

Retry processing for all pages with failed status.

**Request Body (Optional):**
```json
{
  "max_retries": 10,
  "delay_seconds": 5
}
```

**Parameters:**
- `max_retries` (integer, optional, default=unlimited): Maximum number of pages to retry
- `delay_seconds` (integer, optional, default=1): Delay between retry attempts

**Response:**
```json
{
  "status": "batch_retry_started",
  "total_failed_pages": 5,
  "retry_count": 5,
  "message": "Batch retry started for 5 failed pages"
}
```

**Status Codes:**
- `200 OK`: Batch retry started successfully
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Batch retry initiation error

**Example:**
```bash
# Retry all failed pages
curl -X POST "http://localhost:8000/api/v1/retry-failed"

# Retry with limits
curl -X POST "http://localhost:8000/api/v1/retry-failed" \
  -H "Content-Type: application/json" \
  -d '{"max_retries": 10, "delay_seconds": 2}'
```

---

## Error Responses

All endpoints return consistent error responses:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid URL format",
    "details": {
      "field": "url",
      "value": "invalid-url"
    }
  }
}
```

### Common Error Codes

- `VALIDATION_ERROR`: Request validation failed
- `NOT_FOUND`: Resource not found
- `PROCESSING_ERROR`: Internal processing error
- `EXTERNAL_SERVICE_ERROR`: External API error
- `DATABASE_ERROR`: Database operation error

## Rate Limiting

Currently, no rate limiting is implemented. Consider implementing rate limiting for production use.

## OpenAPI Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## SDK and Client Libraries

Currently, no official SDKs are available. The API follows REST conventions and can be used with any HTTP client library.

### Python Example

```python
import requests

# Process URL
response = requests.post(
    "http://localhost:8000/api/v1/process-url",
    json={"url": "https://example.com", "memo": "Test"}
)
page_id = response.json()["page_id"]

# Check status
status_response = requests.get(
    f"http://localhost:8000/api/v1/process-status/{page_id}"
)

# Search
search_response = requests.get(
    "http://localhost:8000/api/v1/search",
    params={"query": "machine learning", "limit": 5}
)
```

### JavaScript Example

```javascript
// Process URL
const processResponse = await fetch('http://localhost:8000/api/v1/process-url', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ url: 'https://example.com', memo: 'Test' })
});
const { page_id } = await processResponse.json();

// Search
const searchResponse = await fetch(
  `http://localhost:8000/api/v1/search?query=machine%20learning&limit=5`
);
const searchResults = await searchResponse.json();

// Retry failed page
const retryResponse = await fetch(`http://localhost:8000/api/v1/retry/${page_id}`, {
  method: 'POST'
});
const retryResult = await retryResponse.json();

// List failed pages
const failedPagesResponse = await fetch(
  'http://localhost:8000/api/v1/pages?status=failed'
);
const failedPages = await failedPagesResponse.json();
```