"""File-backed liveness state for the dedicated job worker."""

import json
import os
import sys
import time
from pathlib import Path

DEFAULT_HEALTH_PATH = Path("/tmp/grimoire-worker-health.json")
DEFAULT_MAX_AGE = 30.0


class WorkerHealth:
    """Publish claim-loop liveness for a container healthcheck."""

    def __init__(self, path: Path = DEFAULT_HEALTH_PATH) -> None:
        self.path = path
        self.status = "starting"
        self.last_claim_at: float | None = None

    def mark_running(self) -> None:
        self.status = "running"
        self.heartbeat()

    def heartbeat(self) -> None:
        self._write(
            {
                "status": self.status,
                "heartbeat_at": time.time(),
                "last_claim_at": self.last_claim_at,
            }
        )

    def record_claim(self) -> None:
        self.last_claim_at = time.time()
        self.heartbeat()

    def mark_stopped(self) -> None:
        self.status = "stopped"
        self.heartbeat()

    def _write(self, state: dict[str, str | float | None]) -> None:
        state["pid"] = os.getpid()
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(json.dumps(state), encoding="utf-8")
        temporary_path.replace(self.path)


def is_healthy(
    path: Path = DEFAULT_HEALTH_PATH,
    max_age: float = DEFAULT_MAX_AGE,
    now: float | None = None,
) -> bool:
    """Return whether the claim loop is running and recently polled."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        heartbeat_at = float(state["heartbeat_at"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    current_time = time.time() if now is None else now
    return (
        state.get("status") == "running" and 0 <= current_time - heartbeat_at <= max_age
    )


def main() -> None:
    """Exit successfully only while the claim loop heartbeat is fresh."""
    path = Path(os.getenv("WORKER_HEALTH_PATH", str(DEFAULT_HEALTH_PATH)))
    max_age = float(os.getenv("WORKER_HEALTH_MAX_AGE", str(DEFAULT_MAX_AGE)))
    sys.exit(0 if is_healthy(path, max_age) else 1)


if __name__ == "__main__":
    main()
