from app.modules.ai.run_registry import AIRunRegistry


def test_ai_run_registry_tracks_phase_revision_and_cancellation():
    registry = AIRunRegistry()
    run = registry.start(kind="analysis", conversation_id="conversation-1", user_id=7, store_id=11)

    preparing = registry.get(run.run_id, user_id=7, store_id=11)
    assert preparing is not None
    assert preparing["phase"] == "preparing"
    assert preparing["revision"] == 0

    streaming = registry.update(run.run_id, event="model", status="running")
    assert streaming is not None
    assert streaming["phase"] == "streaming"
    assert streaming["revision"] == 1
    assert streaming["event_count"] == 1

    assert registry.request_cancel(run.run_id, user_id=7, store_id=11) is True
    stopping = registry.get(run.run_id, user_id=7, store_id=11)
    assert stopping is not None
    assert stopping["phase"] == "stopping"
    assert stopping["cancel_requested"] is True
    assert registry.is_cancelled(run.run_id) is True

    cancelled = registry.finish(run.run_id, phase="cancelled", error="cancelled")
    assert cancelled is not None
    assert cancelled["phase"] == "cancelled"
    assert cancelled["error"] == "cancelled"


def test_ai_run_registry_enforces_user_and_store_scope():
    registry = AIRunRegistry()
    run = registry.start(kind="period-report", conversation_id=None, user_id=3, store_id=9)

    assert registry.get(run.run_id, user_id=4, store_id=9) is None
    assert registry.get(run.run_id, user_id=3, store_id=10) is None
    assert registry.request_cancel(run.run_id, user_id=4, store_id=9) is False
    assert registry.request_cancel(run.run_id, user_id=3, store_id=10) is False
    assert registry.get(run.run_id, user_id=3, store_id=9) is not None


def test_ai_run_registry_marks_final_and_error_events():
    registry = AIRunRegistry()
    completed_run = registry.start(kind="analysis", conversation_id=None, user_id=None, store_id=None)
    completed = registry.update(completed_run.run_id, event="final", status="completed")
    assert completed is not None
    assert completed["phase"] == "complete"

    failed_run = registry.start(kind="analysis", conversation_id=None, user_id=None, store_id=None)
    failed = registry.update(failed_run.run_id, event="error", status="failed", detail="provider timeout")
    assert failed is not None
    assert failed["phase"] == "error"
    assert failed["error"] == "provider timeout"
