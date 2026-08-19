from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_request_id, require_role
from app.core.gate_engine import GateRuleValidationError, validate_gate_rules
from app.core.logging_utils import log
from app.models.core import Conference, GateRule, User
from app.schemas.conferences import ConferenceCreateRequest, ConferenceResponse, GateRulesUpdateRequest

router = APIRouter(prefix="/conferences", tags=["conferences"])


@router.get("", response_model=list[ConferenceResponse])
def list_conferences(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Conference).all()


@router.get("/{conference_id}", response_model=ConferenceResponse)
def get_conference(conference_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conf = db.query(Conference).filter(Conference.id == conference_id).first()
    if conf is None:
        raise HTTPException(status_code=404, detail="Conference not found")
    return conf


@router.post("", response_model=ConferenceResponse, status_code=201)
def create_conference(
    payload: ConferenceCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organizer", "platform_admin")),
):
    req_id = get_request_id(request)
    conf = Conference(organizer_id=user.id, **payload.model_dump())
    db.add(conf)
    db.commit()
    db.refresh(conf)
    log.info(req_id, f"conference created id={conf.id} organizer={user.id}")
    return conf


@router.get("/{conference_id}/gate-rules")
def get_gate_rules(
    conference_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organizer", "platform_admin")),
):
    rules = db.query(GateRule).filter(GateRule.conference_id == conference_id).all()
    return [
        {
            "rule_type": r.rule_type,
            "threshold_soft": float(r.threshold_soft) if r.threshold_soft is not None else None,
            "threshold_hard": float(r.threshold_hard) if r.threshold_hard is not None else None,
            "is_hard_gate": r.is_hard_gate,
        }
        for r in rules
    ]


@router.put("/{conference_id}/gate-rules")
def update_gate_rules(
    conference_id: str,
    payload: GateRulesUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organizer", "platform_admin")),
):
    """
    This is where master doc §5.2's constraint is enforced at the API layer:
    an organizer cannot save ai_content_pct/plagiarism_pct as a hard gate,
    ever. Returns 422 with a clear error message per §5.10's error conventions.
    """
    req_id = get_request_id(request)
    conf = db.query(Conference).filter(Conference.id == conference_id).first()
    if conf is None:
        raise HTTPException(status_code=404, detail="Conference not found")

    rules_as_dicts = [r.model_dump() for r in payload.rules]
    try:
        validate_gate_rules(rules_as_dicts)
    except GateRuleValidationError as e:
        log.warn(req_id, f"gate-rule update rejected for conference={conference_id}: {e}")
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "GATE_RULE_INVALID", "message": str(e), "field": "is_hard_gate"}},
        )

    db.query(GateRule).filter(GateRule.conference_id == conference_id).delete()
    for r in payload.rules:
        db.add(GateRule(conference_id=conference_id, **r.model_dump()))
    db.commit()
    log.info(req_id, f"gate rules updated for conference={conference_id} count={len(payload.rules)}")
    return {"status": "ok", "count": len(payload.rules)}
