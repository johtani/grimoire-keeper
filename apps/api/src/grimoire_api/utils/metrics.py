"""API メトリクス設定"""

from grimoire_shared.telemetry import get_meter

meter = get_meter(__name__)

# URL処理メトリクス
url_processing_requests = meter.create_counter(
    "url_processing_requests_total",
    description="Total number of URL processing requests",
)

url_processing_duration = meter.create_histogram(
    "url_processing_duration_seconds",
    description="Duration of URL processing operations",
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
