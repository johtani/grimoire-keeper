"""Devcontainer configuration contract tests."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parents[4]
COMPOSE_PATH = PROJECT_ROOT / ".devcontainer/docker-compose.yml"
README_PATH = PROJECT_ROOT / ".devcontainer/README.md"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text())


def test_devcontainer_runs_workspace_and_weaviate_only() -> None:
    compose = _compose()

    assert set(compose["services"]) == {"workspace", "weaviate"}
    assert "profiles" not in COMPOSE_PATH.read_text()
    assert not (PROJECT_ROOT / "apps/api/Dockerfile").exists()
    assert not (PROJECT_ROOT / "apps/bot/Dockerfile").exists()
    assert (PROJECT_ROOT / "apps/api/Dockerfile.prod").exists()
    assert (PROJECT_ROOT / "apps/bot/Dockerfile.prod").exists()


def test_devcontainer_weaviate_matches_production_without_llm_port_conflict() -> None:
    compose = _compose()
    weaviate = compose["services"]["weaviate"]

    assert weaviate["image"].endswith(":1.38.8")
    assert weaviate["ports"] == ["127.0.0.1:8089:8080", "127.0.0.1:50051:50051"]
    assert "8080:8080" not in COMPOSE_PATH.read_text()
    assert weaviate["volumes"] == ["weaviate_1_38_8_data:/var/lib/weaviate"]
    assert "weaviate_1_38_8_data" in compose["volumes"]
    assert "weaviate_data" not in compose["volumes"]
    assert "/v1/.well-known/ready" in " ".join(weaviate["healthcheck"]["test"])


def test_workspace_connects_to_internal_weaviate_and_host_llm() -> None:
    workspace = _compose()["services"]["workspace"]

    assert workspace["environment"]["WEAVIATE_HOST"] == "weaviate"
    assert workspace["environment"]["WEAVIATE_PORT"] == 8080
    assert workspace["environment"]["LLM_API_BASE"] == (
        "http://host.docker.internal:8080/v1"
    )
    assert "host.docker.internal:host-gateway" in workspace["extra_hosts"]


def test_devcontainer_editor_configuration_matches_documented_workflow() -> None:
    config = json.loads((PROJECT_ROOT / ".devcontainer/devcontainer.json").read_text())

    assert config["forwardPorts"] == [8000]
    assert "openai.chatgpt" in config["customizations"]["vscode"]["extensions"]
    assert config["postStartCommand"].endswith(
        "HISTFILE=/commandhistory/.bash_history' >> ~/.bashrc"
    )
    assert (
        "bash_history:/commandhistory" in _compose()["services"]["workspace"]["volumes"]
    )
    mounts = "\n".join(config["mounts"])
    assert ".aws" not in mounts
    assert ".claude" not in mounts
    assert ".config/bws.env" in mounts
    assert "readonly" in mounts


def test_devcontainer_readme_covers_end_to_end_and_safe_migration() -> None:
    readme = README_PATH.read_text()

    for guidance in (
        "bash scripts/dev.sh",
        "python -m grimoire_api.worker",
        "http://localhost:8000/api/v1/process-url",
        "http://localhost:8000/api/v1/process-status/{page_id}",
        "http://localhost:8000/api/v1/search",
        "http://host.docker.internal:8080/v1",
        "http://localhost:8089/v1/.well-known/ready",
        "scripts/reindex_weaviate.py --dry-run",
        "weaviate_1_38_8_data",
        "docker compose down -v",
        "GRIMOIRE_KEEPER_JINA_API_KEY",
        "GRIMOIRE_KEEPER_OPENAI_API_KEY",
    ):
        assert guidance in readme

    assert "Amazon Q" not in readme
    assert "1.33.1のデータディレクトリを1.38.8へ直接マウントしない" in readme


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is unavailable")
def test_devcontainer_compose_config_is_valid() -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_PATH), "config", "--quiet"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
