"""Web CI must not select Node.js versions predating the security release."""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parents[4]


def test_web_ci_requires_patched_node_and_checks_latest_release() -> None:
    workflow = yaml.safe_load((PROJECT_ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["web-test"]["steps"]
    setup_node = next(
        step for step in steps if step.get("uses", "").startswith("actions/setup-node@")
    )

    assert setup_node["with"]["node-version"] == ">=22.23.4 <23"
    assert setup_node["with"]["check-latest"] is True
