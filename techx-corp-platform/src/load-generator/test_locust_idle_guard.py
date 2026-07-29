from locust_idle_guard import reap_orphaned_users


class RecordingGroup:
    def __init__(self):
        self.calls = []

    def kill(self, *, block):
        self.calls.append(block)


class FakeRunner:
    def __init__(self, state, user_count, *, with_group=True):
        self.state = state
        self.user_count = user_count
        if with_group:
            self.user_greenlets = RecordingGroup()


def test_reaps_user_left_behind_after_web_stop_race():
    runner = FakeRunner("stopped", 1)

    reaped = reap_orphaned_users(runner)

    assert reaped == 1
    assert runner.user_greenlets.calls == [True]


def test_reaps_user_when_runner_claims_ready():
    runner = FakeRunner("ready", 2)

    assert reap_orphaned_users(runner) == 2
    assert runner.user_greenlets.calls == [True]


def test_never_touches_active_load():
    for state in ("spawning", "running", "cleanup"):
        runner = FakeRunner(state, 3)

        assert reap_orphaned_users(runner) == 0
        assert runner.user_greenlets.calls == []


def test_idle_runner_without_users_is_unchanged():
    runner = FakeRunner("stopped", 0)

    assert reap_orphaned_users(runner) == 0
    assert runner.user_greenlets.calls == []


def test_distributed_runner_without_local_greenlets_is_ignored():
    runner = FakeRunner("stopped", 1, with_group=False)

    assert reap_orphaned_users(runner) == 0
