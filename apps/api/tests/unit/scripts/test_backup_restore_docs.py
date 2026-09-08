"""Run the documented filesystem operations against disposable backup data."""

import os
import re
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[5]


def documented_commands(name: str) -> str:
    document = (PROJECT_ROOT / "DEPLOY.md").read_text()
    section = document.split(f"<!-- {name}:start -->", 1)[1].split(
        f"<!-- {name}:end -->", 1
    )[0]
    return re.search(r"```bash\n(.*?)```", section, re.DOTALL).group(1)


def run_commands(
    name: str, workdir: Path, env: dict[str, str]
) -> subprocess.CompletedProcess:
    # Run as the test user; no production paths, sudo, Docker or external services.
    return subprocess.run(
        [
            "bash",
            "-c",
            'set -euo pipefail\nsudo() { "$@"; }\n'
            'git() { printf "test-commit\\n"; }\n' + documented_commands(name),
        ],
        cwd=workdir,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )


@pytest.fixture
def backup_environment(tmp_path: Path) -> dict[str, str]:
    root = tmp_path / "live data"
    database = root / "database"
    database.mkdir(parents=True)
    with closing(sqlite3.connect(database / "grimoire.db")) as connection:
        connection.execute("CREATE TABLE pages (title TEXT)")
        connection.execute("INSERT INTO pages VALUES ('saved page')")
        connection.commit()
    (database / "grimoire.db").chmod(0o600)
    (root / "json").mkdir()
    (root / "json/page.json").write_text('{"body": "saved content"}')
    (root / "json/.metadata").write_text("hidden file")
    (root / "migration").mkdir()
    (root / "migration/repair-pending.json").write_text("saved report")
    weaviate = tmp_path / "custom vector data"
    weaviate.mkdir()
    (weaviate / "shard").write_bytes(b"saved vector data")
    (tmp_path / ".env").write_text("WEAVIATE_EMBEDDING_DIMENSIONS=1536\n")
    (tmp_path / "docker-compose.prod.yml").write_text("services: {}\n")
    return {
        "DATA_ROOT": str(root),
        "WEAVIATE_DATA_PATH": str(weaviate),
        "WEAVIATE_IMAGE": "test/weaviate:version",
        "BACKUP_PARENT": str(tmp_path / "backups"),
    }


@pytest.mark.parametrize("existing_target", [True, False])
def test_documented_backup_restore_replaces_complete_dataset(
    tmp_path: Path, backup_environment: dict[str, str], existing_target: bool
) -> None:
    env = backup_environment
    result = run_commands("backup-files", tmp_path, env)
    assert result.returncode == 0, result.stderr
    backups = list(Path(env["BACKUP_PARENT"]).iterdir())
    assert len(backups) == 1
    backup = backups[0]
    assert not backup.name.endswith(".partial")
    assert (backup / "COMPLETE").is_file()
    assert (backup / "weaviate-data-path.txt").read_text().strip() == env[
        "WEAVIATE_DATA_PATH"
    ]
    assert (backup / "weaviate-image.txt").read_text().strip() == env["WEAVIATE_IMAGE"]
    targets = [
        Path(env["DATA_ROOT"]) / name for name in ("database", "json", "migration")
    ]
    targets.append(Path(env["WEAVIATE_DATA_PATH"]))
    for target in targets:
        if existing_target:
            (target / "obsolete").write_text("preserve in previous only")
        else:
            for child in target.iterdir():
                child.unlink()
            target.rmdir()
    if existing_target:
        (targets[0] / "grimoire.db-wal").write_bytes(b"obsolete WAL")
        (targets[0] / "grimoire.db-shm").write_bytes(b"obsolete SHM")
        (targets[1] / "page.json").write_text("modified after backup")
    result = run_commands("restore-files", tmp_path, {**env, "BACKUP_DIR": str(backup)})
    assert result.returncode == 0, result.stderr
    for target, source in zip(
        targets, ("database", "json", "migration", "weaviate"), strict=True
    ):
        assert {p.name for p in target.iterdir()} == {
            p.name for p in (backup / source).iterdir()
        }
        for child in target.iterdir():
            original = backup / source / child.name
            assert child.read_bytes() == original.read_bytes()
            assert child.stat().st_mode == original.stat().st_mode
            assert child.stat().st_uid == original.stat().st_uid
            assert child.stat().st_gid == original.stat().st_gid
        stages = list(target.parent.glob(f"{target.name}.restore-*"))
        assert len(stages) == 1
        if existing_target:
            assert (
                stages[0] / "previous/obsolete"
            ).read_text() == "preserve in previous only"
        else:
            assert not (stages[0] / "previous").exists()
    with closing(sqlite3.connect(targets[0] / "grimoire.db")) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT title FROM pages").fetchall() == [
            ("saved page",)
        ]
    assert (backup / "json/page.json").read_text() == '{"body": "saved content"}'


def test_failed_backup_is_not_published(
    tmp_path: Path, backup_environment: dict[str, str]
) -> None:
    env = {**backup_environment, "WEAVIATE_DATA_PATH": str(tmp_path / "missing")}
    result = run_commands("backup-files", tmp_path, env)
    assert result.returncode != 0
    backups = list(Path(env["BACKUP_PARENT"]).iterdir())
    assert len(backups) == 1
    assert backups[0].name.endswith(".partial")
    assert not (backups[0] / "COMPLETE").exists()


@pytest.mark.parametrize("incomplete", ["marker", "weaviate", "partial"])
def test_incomplete_restore_preserves_live_data(
    tmp_path: Path, backup_environment: dict[str, str], incomplete: str
) -> None:
    env = backup_environment
    assert run_commands("backup-files", tmp_path, env).returncode == 0
    backup = next(Path(env["BACKUP_PARENT"]).iterdir())
    if incomplete == "marker":
        (backup / "COMPLETE").unlink()
    elif incomplete == "weaviate":
        (backup / "weaviate/shard").unlink()
        (backup / "weaviate").rmdir()
    else:
        backup = backup.rename(backup.with_name(backup.name + ".partial"))
    live_json = Path(env["DATA_ROOT"]) / "json/page.json"
    live_json.write_text("current data")
    result = run_commands("restore-files", tmp_path, {**env, "BACKUP_DIR": str(backup)})
    assert result.returncode != 0
    assert live_json.read_text() == "current data"
    assert not list(tmp_path.rglob("*.restore-*"))
