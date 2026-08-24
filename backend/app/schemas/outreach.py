from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.integrations.people_search.base import SearchCriteria
from app.providers.base import AgentSpec


class OutreachCampaignCreateRequest(BaseModel):
    title: str
    job_description: str


class CriteriaUpdateRequest(BaseModel):
    criteria: SearchCriteria


class AgentSetRequest(BaseModel):
    agent_id: str | None = None


class CandidateSelectRequest(BaseModel):
    candidate_ids: list[UUID]
    selected: bool = True


class CandidatePatchRequest(BaseModel):
    full_name: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    email: str | None = None
    mobile_number: str | None = None


class CandidateDispatchRequest(BaseModel):
    mobile_number: str | None = None


class SourcedCandidateOut(BaseModel):
    id: UUID
    campaign_id: UUID
    full_name: str
    title: str | None
    company: str | None
    location: str | None
    linkedin_url: str | None
    email: str | None
    mobile_number: str | None
    years_experience: int | None
    match_score: float | None
    source: str
    selected: bool
    call_id: UUID | None
    call_status: str | None = None
    bucket: str
    created_at: datetime


class OutreachFunnelSummary(BaseModel):
    total: int
    counts: dict[str, int]


class OutreachCampaignSummary(BaseModel):
    id: UUID
    title: str
    job_description: str | None
    agent_id: str | None
    agent_autocreated: bool
    agent_create_error: str | None
    created_at: datetime
    funnel: OutreachFunnelSummary


class OutreachCampaignDetail(BaseModel):
    id: UUID
    title: str
    job_description: str | None
    criteria: SearchCriteria
    agent_id: str | None
    agent_spec: AgentSpec
    agent_autocreated: bool
    agent_create_error: str | None
    result_schema: dict[str, Any]
    created_at: datetime
    funnel: OutreachFunnelSummary
    candidates: list[SourcedCandidateOut]


class DispatchResult(BaseModel):
    dispatched: list[UUID]
    skipped_no_phone: list[UUID]


class OutreachOverviewResponse(BaseModel):
    total_candidates: int
    totals: dict[str, int]
    campaigns: list[OutreachCampaignSummary]
