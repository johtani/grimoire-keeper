"""Fixtures for API integration tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from grimoire_api.dependencies import get_db_connection
from grimoire_api.main import app
from grimoire_api.repositories.database import DatabaseConnection


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Label every test below this directory as an integration test."""
    integration = pytest.mark.integration
    for item in items:
        if item.path.is_relative_to(__file__.rsplit("/", 1)[0]):
            item.add_marker(integration)


@pytest.fixture
def integration_client(temp_db: DatabaseConnection) -> Iterator[TestClient]:
    """Serve the real routers and repositories against an isolated SQLite DB."""
    app.dependency_overrides[get_db_connection] = lambda: temp_db
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.clear()
