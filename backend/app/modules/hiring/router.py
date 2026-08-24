import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session
from app.models.call import Call
from app.models.campaign import Campaign
from app.models.enums import Module, PostCallStatus
from app.providers.base import ProviderError, VoiceProvider
from app.providers.factory import get_voice_provider
from app.schemas.hiring import (
    CandidatesCreateRequest,
    CandidateSummary,
    FunnelSummary,
    InterviewCreateRequest,
    InterviewDetailResponse,
    InterviewSummary,
)
from app.services import calls as calls_service
from app.services import campaigns as campaigns_service
from app.services import hiring as hiring_service

logger = logging.getLogger("app.modules.hiring")

# The Hiring Assistant module is a thin layer on top of the voice core: an "interview" IS a
# Campaign with module=hiring, a "candidate" IS a Call under it. Dispatch goes through the
# same calls_service used everywhere else; nothing here reimplements webhook/poll handling.
router = APIRouter(prefix="/hiring", tags=["hiring"])

SessionDep = Annotated[Session, Depends(get_session)]
ProviderDep = Annotated[VoiceProvider, Depends(get_voice_provider)]


def _candidate_summary(call: Call) -> CandidateSummary:
    recommendation = None
    overall_score = None
    if call.scorecard_status == PostCallStatus.done and call.scorecard:
        recommendation = call.scorecard.get("recommendation")
        overall_score = call.scorecard.get("overall_score")
    return CandidateSummary(
        id=call.id,
        callee_name=call.callee_name,
        mobile_number=call.mobile_number,
        provider_call_id=call.provider_call_id,
        status=call.status,
        lifecycle_status=call.lifecycle_status,
        transcript_status=call.transcript_status,
        scorecard_status=call.scorecard_status,
        recommendation=recommendation,
        overall_score=overall_score,
        created_at=call.created_at,
        updated_at=call.updated_at,
    )


def _interview_summary(campaign: Campaign, candidates: list[Call]) -> InterviewSummary:
    return InterviewSummary(
        id=campaign.id,
        title=campaign.name,
        description=campaign.description,
        agent_id=campaign.agent_id,
        created_at=campaign.created_at,
        funnel=FunnelSummary(**hiring_service.compute_funnel(candidates)),
    )


@router.post("/interviews", response_model=InterviewSummary)
def create_interview(req: InterviewCreateRequest, session: SessionDep, provider: ProviderDep) -> InterviewSummary:
    try:
        agent = provider.get_agent(req.agent_id)
    except ProviderError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc

    campaign = campaigns_service.create_campaign(
        session,
        name=req.title,
        module=Module.hiring,
        agent=agent,
        description=req.description,
        meta={"custom_data_defaults": req.custom_data_defaults},
    )
    return _interview_summary(campaign, [])


@router.get("/interviews", response_model=list[InterviewSummary])
def list_interviews(session: SessionDep) -> list[InterviewSummary]:
    campaigns = hiring_service.list_interviews(session)
    return [_interview_summary(c, hiring_service.list_candidates(session, c.id)) for c in campaigns]


@router.get("/interviews/{interview_id}", response_model=InterviewDetailResponse)
def get_interview(interview_id: UUID, session: SessionDep) -> InterviewDetailResponse:
    campaign = hiring_service.get_interview(session, interview_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    candidates = hiring_service.list_candidates(session, interview_id)
    return InterviewDetailResponse(
        id=campaign.id,
        title=campaign.name,
        description=campaign.description,
        agent_id=campaign.agent_id,
        result_schema=campaign.result_schema,
        created_at=campaign.created_at,
        funnel=FunnelSummary(**hiring_service.compute_funnel(candidates)),
        candidates=[_candidate_summary(c) for c in candidates],
    )


@router.post("/interviews/{interview_id}/candidates", response_model=list[CandidateSummary])
def add_candidates(
    interview_id: UUID,
    req: CandidatesCreateRequest,
    session: SessionDep,
    provider: ProviderDep,
    dispatch: bool = False,
) -> list[CandidateSummary]:
    campaign = hiring_service.get_interview(session, interview_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    defaults = (campaign.meta or {}).get("custom_data_defaults", {})
    created: list[Call] = []
    for item in req.candidates:
        call = calls_service.create_draft_call(
            session,
            campaign_id=campaign.id,
            callee_name=item.callee_name,
            mobile_number=item.mobile_number,
            custom_data={**defaults, **item.custom_data},
        )
        if dispatch:
            try:
                call = calls_service.dispatch_call(session, provider, call, agent_id=campaign.agent_id)
            except ProviderError as exc:
                logger.warning("Dispatch failed for candidate %s: %s", call.id, exc.message)
        created.append(call)

    return [_candidate_summary(c) for c in created]


@router.post("/candidates/{call_id}/dispatch", response_model=CandidateSummary)
def dispatch_candidate(call_id: UUID, session: SessionDep, provider: ProviderDep) -> CandidateSummary:
    call = session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    campaign = session.get(Campaign, call.campaign_id) if call.campaign_id else None
    if campaign is None:
        raise HTTPException(status_code=422, detail="Candidate has no associated interview")

    try:
        call = calls_service.dispatch_call(session, provider, call, agent_id=campaign.agent_id)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    return _candidate_summary(call)


@router.post("/candidates/{call_id}/rescore", response_model=CandidateSummary)
def rescore_candidate(call_id: UUID, session: SessionDep) -> CandidateSummary:
    call = session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    call.transcript_status = PostCallStatus.pending
    call.transcript_error = None
    call.scorecard_status = PostCallStatus.pending
    call.scorecard_error = None
    session.add(call)
    session.commit()
    session.refresh(call)

    calls_service.schedule_post_processing(call.id)
    return _candidate_summary(call)
