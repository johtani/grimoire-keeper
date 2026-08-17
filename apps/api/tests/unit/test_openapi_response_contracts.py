"""OpenAPI response schema contract tests."""

from fastapi.testclient import TestClient
from grimoire_api.main import app


def test_public_api_success_responses_use_concrete_schemas() -> None:
    """型付きへ移行した API が具体的な OpenAPI スキーマを公開する."""
    schema = TestClient(app).get("/openapi.json").json()
    expected_schemas = {
        ("/api/v1/pages", "get", "200"): "PageListResponse",
        ("/api/v1/pages/{page_id}", "get", "200"): "PageResponse",
        ("/api/v1/process-status/{page_id}", "get", "200"): "ProcessStatusResponse",
        ("/api/v1/retry/{page_id}", "post", "202"): "RetryResponse",
        ("/api/v1/reprocess/{page_id}", "post", "202"): "RetryResponse",
        ("/api/v1/retry-failed", "post", "202"): "BatchRetryResponse",
        ("/api/v1/repairs", "get", "200"): "RepairListResponse",
        ("/api/v1/repairs/import", "post", "200"): "RepairImportResponse",
        ("/api/v1/repairs/scan", "post", "200"): "RepairScanResponse",
        ("/api/v1/pages/{page_id}/repair", "get", "200"): "RepairDetailResponse",
        ("/api/v1/pages/{page_id}/url", "patch", "200"): "UpdatePageUrlResponse",
    }

    for (path, method, status_code), model_name in expected_schemas.items():
        response_schema = schema["paths"][path][method]["responses"][status_code]
        assert response_schema["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model_name}"
        }


def test_raw_page_json_has_an_explicit_json_schema() -> None:
    """透過取得 API も型なし object ではなく任意 JSON として公開する."""
    schema = TestClient(app).get("/openapi.json").json()
    response_schema = schema["paths"]["/api/v1/pages/{page_id}/json"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]

    assert response_schema == {"$ref": "#/components/schemas/JsonValue"}
