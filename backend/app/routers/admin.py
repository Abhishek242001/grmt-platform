"""
Admin panel API — development_rule.md §7. platform_admin-only throughout.

The maintenance/test-run flow here is intentionally synchronous and simple
for this starter codebase: it shells out to `pytest` and returns the result
in one response. development_rule.md §7.3 specifies live streaming (SSE or
polling) for a large suite — swap the synchronous subprocess.run() below for
a background task + polling/SSE endpoint once the suite is big enough that
"wait for one HTTP response" stops being acceptable (it's fine for the
~20-test starter suite in this codebase; revisit before the suite reaches
the 100-test target).
"""
import subprocess
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_request_id, require_role
from app.core.logging_utils import log
from app.models.core import User
from app.models.platform import AuditLog, FlagFeedback, ModelUsageLog, SystemSetting, TestRun
from app.models.submissions import AIReport

router = APIRouter(prefix="/admin", tags=["admin"])


def _write_audit(db: Session, actor_id: str, action: str, target_type: str | None = None, target_id: str | None = None):
    db.add(AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id))
    db.commit()


@router.get("/models/usage")
def model_usage(db: Session = Depends(get_db), user: User = Depends(require_role("platform_admin"))):
    """development_rule.md §7.1 — per-service usage/performance dashboard data."""
    rows = db.query(ModelUsageLog).order_by(ModelUsageLog.window_end.desc()).limit(50).all()
    by_service: dict[str, dict] = {}
    for r in rows:
        if r.service_name not in by_service:
            by_service[r.service_name] = {
                "service_name": r.service_name,
                "model_version": r.model_version,
                "request_count_24h": 0,
                "error_count_24h": 0,
                "avg_latency_ms": None,
            }
        by_service[r.service_name]["request_count_24h"] += r.request_count
        by_service[r.service_name]["error_count_24h"] += r.error_count

    check_type_counts = db.query(AIReport.check_type, AIReport.flagged).all()
    counts: dict[str, dict[str, int]] = {}
    for check_type, flagged in check_type_counts:
        counts.setdefault(check_type, {"total_checks": 0, "flagged_count": 0})
        counts[check_type]["total_checks"] += 1
        if flagged:
            counts[check_type]["flagged_count"] += 1
    per_check = [{"check_type": ct, **v} for ct, v in counts.items()]
    return {"services": list(by_service.values()), "per_check_type": per_check}


@router.get("/models/false-positive-rate")
def false_positive_rate(db: Session = Depends(get_db), user: User = Depends(require_role("platform_admin"))):
    """
    development_rule.md §7.2 — false-positive rate = incorrect flags / total
    flags with feedback, per check_type. Sample size is returned alongside
    the rate so a tiny sample isn't presented with false confidence.
    """
    rows = db.query(AIReport.check_type, FlagFeedback.was_correct).join(
        FlagFeedback, FlagFeedback.ai_report_id == AIReport.id
    ).all()
    tally: dict[str, dict[str, int]] = {}
    for check_type, was_correct in rows:
        tally.setdefault(check_type, {"correct": 0, "incorrect": 0})
        tally[check_type]["incorrect" if not was_correct else "correct"] += 1

    result = []
    for check_type, counts in tally.items():
        total = counts["correct"] + counts["incorrect"]
        fp_rate = counts["incorrect"] / total if total else None
        result.append({"check_type": check_type, "sample_size": total, "false_positive_rate": fp_rate})
    return {"false_positive_rates": result}


@router.post("/maintenance/start")
def start_maintenance(request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("platform_admin"))):
    req_id = get_request_id(request)
    setting = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
    if setting is None:
        setting = SystemSetting(key="maintenance_mode", value="true")
        db.add(setting)
    else:
        setting.value = "true"
    db.commit()
    _write_audit(db, user.id, "maintenance_start")
    log.info(req_id, f"maintenance mode STARTED by user={user.id}")
    return {"maintenance_mode": True}


@router.post("/maintenance/end")
def end_maintenance(request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("platform_admin"))):
    req_id = get_request_id(request)
    setting = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
    if setting is None:
        setting = SystemSetting(key="maintenance_mode", value="false")
        db.add(setting)
    else:
        setting.value = "false"
    db.commit()
    _write_audit(db, user.id, "maintenance_end")
    log.info(req_id, f"maintenance mode ENDED by user={user.id}")
    return {"maintenance_mode": False}


@router.get("/maintenance/status")
def maintenance_status(db: Session = Depends(get_db)):
    """Unauthenticated on purpose — the frontend needs this to render the maintenance banner for ANY user."""
    setting = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
    return {"maintenance_mode": (setting is not None and setting.value == "true")}


@router.post("/test-run")
def trigger_test_run(request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("platform_admin"))):
    """
    development_rule.md §7.3 step 4-5. Runs the full pytest suite as a
    subprocess and records the result. See module docstring re: this being a
    synchronous starting point, not the final SSE-streaming design.
    """
    req_id = get_request_id(request)
    run = TestRun(triggered_by=user.id, status="running", started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)

    log.info(req_id, f"test run {run.id} started by user={user.id}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", "-q"],
        cwd=".",
        capture_output=True,
        text=True,
        timeout=300,
    )
    passed = "failed" not in result.stdout.lower() and result.returncode == 0

    run.status = "passed" if passed else "failed"
    run.completed_at = datetime.now(timezone.utc)
    run.failure_detail = {"stdout_tail": result.stdout[-4000:], "stderr_tail": result.stderr[-2000:]}
    db.commit()

    log.info(req_id, f"test run {run.id} finished status={run.status}")
    if not passed:
        log.error(req_id, f"test run {run.id} FAILED — see failure_detail", exc=None)

    _write_audit(db, user.id, "test_run", target_type="test_runs", target_id=run.id)
    return {"id": run.id, "status": run.status, "stdout_tail": run.failure_detail["stdout_tail"]}


@router.post("/server/restore")
def restore_server(request: Request, run_id: str, db: Session = Depends(get_db), user: User = Depends(require_role("platform_admin"))):
    """
    development_rule.md §7.3 step 6: bringing the server back up is ALWAYS a
    separate, explicit action from the test run finishing, even if all tests
    passed.
    """
    req_id = get_request_id(request)
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Test run not found")
    run.server_restored_at = datetime.now(timezone.utc)
    run.restored_by = user.id

    setting = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
    if setting:
        setting.value = "false"
    db.commit()

    _write_audit(db, user.id, "server_restore", target_type="test_runs", target_id=run.id)
    log.info(req_id, f"server restored by user={user.id} after test run={run.id}")
    return {"maintenance_mode": False, "restored_by": user.id}
