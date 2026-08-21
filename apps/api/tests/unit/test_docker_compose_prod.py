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


def test_api_and_worker_receive_canonical_llm_api_key() -> None:
    """APIとworkerが要約LLM用の正規変数を同じ方法で受け取る."""
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    api_section = compose.split("  api:", 1)[1].split("  worker:", 1)[0]
    worker_section = compose.split("  worker:", 1)[1].split("  weaviate:", 1)[0]

    expected = "LLM_API_KEY=${GRIMOIRE_KEEPER_LLM_API_KEY}"
    for service_section in (api_section, worker_section):
        assert expected in service_section
        assert "GOOGLE_API_KEY" not in service_section
        assert "GRIMOIRE_KEEPER_LLM_API_KEY:-dummy" not in service_section


def test_dev_script_maps_canonical_llm_api_key() -> None:
    """開発起動スクリプトも本番Composeと同じLLMキーを渡す."""
    script = (PROJECT_ROOT / "scripts/dev.sh").read_text()

    assert 'export LLM_API_KEY="${GRIMOIRE_KEEPER_LLM_API_KEY}"' in script
    assert "GOOGLE_API_KEY" not in script


def test_web_healthcheck_uses_canonical_api_path_through_nginx() -> None:
    api_client = (PROJECT_ROOT / "apps/web/static/js/api.js").read_text()
    nginx = (PROJECT_ROOT / "apps/web/nginx.conf").read_text()

    health_check = api_client.split("async healthCheck()", 1)[1].split(
        "async getSystemInfo()", 1
    )[0]
    assert "this.request('/api/v1/health')" in health_check
    assert "this.request('/health')" not in health_check

    assert "location /api/" in nginx
    assert "proxy_pass http://api:8000/api/;" in nginx
    assert "location /health" not in nginx
    assert "proxy_pass http://api:8000/health" not in nginx


def test_deploy_checks_api_health_through_web_proxy() -> None:
    deploy = (PROJECT_ROOT / "scripts/deploy.sh").read_text()

    assert "curl -f http://localhost:8001/api/v1/health" in deploy
    assert "curl -f http://localhost:8000/api/v1/health" not in deploy


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
