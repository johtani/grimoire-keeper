"""Slack Bot test fixtures."""

import json
from pathlib import Path
from typing import Any

import pytest

BOT_CONTRACT_FIXTURES = (
    Path(__file__).parents[2] / "api" / "tests" / "fixtures" / "bot_contracts"
)


@pytest.fixture
def bot_contract_fixture():
    """API 所有の Bot contract fixture を読み込む."""

    def load(fixture_name: str) -> dict[str, Any]:
        return json.loads((BOT_CONTRACT_FIXTURES / fixture_name).read_text())

    return load
