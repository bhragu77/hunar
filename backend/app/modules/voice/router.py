from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session
from app.models.call import Call
from app.models.campaign import Campaign
from app.providers.base import Agent, PhoneNumber, ProviderError, VoiceProvider
from app.providers.factory import get_voice_provider
from app.schemas.voice import CallCreateRequest, CallDetailResponse, CampaignCreateRequest
from app.services import calls as calls_service
from app.services import campaigns as campaigns_service

router = APIRouter(tags=["voice"])

SessionDep = Annotated[Session, Depends(get_session)]
ProviderDep = Annotated[VoiceProvider, Depends(get_voice_provider)]


@router.get("/agents", response_model=list[Agent])
def list_agents(provider: ProviderDep) -> list[Agent]:
    """Return the configured voice provider's agents. Proves provider wiring end-to-end."""
    return provider.list_agents()


@router.get("/numbers", response_model=list[PhoneNumber])
def list_numbers(provider: ProviderDep) -> list[PhoneNumber]:
    return provider.list_numbers()


@router.post("/campaigns", response_model=Campaign)
def create_campaign(req: CampaignCreateRequest, session: SessionDep, provider: ProviderDep) -> Campaign:
    try:
        agent = provider.get_agent(req.agent_id)
    except ProviderError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    return campaigns_service.create_campaign(session, name=req.name, module=req.module, agent=agent, meta=req.meta)


@router.get("/campaigns", response_model=list[Campaign])
def list_campaigns(session: SessionDep) -> list[Campaign]:
    return campaigns_service.list_campaigns(session)


@router.get("/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: UUID, session: SessionDep) -> Campaign:
    campaign = campaigns_service.get_campaign(session, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/calls", response_model=Call)
def create_call(req: CallCreateRequest, session: SessionDep, provider: ProviderDep) -> Call:
    agent_id = req.agent_id
    campaign = None

    if req.campaign_id is not None:
        campaign = campaigns_service.get_campaign(session, req.campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        agent_id = campaign.agent_id

    if agent_id is None:
        raise HTTPException(status_code=422, detail="agent_id is required when campaign_id is not set")

    try:
        return calls_service.create_call(
            session,
            provider,
            agent_id=agent_id,
            callee_name=req.callee_name,
            mobile_number=req.mobile_number,
            custom_data=req.custom_data,
            campaign_id=campaign.id if campaign else None,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc


@router.get("/calls", response_model=list[Call])
def list_calls(session: SessionDep, campaign_id: UUID | None = None) -> list[Call]:
    return calls_service.list_calls(session, campaign_id=campaign_id)


@router.get("/calls/{call_id}", response_model=CallDetailResponse)
def get_call(call_id: UUID, session: SessionDep) -> CallDetailResponse:
    result = calls_service.get_call_with_events(session, call_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Call not found")
    call, events = result
    return CallDetailResponse(call=call, events=events)
