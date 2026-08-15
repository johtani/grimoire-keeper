"""Production Compose readiness configuration tests."""

from pathlib import Path


def test_weaviate_healthcheck_and_api_healthy_dependency() -> None:
    compose = (Path(__file__).parents[4] / "docker-compose.prod.yml").read_text()

    assert "/v1/.well-known/ready" in compose
    assert "condition: service_healthy" in compose
    assert '"--spider"' not in compose
    assert '"-O", "/dev/null"' in compose
