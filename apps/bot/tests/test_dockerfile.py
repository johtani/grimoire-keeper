"""Bot Dockerfile configuration tests."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]


def test_healthcheck_converts_api_result_to_exit_code() -> None:
    """APIヘルスチェック結果をコンテナの終了コードへ反映する."""
    dockerfile = (PROJECT_ROOT / "apps/bot/Dockerfile.prod").read_text()
    healthcheck = dockerfile.split("HEALTHCHECK", 1)[1].split("# ボット起動", 1)[0]

    assert "sys.exit(not asyncio.run(ApiClient().health_check()))" in healthcheck
    assert "from grimoire_bot.services.api_client import ApiClient" in healthcheck
