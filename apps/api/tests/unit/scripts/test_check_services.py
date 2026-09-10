"""Keep service-check guidance and development startup documentation valid."""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[5]


def test_check_services_references_existing_development_guide() -> None:
    script = (PROJECT_ROOT / "scripts/check_services.py").read_text()

    assert "docs/development.md" in script
    assert "SETUP_API.md" not in script
    assert (PROJECT_ROOT / "docs/development.md").is_file()


def test_dev_script_only_starts_api() -> None:
    script_path = PROJECT_ROOT / "scripts/dev.sh"
    script = script_path.read_text()

    result = subprocess.run(
        ["bash", "-n", str(script_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "uvicorn grimoire_api.main:app" in script
    assert "grimoire_api.worker" not in script
    assert "bws run" not in script
