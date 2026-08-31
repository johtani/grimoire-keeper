"""Dedicated worker process-lock tests."""

import subprocess
import sys
from pathlib import Path

import pytest
from grimoire_api.worker_lock import WorkerAlreadyRunningError, WorkerLock


def test_worker_lock_rejects_second_owner(tmp_path: Path) -> None:
    """同じDBを使う二つ目のworkerを明示的に拒否する."""
    database_path = str(tmp_path / "grimoire.db")

    with WorkerLock(database_path):
        with pytest.raises(
            WorkerAlreadyRunningError, match="Another job worker is already using"
        ):
            WorkerLock(database_path).acquire()


def test_worker_lock_can_be_reacquired_after_release(tmp_path: Path) -> None:
    """ownerの終了後は残存lock fileがあっても次のworkerが取得できる."""
    database_path = str(tmp_path / "grimoire.db")
    first_lock = WorkerLock(database_path)
    first_lock.acquire()
    lock_path = first_lock.path
    first_lock.release()

    assert lock_path.exists()
    with WorkerLock(database_path):
        pass


def test_worker_lock_is_released_when_owner_process_exits(tmp_path: Path) -> None:
    """ownerが明示解放せず終了してもkernelがstale lockを復旧する."""
    database_path = str(tmp_path / "grimoire.db")
    script = (
        "import os, sys; "
        "from grimoire_api.worker_lock import WorkerLock; "
        "WorkerLock(sys.argv[1]).acquire(); "
        "os._exit(0)"
    )

    subprocess.run([sys.executable, "-c", script, database_path], check=True)

    with WorkerLock(database_path):
        pass


def test_worker_lock_release_is_idempotent(tmp_path: Path) -> None:
    """起動途中の失敗を想定し、重複解放を安全に扱う."""
    worker_lock = WorkerLock(str(tmp_path / "grimoire.db"))
    worker_lock.acquire()

    worker_lock.release()
    worker_lock.release()
