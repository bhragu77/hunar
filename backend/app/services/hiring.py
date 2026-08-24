from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from app.models.call import Call
from app.models.campaign import Campaign
from app.models.enums import Module, PostCallStatus


def list_interviews(session: Session) -> list[Campaign]:
    stmt = select(Campaign).where(Campaign.module == Module.hiring).order_by(Campaign.created_at.desc())
    return list(session.exec(stmt).all())


def get_interview(session: Session, interview_id: UUID) -> Campaign | None:
    campaign = session.get(Campaign, interview_id)
    if campaign is None or campaign.module != Module.hiring:
        return None
    return campaign


def list_candidates(session: Session, interview_id: UUID) -> list[Call]:
    stmt = select(Call).where(Call.campaign_id == interview_id).order_by(Call.created_at)
    return list(session.exec(stmt).all())


def compute_funnel(calls: list[Call]) -> dict[str, Any]:
    """Counts by call status and by scorecard recommendation - computed in Python rather
    than a JSON SQL query, since candidate volume per interview is small and this is far
    easier to read and debug."""
    by_status: dict[str, int] = {}
    by_recommendation: dict[str, int] = {}
    for call in calls:
        by_status[call.status] = by_status.get(call.status, 0) + 1
        if call.scorecard_status == PostCallStatus.done and call.scorecard:
            recommendation = call.scorecard.get("recommendation", "unknown")
            by_recommendation[recommendation] = by_recommendation.get(recommendation, 0) + 1
    return {"total": len(calls), "by_status": by_status, "by_recommendation": by_recommendation}
