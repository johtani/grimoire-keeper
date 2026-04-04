"""Shared fixtures for router unit tests."""

import pytest
from grimoire_api.main import app


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> pytest.FixtureRequest:
    """各テストの前後に dependency_overrides をクリア."""
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
