"""Reproducible production container configuration tests."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[4]
DOCKERFILES = (
    PROJECT_ROOT / "apps/api/Dockerfile.prod",
    PROJECT_ROOT / "apps/bot/Dockerfile.prod",
)


def test_production_dockerfiles_use_pinned_multistage_images() -> None:
    """Base and uv images are immutable and uv stays in the builder stages."""
    for dockerfile in DOCKERFILES:
        content = dockerfile.read_text()

        assert "python:3.13-slim-bookworm@sha256:" in content
        assert "docker.io/astral/uv:0.11.30@sha256:" in content
        assert "FROM ${UV_IMAGE} AS uv" in content
        assert "FROM ${PYTHON_IMAGE} AS builder" in content
        assert "FROM ${PYTHON_IMAGE} AS runtime" in content
        runtime = content.split("FROM ${PYTHON_IMAGE} AS runtime", 1)[1]
        assert "COPY --from=uv" not in runtime
        assert "uv run" not in runtime


def test_production_sync_is_frozen_and_excludes_development_dependencies() -> None:
    """Both dependency layers are resolved exclusively from the committed lockfile."""
    for dockerfile in DOCKERFILES:
        content = dockerfile.read_text()
        sync_commands = [
            line for line in content.splitlines() if line.startswith("RUN uv sync")
        ]

        assert "COPY pyproject.toml uv.lock ./" in content
        assert "RUN uv lock --check" in content
        assert len(sync_commands) == 2
        assert all("--frozen" in command for command in sync_commands)
        assert all("--no-dev" in command for command in sync_commands)
        assert "--no-install-workspace" in sync_commands[0]
        assert "--no-editable" in sync_commands[1]


def test_runtime_commands_do_not_depend_on_uv() -> None:
    """Production entrypoints and operational commands use the built virtualenv."""
    files = (
        PROJECT_ROOT / "docker-compose.prod.yml",
        PROJECT_ROOT / "scripts/deploy.sh",
        PROJECT_ROOT / "tools/weaviate_1_38_migration/migrate.sh",
    )

    for path in files:
        assert "uv run" not in path.read_text()
