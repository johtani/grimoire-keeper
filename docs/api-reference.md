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

#### `GET /api/v1/health`

Backward-compatible alias for the readiness check. It returns the same response as
`GET /api/v1/health/ready`.

#### `GET /api/v1/health/ready`

Check whether the API is ready to accept requests. Both SQLite and Weaviate must be
available for this endpoint to return `200 OK`.

**200 Response:**

```json
{
  "status": "healthy",
  "message": "Grimoire Keeper API is ready",
  "version": "0.1.0",
  "git_commit": "abc1234",
  "build_date": "2026-04-09T12:00:00Z",
  "database": "ready",
  "weaviate": "ready"
}
```

**503 Response:**

```json
{
  "status": "unhealthy",
  "message": "Weaviate is not available",
  "version": "0.1.0",
  "git_commit": "abc1234",
  "build_date": "2026-04-09T12:00:00Z",
  "database": "ready",
  "weaviate": "unavailable"
}
```

**Status Codes:**

- `200 OK`: SQLite and Weaviate are ready
- `503 Service Unavailable`: SQLite or Weaviate is unavailable

#### `GET /api/v1/health/live`

Check whether the API process can respond to HTTP requests. This endpoint does not
check SQLite or Weaviate.

**200 Response:**

```json
{
  "status": "healthy",
  "message": "Grimoire Keeper API is running",
  "version": "0.1.0",
  "git_commit": "abc1234",
  "build_date": "2026-04-09T12:00:00Z"
}
```

**Status Codes:**

- `200 OK`: The API process is running

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
  "status": "queued",
  "page_id": 123,
  "job_id": 456,
  "message": "URL processing queued"
}
```

**Status Codes:**
- `202 Accepted`: The persistent job was queued successfully
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
- `queued`: Persisted and waiting for the worker
- `processing`: Still being processed
- `completed`: Successfully completed
- `failed`: Processing failed
- `not_found`: Page ID not found

**Status Codes:**
- `200 OK`: Status retrieved successfully
- Unknown IDs are represented by `status: "not_found"` in a `200 OK` response

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/process-status/123"
```

---

### Search

#### `POST /api/v1/search`

Search processed content using vector similarity search.

**Request Body:**
```json
{
  "query": "machine learning",
  "limit": 5
}
```

**Request Body Parameters:**
- `query` (string, required, 1-1000 characters): Search query text; whitespace-only values are rejected
- `limit` (integer, optional, default=5, range=1-100): Maximum number of results
- `filters` (object, optional): Search filters. Supported fields are `url` (1-2048 characters), `keywords` (1-20 strings of 1-100 characters), `date_from`, and `date_to`. Unknown fields and reversed date ranges are rejected
- `vector_name` (string, optional, default="content_vector"): Named vector to
  search against. `content_vector` searches body chunks in
  `GrimoireContentChunk`; `title_vector` and `memo_vector` search one
  representative object per page in `GrimoirePage`.
- `exclude_keywords` (array of strings, optional): 1-20 keywords of 1-100 characters to exclude from results

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
  "query": "machine learning"
}
```

For page-level searches (`title_vector` and `memo_vector`), `chunk_id` is `0`
and `content` is an empty string. Body searches continue to return the matching
chunk ID and content. Page-level metadata in body results is loaded from SQLite,
which is the source of truth.

**Status Codes:**
- `200 OK`: Search completed successfully
- `500 Internal Server Error`: Search error

**Examples:**

Vector search:
```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "limit": 10}'
```

Search with title vector:
```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "AI introduction", "vector_name": "title_vector", "limit": 5}'
```

Search with keyword exclusion:
```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "python", "limit": 10, "exclude_keywords": ["tutorial", "beginner"]}'
```

---

#### `POST /api/v1/search/keywords`

Search processed content by matching against stored keywords.

**Request Body:**
```json
["machine learning", "AI", "neural networks"]
```

**Query Parameters:**
- `limit` (integer, optional, default=5): Maximum number of results

**Response:** Same format as `POST /api/v1/search`

**Status Codes:**
- `200 OK`: Search completed successfully
- `500 Internal Server Error`: Search error

**Examples:**
```bash
curl -X POST "http://localhost:8000/api/v1/search/keywords?limit=10" \
  -H "Content-Type: application/json" \
  -d '["machine learning", "AI"]'
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
  "error_message": "Jina API HTTP error 404"
}
```

External service response bodies are not included in error messages or logs because
they may contain page content or other sensitive data.

**Status Codes:**
- `200 OK`: Page found and returned
- `404 Not Found`: Page not found

**Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/pages/123"
```

---

### Repair Management

Repair cases identify stored pages that need manual correction or reprocessing.
Cases have a `pending` or `resolved` status.

#### `GET /api/v1/repairs`

List repair cases, filtered by repair status.

**Query Parameters:**

- `status` (string, optional, default=`pending`): `pending`, `resolved`, or `all`

**Response:**

```json
{
  "repairs": [
    {
      "page_id": 56,
      "url": "https://example.com/article",
      "report_url": null,
      "source": "scan",
      "reasons": [
        {
          "code": "missing_json",
          "detail": "Stored source JSON is missing for page 56"
        }
      ],
      "repair_status": "pending",
      "detected_at": "2026-04-09T12:00:00Z",
      "resolved_at": null
    }
  ],
  "total": 1
}
```

**Status Codes:**

- `200 OK`: Repair cases returned
- `422 Unprocessable Entity`: `status` is not `pending`, `resolved`, or `all`

**Validation Error Example:**

```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["query", "status"],
      "msg": "String should match pattern '^(pending|resolved|all)$'",
      "input": "invalid"
    }
  ]
}
```

#### `POST /api/v1/repairs/import`

Import migration repair cases from `REPAIR_REPORT_PATH` (default:
`./data/migration/repair-pending.json`). This endpoint has no request body.
Existing resolved cases are not reopened by an imported report.

**Response:**

```json
{
  "imported": 3,
  "missing_pages": 1,
  "url_mismatches": 1
}
```

**Status Codes:**

- `200 OK`: Report processed
- `404 Not Found`: Report file does not exist
- `422 Unprocessable Entity`: Report JSON or schema is invalid

**Error Example:**

```json
{
  "detail": "Repair report not found: data/migration/repair-pending.json"
}
```

#### `POST /api/v1/repairs/scan`

Scan all stored pages and create or update `pending` repair cases for pages whose
cached source JSON is missing, invalid, or inconsistent. This endpoint has no
request body.

**Response:**

```json
{
  "scanned": 120,
  "pending": 2,
  "resolved": 0
}
```

**Status Codes:**

- `200 OK`: Scan completed
- `500 Internal Server Error`: Scan failed

#### `GET /api/v1/pages/{page_id}/repair`

Get the repair case, current JSON validation result, latest processing error and
job, and Weaviate registration state for a page. `weaviate_registered` is `null`
when Weaviate is unavailable.

**Parameters:**

- `page_id` (integer, required, greater than zero): Page ID

**Response:**

```json
{
  "page_id": 56,
  "url": "https://example.com/article",
  "repair_status": "pending",
  "reasons": [
    {
      "code": "url_mismatch",
      "detail": "Stored URL does not match the page URL"
    }
  ],
  "json_validation": {
    "valid": false,
    "reasons": [
      {
        "code": "url_mismatch",
        "detail": "Stored URL does not match the page URL"
      }
    ]
  },
  "latest_error": "Jina API HTTP error 404",
  "latest_job": {
    "id": 91,
    "status": "failed",
    "start_step": "download",
    "current_step": null,
    "error_message": "Jina API HTTP error 404"
  },
  "weaviate_registered": false
}
```

`repair_status`, `latest_error`, and `latest_job` can be `null` when no matching
record exists. A latest job has status `queued`, `running`, `succeeded`, or
`failed`; `start_step` is `download`, `llm`, or `vectorize`.

**Status Codes:**

- `200 OK`: Repair details returned
- `404 Not Found`: Page does not exist
- `422 Unprocessable Entity`: `page_id` is not a positive integer

**Error Example:**

```json
{
  "error": {
    "code": "not_found",
    "message": "Page not found"
  }
}
```

#### `PATCH /api/v1/pages/{page_id}/url`

Correct a page URL using optimistic locking. `current_url` must match the value
currently stored for the page. A successful update marks the page as `failed`,
creates or updates a `pending` repair case, and requires the page to be
reprocessed.

**Parameters:**

- `page_id` (integer, required, greater than zero): Page ID

**Request Body:**

```json
{
  "current_url": "https://example.com/article%3E",
  "new_url": "https://example.com/article"
}
```

**Response:**

```json
{
  "current_url": "https://example.com/article%3E",
  "new_url": "https://example.com/article",
  "status": "failed"
}
```

**Status Codes:**

- `200 OK`: URL updated and page marked for repair
- `404 Not Found`: Page does not exist
- `409 Conflict`: `current_url` is stale or `new_url` belongs to another page
- `422 Unprocessable Entity`: Path or request body validation failed

**Conflict Error Example:**

```json
{
  "error": {
    "code": "conflict",
    "message": "Current URL does not match"
  }
}
```

**Validation Error Example:**

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [
      {
        "location": ["body", "new_url"],
        "message": "Value error, URL must not end with '>' or '%3E'",
        "type": "value_error"
      }
    ]
  }
}
```

#### Repair State Transitions

1. A report import, integrity scan, or manual URL correction creates or updates a
   `pending` repair case.
2. An imported report does not reopen a case that is already `resolved`. A later
   scan or manual URL correction can reopen it when a current problem is found.
3. Correct the underlying problem, then enqueue retry or reprocessing through the
   corresponding processing API.
4. After a job succeeds, the worker verifies the cached JSON and Weaviate object.
   If both are valid, it changes the repair case from `pending` to `resolved` and
   records `resolved_at`.
5. Use `GET /api/v1/repairs?status=resolved` to audit resolved cases, or delete a
   page while its repair case is still `pending` with the deletion API below.

---

### Delete Pending Repair Page

#### `DELETE /api/v1/pages/{page_id}`

Permanently delete a page only when it has a `pending` repair case and no
`queued` or `running` job. This removes its page and chunk objects from
Weaviate, `data/json/{page_id}.json`, and the `pages`, `process_logs`, `jobs`,
and `repair_cases` SQLite rows.

Missing JSON files and Weaviate objects are treated as already deleted. If an
external or database deletion fails, the page and repair case remain and a
failure is recorded in `process_logs`; retry the same request to finish cleanup.

**Response:**
```json
{
  "page_id": 123,
  "url": "https://example.com/unneeded",
  "status": "deleted"
}
```

**Status Codes:**
- `200 OK`: Page and related data deleted
- `404 Not Found`: Page does not exist
- `409 Conflict`: Repair case is missing/resolved, or an active job exists
- `500 Internal Server Error`: Partial deletion failed and may be retried
- `503 Service Unavailable`: Weaviate is unavailable

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
  "job_id": 457,
  "restart_from": "llm",
  "message": "Retry processing started from llm step"
}
```

**Restart Points:**
- `download`: Start from content extraction (Jina AI)
- `llm`: Start from summary/keywords generation
- `vectorize`: Start from vector storage (Weaviate)

**Status Codes:**
- `202 Accepted`: Retry job queued successfully
- `500 Internal Server Error`: Page lookup or job registration error

**Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/retry/123"
```

---

#### `POST /api/v1/reprocess/{page_id}`

Queue reprocessing for any existing page, including a successfully completed page.

**Request Body (Optional):**
```json
{
  "from_step": "auto"
}
```

`from_step` accepts only `auto`, `download`, `llm`, or `vectorize`. `auto` selects
the restart point from `last_success_step`. Any other value returns
`422 Unprocessable Entity` and no job is created.

**Response:**
```json
{
  "status": "reprocess_started",
  "page_id": 123,
  "job_id": 458,
  "restart_from": "vectorize",
  "message": "Reprocessing started from vectorize step"
}
```

**Status Codes:**
- `202 Accepted`: Reprocessing job queued successfully
- `422 Unprocessable Entity`: Unknown `from_step`
- `500 Internal Server Error`: Page lookup or job registration error

---

#### `POST /api/v1/retry-failed`

Retry processing for all pages with failed status.

**Request Body (Optional):**
```json
{
  "max_retries": 10
}
```

**Parameters:**
- `max_retries` (integer, optional, default=unlimited, range=1-1000): Maximum number of pages to retry

The unused `delay_seconds` field has been removed. Requests containing it are rejected with `422 Unprocessable Entity`.

**Response:**
```json
{
  "status": "batch_retry_started",
  "total_failed_pages": 5,
  "retry_count": 5,
  "job_ids": [460, 461, 462, 463, 464],
  "message": "Batch retry started for 5 failed pages"
}
```

**Status Codes:**
- `202 Accepted`: Retry jobs queued successfully
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Batch retry initiation error

**Example:**
```bash
# Retry all failed pages
curl -X POST "http://localhost:8000/api/v1/retry-failed"

# Retry with limits
curl -X POST "http://localhost:8000/api/v1/retry-failed" \
  -H "Content-Type: application/json" \
  -d '{"max_retries": 10}'
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
---

## Retry Processing / リトライ処理

URL 処理がいずれかのステージで失敗した場合、システムは失敗を記録し、最後に成功したステップからインテリジェントなリトライを可能にします。

`pages.status` がページの現在状態の正本です。`process_logs` は監査履歴として保持されますが、
過去の失敗ログだけを理由に失敗一覧や一括リトライの対象にはなりません。ジョブは SQLite の
`jobs` テーブルへ永続化され、API 起動時に `queued` ジョブを再開し、中断された `running`
ジョブを `queued` に戻します。同一ページに `queued` または `running` のジョブを複数登録する
ことはできません。

### 処理ステージ

| ステージ | `last_success_step` 値 | 説明 |
|---------|----------------------|------|
| コンテンツ取得 | `downloaded` | Jina AI Reader でページを取得 |
| LLM 処理 | `llm_processed` | 要約とキーワードを生成 |
| ベクトル化 | `vectorized` | Weaviate にベクトルを保存 |
| 完了 | `completed` | 全処理完了 |

### スマートリスタートロジック

リトライ時は `last_success_step` に基づいて再開ポイントを決定します:

| 最後の成功ステップ | 再開位置 |
|------------------|---------|
| `NULL` または空 | コンテンツ取得から |
| `downloaded` | LLM 処理から (取得をスキップ) |
| `llm_processed` | ベクトル化から (取得・LLM をスキップ) |
| `vectorized` | ベクトル化から再実行 |
| `completed` | リトライ不要 |

### リトライ API

**個別リトライ:**
```bash
curl -X POST "http://localhost:8000/api/v1/retry/123"
```

**一括リトライ (失敗した全ページ):**
```bash
curl -X POST "http://localhost:8000/api/v1/retry-failed"
```

**失敗ページ一覧:**
```bash
curl -X GET "http://localhost:8000/api/v1/pages?status=failed"
```
