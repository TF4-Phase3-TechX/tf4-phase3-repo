from datetime import datetime, timedelta, timezone

from app.rca_episode import RCAEpisodeTracker


def test_breach_onset_is_recorded_before_sustained_anomaly():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    tracker = RCAEpisodeTracker(analysis_window_seconds=180)
    tracker.observe("payment", anomalous=False, breached=True, at=t0)
    tracker.observe(
        "payment",
        anomalous=True,
        breached=True,
        at=t0 + timedelta(seconds=45),
    )
    assert tracker.first_onset("payment") == t0


def test_recovered_service_remains_until_deterministic_expiry():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    tracker = RCAEpisodeTracker(analysis_window_seconds=60)
    tracker.observe("payment", anomalous=True, breached=True, at=t0)
    tracker.observe(
        "payment",
        anomalous=False,
        breached=False,
        at=t0 + timedelta(seconds=10),
    )
    assert tracker.recent_affected(t0 + timedelta(seconds=59)) == ["payment"]
    assert tracker.recent_affected(t0 + timedelta(seconds=61)) == []
