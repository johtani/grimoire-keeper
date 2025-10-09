# Retry Processing Guide

This guide explains how to use the retry processing functionality in Grimoire Keeper to handle failed URL processing operations.

## Overview

When URL processing fails at any stage (content extraction, LLM processing, or vectorization), the system tracks the failure and allows for intelligent retry operations that resume from the last successful step.

## Processing Stages

The URL processing pipeline consists of several stages:

1. **Content Extraction** (`downloaded`)
   - Fetch content using Jina AI Reader
   - Save raw content to JSON file
   - Update page title

2. **LLM Processing** (`llm_processed`)
   - Generate summary and keywords using Google Gemini
   - Update page metadata

3. **Vectorization** (`vectorized`)
   - Create vector embeddings using OpenAI
   - Store in Weaviate vector database

4. **Completion** (`completed`)
   - Mark processing as fully complete

## How Retry Works

### Progress Tracking

The system tracks processing progress using the `last_success_step` field in the pages table:

- `NULL`: No processing completed
- `'downloaded'`: Content extraction completed
- `'llm_processed'`: Summary/keywords generation completed  
- `'vectorized'`: Vector storage completed
- `'completed'`: All processing completed

### Smart Restart Logic

When retrying a failed page, the system:

1. Checks the `last_success_step` value
2. Determines the appropriate restart point
3. Resumes processing from that step
4. Updates progress tracking as each step completes

**Restart Decision Matrix:**

| Last Success Step | Restart From | Description |
|-------------------|--------------|-------------|
| `NULL` or empty   | Content Extraction | Start from the beginning |
| `'downloaded'`    | LLM Processing | Skip content extraction |
| `'llm_processed'` | Vectorization | Skip content extraction and LLM |
| `'vectorized'`    | Completion | Only finalize the process |
| `'completed'`     | Already Done | No retry needed |

## Using Retry Functionality

### 1. Individual Page Retry

Retry a specific failed page:

```bash
curl -X POST "http://localhost:8000/api/v1/retry/123"
```

**Response:**
```json
{
  "status": "retry_started",
  "page_id": 123,
  "restart_from": "llm_processing",
  "message": "Retry processing started from LLM step"
}
```

### 2. Batch Retry All Failed Pages

Retry all pages with failed status:

```bash
curl -X POST "http://localhost:8000/api/v1/retry-failed"
```

**With Options:**
```bash
curl -X POST "http://localhost:8000/api/v1/retry-failed" \
  -H "Content-Type: application/json" \
  -d '{
    "max_retries": 10,
    "delay_seconds": 2
  }'
```

**Response:**
```json
{
  "status": "batch_retry_started",
  "total_failed_pages": 5,
  "retry_count": 5,
  "message": "Batch retry started for 5 failed pages"
}
```

### 3. Web UI Integration

The Web UI provides retry functionality through:

- **Individual Retry**: "Retry" button on failed pages in the pages management interface
- **Batch Retry**: "Retry All Failed" button for processing all failed pages at once
- **Status Monitoring**: Real-time updates on retry progress

## Common Failure Scenarios

### Content Extraction Failures

**Causes:**
- Invalid or inaccessible URLs
- Network timeouts
- Jina AI Reader service issues
- Content format not supported

**Retry Behavior:**
- Restarts from content extraction step
- May succeed if the issue was temporary

### LLM Processing Failures

**Causes:**
- Google Gemini API rate limits
- Invalid API keys
- Content too large for processing
- JSON parsing errors in LLM response

**Retry Behavior:**
- Skips content extraction (already completed)
- Restarts from LLM processing step
- Preserves downloaded content

### Vectorization Failures

**Causes:**
- Weaviate database unavailable
- OpenAI API issues
- Vector storage capacity limits
- Network connectivity problems

**Retry Behavior:**
- Skips content extraction and LLM processing
- Restarts from vectorization step
- Preserves summary and keywords

## Best Practices

### 1. Monitor Failed Pages

Regularly check for failed pages using the Web UI or API:

```bash
# List all failed pages
curl -X GET "http://localhost:8000/api/v1/pages?status=failed"
```

### 2. Batch Retry During Off-Peak Hours

Run batch retries during low-usage periods to avoid API rate limits:

```bash
# Retry with delays to respect rate limits
curl -X POST "http://localhost:8000/api/v1/retry-failed" \
  -H "Content-Type: application/json" \
  -d '{"delay_seconds": 5}'
```

### 3. Check Error Messages

Before retrying, examine error messages to understand failure causes:

```bash
# Get page details including error message
curl -X GET "http://localhost:8000/api/v1/pages/123"
```

### 4. Gradual Retry Approach

For large numbers of failed pages:

1. Start with a small batch to test
2. Gradually increase batch size
3. Monitor success rates
4. Adjust delays based on API response times

## Troubleshooting

### Retry Not Starting

**Possible Causes:**
- Page is not in failed state
- Page ID doesn't exist
- System resources unavailable

**Solutions:**
- Verify page status: `GET /api/v1/pages/{page_id}`
- Check system health: `GET /health`
- Review error logs

### Repeated Failures

**Possible Causes:**
- Persistent external service issues
- Invalid configuration
- Resource constraints

**Solutions:**
- Check API key configuration
- Verify external service status
- Review system resource usage
- Consider manual intervention for problematic URLs

### Partial Success

**Scenario:** Some pages retry successfully, others continue to fail

**Actions:**
1. Analyze error patterns in failed pages
2. Group failures by error type
3. Address systematic issues (API keys, configuration)
4. Retry remaining pages after fixes

## Monitoring and Logging

### Progress Tracking

Monitor retry progress through:

- **Web UI**: Real-time status updates in pages management
- **API**: Regular status checks via `/api/v1/pages/{page_id}`
- **Logs**: Server logs contain detailed retry information

### Success Metrics

Track retry effectiveness:

- **Success Rate**: Percentage of retries that succeed
- **Time to Completion**: Average time for retry operations
- **Error Patterns**: Common failure types and frequencies

## API Integration Examples

### Python Example

```python
import requests
import time

def retry_failed_pages(base_url="http://localhost:8000"):
    # Get all failed pages
    response = requests.get(f"{base_url}/api/v1/pages?status=failed")
    failed_pages = response.json()["pages"]
    
    print(f"Found {len(failed_pages)} failed pages")
    
    # Retry each page individually with delay
    for page in failed_pages:
        page_id = page["id"]
        print(f"Retrying page {page_id}: {page['url']}")
        
        retry_response = requests.post(f"{base_url}/api/v1/retry/{page_id}")
        result = retry_response.json()
        
        print(f"  Status: {result['status']}")
        print(f"  Restart from: {result.get('restart_from', 'N/A')}")
        
        # Wait between retries
        time.sleep(2)

# Run retry operation
retry_failed_pages()
```

### JavaScript Example

```javascript
async function retryFailedPages(baseUrl = 'http://localhost:8000') {
  // Get failed pages
  const response = await fetch(`${baseUrl}/api/v1/pages?status=failed`);
  const { pages: failedPages } = await response.json();
  
  console.log(`Found ${failedPages.length} failed pages`);
  
  // Batch retry all failed pages
  const batchResponse = await fetch(`${baseUrl}/api/v1/retry-failed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ delay_seconds: 3 })
  });
  
  const result = await batchResponse.json();
  console.log(`Batch retry result:`, result);
}

// Run retry operation
retryFailedPages();
```

## Configuration

### Environment Variables

Retry behavior can be configured through environment variables:

```bash
# Maximum concurrent retry operations
MAX_CONCURRENT_RETRIES=5

# Default delay between retry attempts (seconds)
DEFAULT_RETRY_DELAY=1

# Maximum retry attempts per page
MAX_RETRY_ATTEMPTS=3
```

### Rate Limiting Considerations

When retrying, consider external API rate limits:

- **Jina AI Reader**: Respect rate limits for content extraction
- **Google Gemini**: Monitor quota usage for LLM processing
- **OpenAI**: Consider embedding API rate limits

Adjust retry delays accordingly to avoid hitting rate limits.