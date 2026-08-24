from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.call import Call
from app.models.call_event import CallEvent
from app.models.enums import Module


class CampaignCreateRequest(BaseModel):
    name: str
    module: Module
    agent_id: str
    meta: dict[str, Any] = {}


class CallCreateRequest(BaseModel):
    campaign_id: UUID | None = None
    agent_id: str | None = None
    callee_name: str
    mobile_number: str
    custom_data: dict[str, Any] = {}


class CallDetailResponse(BaseModel):
    call: Call
    events: list[CallEvent]
