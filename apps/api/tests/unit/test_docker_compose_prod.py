"""Production Compose readiness configuration tests."""

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[4]


def test_weaviate_healthcheck_only_blocks_worker_startup() -> None:
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    api_section = compose.split("  api:", 1)[1].split("  worker:", 1)[0]
    worker_section = compose.split("\n  worker:", 1)[1].split("\n  weaviate:", 1)[0]

    assert "/v1/.well-known/ready" in compose
    assert "condition: service_healthy" not in api_section
    assert "condition: service_healthy" in worker_section
    assert '"--spider"' not in compose
    assert '"-O", "/dev/null"' in compose


def test_host_ports_are_loopback_only_and_internal_connections_are_preserved() -> None:
    """ホスト公開をloopbackに限定し、コンテナ間通信は内部DNSを使う."""
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    web_section = compose.split("  web:", 1)[1].split("  bot:", 1)[0]
    bot_section = compose.split("  bot:", 1)[1].split("  api:", 1)[0]
    api_section = compose.split("  api:", 1)[1].split("  worker:", 1)[0]
    weaviate_section = compose.rsplit("  weaviate:", 1)[1].split("networks:", 1)[0]

    assert '"127.0.0.1:8001:80"' in web_section
    assert '"127.0.0.1:8000:8000"' in api_section
    assert '"127.0.0.1:8089:8080"' in weaviate_section
    assert '"127.0.0.1:50051:50051"' in weaviate_section
    assert "BACKEND_API_URL=http://api:8000" in bot_section
    assert "AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'" in weaviate_section

    unrestricted_bindings = (
        '"8001:80"',
        '"8000:8000"',
        '"8089:8080"',
        '"50051:50051"',
        "0.0.0.0:",
    )
    assert all(binding not in compose for binding in unrestricted_bindings)


def test_deploy_documentation_preserves_local_only_access_policy() -> None:
    """本番手順が管理portを外部公開せず、内部通信と確認方法を案内する."""
    deploy = (PROJECT_ROOT / "DEPLOY.md").read_text()

    for binding in (
        "127.0.0.1:8001",
        "127.0.0.1:8000",
        "127.0.0.1:8089",
        "127.0.0.1:50051",
    ):
        assert binding in deploy

    assert "http://api:8000" in deploy
    assert "weaviate:8080" in deploy
    assert "Socket Mode" in deploy
    assert "outbound" in deploy
    assert "docker compose -f docker-compose.prod.yml config" in deploy
    assert "sudo ss -lntp" in deploy
    assert "sudo ufw status numbered" in deploy
    assert "ssh -N -L 8001:127.0.0.1:8001" in deploy

    unsafe_guidance = (
        "8000番ポートのみ公開",
        "API (外部公開)",
        "listen 80;",
        "server_name your-domain.com",
    )
    assert all(guidance not in deploy for guidance in unsafe_guidance)


def test_worker_has_claim_loop_healthcheck_and_allows_graceful_stop() -> None:
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    worker_section = compose.split("\n  worker:", 1)[1].split("\n  weaviate:", 1)[0]

    assert '"grimoire_api.worker"' in worker_section
    assert '"grimoire_api.worker_health"' in worker_section
    assert '"/app/.venv/bin/python"' in worker_section
    assert "healthcheck:\n      disable: true" not in worker_section
    assert "stop_grace_period: 20s" in worker_section
    assert "restart: unless-stopped" in worker_section


def test_only_worker_receives_processing_credentials() -> None:
    """AI処理用キーはworkerだけへ渡す."""
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    api_section = compose.split("  api:", 1)[1].split("  worker:", 1)[0]
    worker_section = compose.split("\n  worker:", 1)[1].split("\n  weaviate:", 1)[0]

    processing_keys = (
        "OPENAI_API_KEY=${GRIMOIRE_KEEPER_OPENAI_API_KEY}",
        "JINA_API_KEY=${GRIMOIRE_KEEPER_JINA_API_KEY}",
        "LLM_API_KEY=${GRIMOIRE_KEEPER_LLM_API_KEY}",
    )
    assert all(key not in api_section for key in processing_keys)
    assert all(key in worker_section for key in processing_keys)


def test_worker_receives_pinned_embedding_configuration() -> None:
    """workerへ非秘密の埋め込み設定を明示的に渡す."""
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    worker_section = compose.split("\n  worker:", 1)[1].split("\n  weaviate:", 1)[0]

    assert (
        "WEAVIATE_EMBEDDING_PROVIDER=${WEAVIATE_EMBEDDING_PROVIDER:-text2vec-openai}"
        in worker_section
    )
    assert (
        "WEAVIATE_EMBEDDING_MODEL=${WEAVIATE_EMBEDDING_MODEL:-text-embedding-ada-002}"
        in worker_section
    )
    assert (
        "WEAVIATE_EMBEDDING_DIMENSIONS=${WEAVIATE_EMBEDDING_DIMENSIONS:-1536}"
        in worker_section
    )


def test_dev_api_script_does_not_require_worker_credentials() -> None:
    """開発APIはBitwardenやAI処理用キーなしで起動する."""
    script = (PROJECT_ROOT / "scripts/dev.sh").read_text()

    assert "bws run" not in script
    assert "BWS_ACCESS_TOKEN" not in script
    assert "GRIMOIRE_KEEPER_" not in script
    assert "uvicorn grimoire_api.main:app" in script


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
    backup = 'sudo cp -a "${DATA_ROOT}/database/." "${backup_path}/"'
    migration = "init_database.py sqlite"
    services = "docker compose -f docker-compose.prod.yml up -d"

    assert deploy.index(status) < deploy.index(backup)
    assert deploy.index(backup) < deploy.index(migration)
    assert deploy.index(migration) < deploy.index(services)
    assert 'case "${migration_status}"' in deploy
    assert '"${FORCE_SQLITE_BACKUP:-false}"' in deploy
    assert 'sudo chown -R "${USER}:${USER}" "${backup_path}"' in deploy
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


def _application_sections(compose: str) -> dict[str, str]:
    return {
        "bot": compose.split("\n  bot:", 1)[1].split("\n  api:", 1)[0],
        "api": compose.split("\n  api:", 1)[1].split("\n  worker:", 1)[0],
        "worker": compose.split("\n  worker:", 1)[1].split("\n  weaviate:", 1)[0],
    }


def test_application_services_are_hardened() -> None:
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()

    for section in _application_sections(compose).values():
        assert 'user: "10001:10001"' in section
        assert "read_only: true" in section
        assert "- /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777" in section
        assert "cap_drop:\n      - ALL" in section
        assert "security_opt:\n      - no-new-privileges:true" in section


def test_application_volume_permissions_follow_service_responsibilities() -> None:
    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    sections = _application_sections(compose)

    assert "volumes:" not in sections["bot"]
    assert "/opt/grimoire-keeper-data/database:/data" in sections["api"]
    assert (
        "/opt/grimoire-keeper-data/json:/app/apps/api/data/json:ro" in sections["api"]
    )
    assert (
        "/opt/grimoire-keeper-data/migration:/app/apps/api/data/migration:ro"
        in sections["api"]
    )
    assert "/opt/grimoire-keeper-data/database:/data" in sections["worker"]
    assert (
        "/opt/grimoire-keeper-data/json:/app/apps/api/data/json" in sections["worker"]
    )
    assert (
        "/opt/grimoire-keeper-data/json:/app/apps/api/data/json:ro"
        not in sections["worker"]
    )


def test_deploy_prepares_only_application_data_for_fixed_uid() -> None:
    deploy = (PROJECT_ROOT / "scripts/deploy.sh").read_text()

    assert "APP_UID=10001" in deploy
    assert "APP_GID=10001" in deploy
    assert '"${DATA_ROOT}/migration"' in deploy
    assert 'sudo chown -R "${APP_UID}:${APP_GID}"' in deploy
    assert 'sudo chmod 0750 "${DATA_ROOT}/database" "${DATA_ROOT}/json"' in deploy
    subprocess.run(["bash", "-n", "scripts/deploy.sh"], check=True)


def test_production_compose_renders(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is not installed")

    compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text()
    test_compose = tmp_path / "docker-compose.prod.yml"
    test_compose.write_text(compose.replace("      - .env\n", "      - .env.test\n"))
    subprocess.run(
        [
            "docker",
            "compose",
            "--project-directory",
            str(PROJECT_ROOT),
            "-f",
            str(test_compose),
            "config",
            "--quiet",
        ],
        check=True,
        cwd=PROJECT_ROOT,
    )
