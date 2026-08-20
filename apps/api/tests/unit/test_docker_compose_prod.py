"""Production Compose readiness configuration tests."""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[4]


def test_weaviate_healthcheck_and_api_healthy_dependency() -> None:
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()

    assert "/v1/.well-known/ready" in compose
    assert "condition: service_healthy" in compose
    assert '"--spider"' not in compose
    assert '"-O", "/dev/null"' in compose


def test_worker_overrides_api_healthcheck_and_allows_graceful_stop() -> None:
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    worker_section = compose.split("  worker:", 1)[1].split("  weaviate:", 1)[0]

    assert '"grimoire_api.worker"' in worker_section
    assert "healthcheck:\n      disable: true" in worker_section
    assert "stop_grace_period: 20s" in worker_section


def test_deploy_runs_conditional_backup_before_single_process_migration() -> None:
    """本番デプロイが判定、バックアップ、単独移行、起動の順で行われる."""
    deploy = (Path(__file__).parents[4] / "scripts" / "deploy.sh").read_text()

    status = "init_database.py migration-status"
    backup = 'cp -a "${DATA_ROOT}/database/." "${backup_path}/"'
    migration = "init_database.py sqlite"
    services = "docker compose -f docker-compose.prod.yml up -d"

    assert deploy.index(status) < deploy.index(backup)
    assert deploy.index(backup) < deploy.index(migration)
    assert deploy.index(migration) < deploy.index(services)
    assert 'case "${migration_status}"' in deploy
    assert '"${FORCE_SQLITE_BACKUP:-false}"' in deploy
    subprocess.run(["bash", "-n", "scripts/deploy.sh"], check=True)


def test_documented_weaviate_commands_reference_tracked_compose_file() -> None:
    """利用者向けのWeaviate起動案内が実在するComposeファイルを参照する."""
    compose_file = PROJECT_ROOT / "docker-compose.prod.yml"
    documented_command = "docker compose -f docker-compose.prod.yml up -d weaviate"

    assert compose_file.is_file()
    for relative_path in ("README.md", "AGENTS.md", "scripts/init_database.py"):
        content = (PROJECT_ROOT / relative_path).read_text()
        assert documented_command in content
        assert "docker compose up -d weaviate" not in content

    assert "`docker-compose.yml`" not in (PROJECT_ROOT / "README.md").read_text()


def test_deploy_removes_orphan_containers_when_recreating_services() -> None:
    deploy = (Path(__file__).parents[4] / "scripts" / "deploy.sh").read_text()

    assert "docker compose -f docker-compose.prod.yml down --remove-orphans" in deploy
    assert "docker compose -f docker-compose.prod.yml up -d --remove-orphans" in deploy
