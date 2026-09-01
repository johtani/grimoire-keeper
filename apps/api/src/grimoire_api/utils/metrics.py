"""API メトリクス設定"""

from grimoire_shared.telemetry import get_meter

meter = get_meter(__name__)

# URL処理 API 受付メトリクス
url_processing_api_requests = meter.create_counter(
    "url_processing_api_requests_total",
    description="Total number of URL processing API requests",
)

url_processing_api_duration = meter.create_histogram(
    "url_processing_api_duration_seconds",
    description="Duration of URL processing API requests",
    unit="s",
)

# 永続ジョブ実行メトリクス
url_processing_job_attempts = meter.create_counter(
    "url_processing_job_attempts_total",
    description="Total number of completed URL processing job attempts",
)

url_processing_job_attempt_duration = meter.create_histogram(
    "url_processing_job_attempt_duration_seconds",
    description="Duration of URL processing job attempts",
    unit="s",
)

url_processing_job_completions = meter.create_counter(
    "url_processing_job_completions_total",
    description="Total number of logical URL processing job completions",
)

url_processing_job_duration = meter.create_histogram(
    "url_processing_job_duration_seconds",
    description="Duration of logical URL processing jobs",
    unit="s",
)

# 検索メトリクス
search_requests = meter.create_counter(
    "search_requests_total", description="Total number of search requests"
)

search_results_count = meter.create_histogram(
    "search_results_count", description="Number of search results returned"
)

# データベース操作メトリクス
database_operations = meter.create_counter(
    "database_operations_total", description="Total number of database operations"
)

# 外部API呼び出しメトリクス
external_api_calls = meter.create_counter(
    "external_api_calls_total", description="Total number of external API calls"
)

external_api_duration = meter.create_histogram(
    "external_api_duration_seconds", description="Duration of external API calls"
)
