"""Fail-safe cleanup for Locust users left behind by a Web UI stop race."""

from __future__ import annotations

from typing import Any


IDLE_RUNNER_STATES = frozenset({"ready", "stopped"})


def reap_orphaned_users(runner: Any) -> int:
    """Force-stop users only when Locust already claims to be idle.

    Locust's Web UI can race with an in-progress spawn: the runner reaches an
    idle state while a user greenlet remains alive. A later `/stop` is a no-op
    because Locust returns early for an already-stopped runner.

    Distributed runners do not expose ``user_greenlets`` and are deliberately
    ignored. Active ``spawning`` and ``running`` states are never touched.
    """

    if runner is None or getattr(runner, "state", None) not in IDLE_RUNNER_STATES:
        return 0

    user_count = int(getattr(runner, "user_count", 0) or 0)
    user_greenlets = getattr(runner, "user_greenlets", None)
    if user_count <= 0 or user_greenlets is None:
        return 0

    user_greenlets.kill(block=True)
    return user_count
