from types import SimpleNamespace

from src.storage import RunStore


def test_run_store_tracks_runs_and_email_attempts(tmp_path):
    store = RunStore(str(tmp_path / "runs.db"))
    result = SimpleNamespace(
        run_id="run-123",
        task="test task",
        status="success",
        sources=[object(), object()],
        duration_seconds=1.25,
        report_markdown="# report",
        errors=[],
    )
    store.save_run(result)
    store.log_email("run-123", "test@example.com", True, "approved by user")

    rows = store.recent_runs()
    metrics = store.metrics()
    assert rows[0]["run_id"] == "run-123"
    assert rows[0]["email_to"] == "test@example.com"
    assert rows[0]["email_sent"] == 1
    assert metrics["total_runs"] == 1
    assert metrics["success_rate_pct"] == 100.0
    assert metrics["emails_sent"] == 1
