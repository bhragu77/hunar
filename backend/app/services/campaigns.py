from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from app.models.campaign import Campaign
from app.models.enums import Module
from app.providers.base import Agent


def create_campaign(
    session: Session,
    *,
    name: str,
    module: Module,
    agent: Agent,
    description: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Campaign:
    """Snapshot the agent's result_schema at creation time, so a campaign's expected result
    shape doesn't silently drift if the agent is edited later."""
    campaign = Campaign(
        name=name,
        description=description,
        module=module,
        agent_id=agent.id,
        result_schema=agent.result_schema,
        status="active",
        meta=meta or {},
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def list_campaigns(session: Session) -> list[Campaign]:
    return list(session.exec(select(Campaign).order_by(Campaign.created_at.desc())).all())


def get_campaign(session: Session, campaign_id: UUID) -> Campaign | None:
    return session.get(Campaign, campaign_id)
