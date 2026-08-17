"""Production Compose readiness configuration tests."""

from pathlib import Path


def test_weaviate_healthcheck_and_api_healthy_dependency() -> None:
    compose = (Path(__file__).parents[4] / "docker-compose.prod.yml").read_text()

    assert "/v1/.well-known/ready" in compose
    assert "condition: service_healthy" in compose
    assert '"--spider"' not in compose
    assert '"-O", "/dev/null"' in compose


def test_worker_overrides_api_healthcheck_and_allows_graceful_stop() -> None:
    compose = (Path(__file__).parents[4] / "docker-compose.prod.yml").read_text()
    worker_section = compose.split("  worker:", 1)[1].split("  weaviate:", 1)[0]

    assert '"grimoire_api.worker"' in worker_section
    assert "healthcheck:\n      disable: true" in worker_section
    assert "stop_grace_period: 20s" in worker_section
