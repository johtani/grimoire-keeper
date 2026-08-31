"""Dedicated worker health-state tests."""

import json
from pathlib import Path

from grimoire_api.worker_health import WorkerHealth, is_healthy


def test_running_recent_heartbeat_is_healthy(tmp_path: Path) -> None:
    path = tmp_path / "worker-health.json"
    health = WorkerHealth(path)

    health.mark_running()

    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["status"] == "running"
    assert state["last_claim_at"] is None
    assert is_healthy(path, now=state["heartbeat_at"] + 1)

    health.record_claim()
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["last_claim_at"] is not None


def test_missing_stale_and_stopped_health_are_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "worker-health.json"
    assert not is_healthy(path)

    health = WorkerHealth(path)
    health.mark_running()
    state = json.loads(path.read_text(encoding="utf-8"))
    assert not is_healthy(path, max_age=10, now=state["heartbeat_at"] + 11)

    health.mark_stopped()
    assert not is_healthy(path)


def test_invalid_health_state_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "worker-health.json"
    path.write_text("not-json", encoding="utf-8")

    assert not is_healthy(path)
