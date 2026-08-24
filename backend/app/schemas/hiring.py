from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import PostCallStatus


class InterviewCreateRequest(BaseModel):
    title: str
    description: str | None = None
    agent_id: str
    custom_data_defaults: dict[str, Any] = {}


class CandidateCreateItem(BaseModel):
    callee_name: str
    mobile_number: str
    custom_data: dict[str, Any] = {}


class CandidatesCreateRequest(BaseModel):
    candidates: list[CandidateCreateItem]


class FunnelSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    by_recommendation: dict[str, int]


class InterviewSummary(BaseModel):
    id: UUID
    title: str
    description: str | None
    agent_id: str
    created_at: datetime
    funnel: FunnelSummary


class CandidateSummary(BaseModel):
    """A slim per-candidate row for interview list/detail tables. Full candidate detail
    (transcript, full scorecard, event timeline) reuses GET /api/calls/{id} instead of
    duplicating those fields here."""

    id: UUID
    callee_name: str
    mobile_number: str
    provider_call_id: str | None
    status: str
    lifecycle_status: str | None
    transcript_status: PostCallStatus
    scorecard_status: PostCallStatus
    recommendation: str | None
    overall_score: int | None
    created_at: datetime
    updated_at: datetime


class InterviewDetailResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    agent_id: str
    result_schema: dict[str, Any]
    created_at: datetime
    funnel: FunnelSummary
    candidates: list[CandidateSummary]
