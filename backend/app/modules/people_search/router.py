import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import get_session
from app.integrations.people_search.base import (
    PeopleSearchError,
    PeopleSearchProvider,
    SearchCriteria,
)
from app.integrations.people_search.factory import get_people_search_provider
from app.models.call import Call
from app.models.campaign import Campaign
from app.models.sourced_candidate import SourcedCandidate
from app.providers.base import Agent, AgentSpec, ProviderError, VoiceProvider
from app.providers.factory import get_voice_provider
from app.schemas.outreach import (
    AgentSetRequest,
    CandidateDispatchRequest,
    CandidatePatchRequest,
    CandidateSelectRequest,
    CriteriaUpdateRequest,
    DispatchResult,
    OutreachCampaignCreateRequest,
    OutreachCampaignDetail,
    OutreachCampaignSummary,
    OutreachFunnelSummary,
    SourcedCandidateOut,
)
from app.services import calls as calls_service
from app.services import outreach as outreach_service
from app.services import sourced_candidates as sourced_candidates_service
from app.services.agent_designer import design_outreach_agent
from app.services.jd_parser import parse_jd_to_criteria

logger = logging.getLogger("app.modules.people_search")

# Module 2 - People Search & Reachout. An outreach campaign IS a Campaign with
# module="outreach"; a contacted candidate's call IS a Call under it. Dispatch goes through
# the same calls_service used everywhere else; nothing here reimplements webhook/poll
# handling. Registered under /api/outreach (see app/modules/outreach/router.py for the
# read-only cross-campaign overview that lives alongside this one).
router = APIRouter(prefix="/outreach", tags=["outreach", "people-search"])

SessionDep = Annotated[Session, Depends(get_session)]
ProviderDep = Annotated[VoiceProvider, Depends(get_voice_provider)]
PeopleSearchDep = Annotated[PeopleSearchProvider, Depends(get_people_search_provider)]


def _calls_by_id(session: Session, candidates: list[SourcedCandidate]) -> dict[UUID, Call]:
    call_ids = [c.call_id for c in candidates if c.call_id is not None]
    if not call_ids:
        return {}
    return {call.id: call for call in session.exec(select(Call).where(Call.id.in_(call_ids)))}


def _candidate_out(candidate: SourcedCandidate, call: Call | None) -> SourcedCandidateOut:
    return SourcedCandidateOut(
        id=candidate.id,
        campaign_id=candidate.campaign_id,
        full_name=candidate.full_name,
        title=candidate.title,
        company=candidate.company,
        location=candidate.location,
        linkedin_url=candidate.linkedin_url,
        email=candidate.email,
        mobile_number=candidate.mobile_number,
        years_experience=candidate.years_experience,
        match_score=candidate.match_score,
        source=candidate.source,
        selected=candidate.selected,
        call_id=candidate.call_id,
        call_status=call.status if call else None,
        bucket=outreach_service.outreach_bucket(candidate, call),
        created_at=candidate.created_at,
    )


def campaign_summary_response(session: Session, campaign: Campaign) -> OutreachCampaignSummary:
    """Shared by this router's list endpoint and app/modules/outreach/router.py's aggregate
    overview, so the two never compute a campaign's funnel differently."""
    funnel = outreach_service.funnel_summary(session, campaign)
    total = funnel.pop("total")
    meta = campaign.meta or {}
    return OutreachCampaignSummary(
        id=campaign.id,
        title=campaign.name,
        job_description=campaign.description,
        agent_id=campaign.agent_id,
        agent_autocreated=bool(meta.get("agent_autocreated")),
        agent_create_error=meta.get("agent_create_error"),
        created_at=campaign.created_at,
        funnel=OutreachFunnelSummary(total=total, counts=funnel),
    )


def _campaign_detail(session: Session, campaign: Campaign) -> OutreachCampaignDetail:
    meta = campaign.meta or {}
    criteria = SearchCriteria(**(meta.get("search_criteria") or {}))
    agent_spec = AgentSpec(**(meta.get("agent_spec") or {}))

    candidates = sourced_candidates_service.list_candidates(session, campaign.id)
    calls_by_id = _calls_by_id(session, candidates)
    candidate_outs = [_candidate_out(c, calls_by_id.get(c.call_id)) for c in candidates]

    funnel = outreach_service.funnel_summary(session, campaign)
    total = funnel.pop("total")

    return OutreachCampaignDetail(
        id=campaign.id,
        title=campaign.name,
        job_description=campaign.description,
        criteria=criteria,
        agent_id=campaign.agent_id,
        agent_spec=agent_spec,
        agent_autocreated=bool(meta.get("agent_autocreated")),
        agent_create_error=meta.get("agent_create_error"),
        result_schema=campaign.result_schema,
        created_at=campaign.created_at,
        funnel=OutreachFunnelSummary(total=total, counts=funnel),
        candidates=candidate_outs,
    )


def _autocreate_agent(provider: VoiceProvider, agent_spec: AgentSpec) -> tuple[Agent | None, str | None]:
    if not settings.AGENT_AUTOCREATE:
        return None, None
    try:
        return provider.create_agent(agent_spec), None
    except ProviderError as exc:
        return None, exc.message
    except Exception as exc:  # a misbehaving provider must never break campaign creation
        logger.exception("Unexpected error auto-creating outreach agent")
        return None, str(exc)


@router.post("/campaigns", response_model=OutreachCampaignDetail)
def create_campaign(req: OutreachCampaignCreateRequest, session: SessionDep, provider: ProviderDep) -> OutreachCampaignDetail:
    criteria = parse_jd_to_criteria(req.job_description)
    agent_spec = design_outreach_agent(req.job_description, req.title)
    agent, agent_create_error = _autocreate_agent(provider, agent_spec)

    campaign = outreach_service.create_outreach_campaign(
        session,
        title=req.title,
        job_description=req.job_description,
        criteria=criteria,
        agent_spec=agent_spec,
        agent=agent,
        agent_create_error=agent_create_error,
    )
    return _campaign_detail(session, campaign)


@router.get("/campaigns", response_model=list[OutreachCampaignSummary])
def list_campaigns(session: SessionDep) -> list[OutreachCampaignSummary]:
    campaigns = outreach_service.list_outreach_campaigns(session)
    return [campaign_summary_response(session, c) for c in campaigns]


@router.get("/campaigns/{campaign_id}", response_model=OutreachCampaignDetail)
def get_campaign(campaign_id: UUID, session: SessionDep) -> OutreachCampaignDetail:
    campaign = outreach_service.get_outreach_campaign(session, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Outreach campaign not found")
    return _campaign_detail(session, campaign)


@router.patch("/campaigns/{campaign_id}/criteria", response_model=OutreachCampaignDetail)
def update_criteria(campaign_id: UUID, req: CriteriaUpdateRequest, session: SessionDep) -> OutreachCampaignDetail:
    campaign = outreach_service.get_outreach_campaign(session, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Outreach campaign not found")
    campaign = outreach_service.update_campaign_criteria(session, campaign, req.criteria)
    return _campaign_detail(session, campaign)


@router.post("/campaigns/{campaign_id}/agent", response_model=OutreachCampaignDetail)
def set_or_regenerate_agent(
    campaign_id: UUID,
    req: AgentSetRequest,
    session: SessionDep,
    provider: ProviderDep,
    regenerate: bool = False,
) -> OutreachCampaignDetail:
    campaign = outreach_service.get_outreach_campaign(session, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Outreach campaign not found")

    if regenerate:
        agent_spec = design_outreach_agent(campaign.description or "", campaign.name)
        agent, agent_create_error = _autocreate_agent(provider, agent_spec)
        campaign = outreach_service.apply_agent_to_campaign(
            session, campaign, agent=agent, agent_spec=agent_spec, agent_create_error=agent_create_error
        )
        return _campaign_detail(session, campaign)

    if not req.agent_id:
        raise HTTPException(status_code=422, detail="agent_id is required unless regenerate=true")
    try:
        agent = provider.get_agent(req.agent_id)
    except ProviderError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc

    campaign = outreach_service.apply_agent_to_campaign(session, campaign, agent=agent, agent_create_error=None)
    return _campaign_detail(session, campaign)


@router.post("/campaigns/{campaign_id}/search", response_model=list[SourcedCandidateOut])
def search_candidates(
    campaign_id: UUID, session: SessionDep, people_search: PeopleSearchDep
) -> list[SourcedCandidateOut]:
    campaign = outreach_service.get_outreach_campaign(session, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Outreach campaign not found")

    criteria = SearchCriteria(**((campaign.meta or {}).get("search_criteria") or {}))
    try:
        profiles = people_search.search(criteria, settings.PEOPLE_SEARCH_MAX_RESULTS)
    except PeopleSearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    candidates = sourced_candidates_service.upsert_sourced_candidates(
        session, campaign_id=campaign.id, profiles=profiles, source=settings.PEOPLE_SEARCH_PROVIDER
    )
    calls_by_id = _calls_by_id(session, candidates)
    return [_candidate_out(c, calls_by_id.get(c.call_id)) for c in candidates]


@router.post("/candidates/select", response_model=list[SourcedCandidateOut])
def select_candidates(req: CandidateSelectRequest, session: SessionDep) -> list[SourcedCandidateOut]:
    updated = sourced_candidates_service.set_selected(session, req.candidate_ids, selected=req.selected)
    calls_by_id = _calls_by_id(session, updated)
    return [_candidate_out(c, calls_by_id.get(c.call_id)) for c in updated]


@router.patch("/candidates/{candidate_id}", response_model=SourcedCandidateOut)
def update_candidate(candidate_id: UUID, req: CandidatePatchRequest, session: SessionDep) -> SourcedCandidateOut:
    candidate = sourced_candidates_service.get_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(candidate, field, value)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)

    call = session.get(Call, candidate.call_id) if candidate.call_id else None
    return _candidate_out(candidate, call)


def _dispatch_one(session: Session, provider: VoiceProvider, campaign: Campaign, candidate: SourcedCandidate) -> Call:
    call = calls_service.create_draft_call(
        session,
        campaign_id=campaign.id,
        callee_name=candidate.full_name,
        mobile_number=candidate.mobile_number,
        custom_data={
            "role_title": campaign.name,
            "candidate_title": candidate.title or "",
            "candidate_company": candidate.company or "",
        },
    )
    try:
        call = calls_service.dispatch_call(session, provider, call, agent_id=campaign.agent_id)
    except ProviderError as exc:
        logger.warning("Dispatch failed for candidate %s: %s", candidate.id, exc.message)
        call = session.get(Call, call.id)  # already persisted as FAILED by dispatch_call

    candidate.call_id = call.id
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return call


@router.post("/campaigns/{campaign_id}/dispatch", response_model=DispatchResult)
def dispatch_campaign(campaign_id: UUID, session: SessionDep, provider: ProviderDep) -> DispatchResult:
    campaign = outreach_service.get_outreach_campaign(session, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Outreach campaign not found")
    if not campaign.agent_id:
        raise HTTPException(status_code=422, detail="Campaign has no agent set; assign or regenerate one first")

    dispatched: list[UUID] = []
    skipped_no_phone: list[UUID] = []
    for candidate in sourced_candidates_service.list_candidates(session, campaign.id):
        if not candidate.selected or candidate.call_id is not None:
            continue
        if not candidate.mobile_number:
            skipped_no_phone.append(candidate.id)
            continue
        _dispatch_one(session, provider, campaign, candidate)
        dispatched.append(candidate.id)

    return DispatchResult(dispatched=dispatched, skipped_no_phone=skipped_no_phone)


@router.post("/candidates/{candidate_id}/dispatch", response_model=SourcedCandidateOut)
def dispatch_candidate(
    candidate_id: UUID, req: CandidateDispatchRequest, session: SessionDep, provider: ProviderDep
) -> SourcedCandidateOut:
    candidate = sourced_candidates_service.get_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    campaign = outreach_service.get_outreach_campaign(session, candidate.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=422, detail="Candidate has no associated outreach campaign")
    if not campaign.agent_id:
        raise HTTPException(status_code=422, detail="Campaign has no agent set; assign or regenerate one first")

    if req.mobile_number:
        candidate.mobile_number = req.mobile_number
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

    if not candidate.mobile_number:
        raise HTTPException(status_code=422, detail="Candidate has no phone number; provide one to dispatch")

    if candidate.call_id is not None:
        call = session.get(Call, candidate.call_id)
        try:
            call = calls_service.dispatch_call(session, provider, call, agent_id=campaign.agent_id)
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=exc.message) from exc
    else:
        call = _dispatch_one(session, provider, campaign, candidate)

    return _candidate_out(candidate, call)
