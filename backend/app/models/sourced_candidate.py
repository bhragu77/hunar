from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourcedCandidate(SQLModel, table=True):
    """One candidate profile sourced for an outreach campaign via a people-search provider.

    Dispatch links a candidate to a Call under the same campaign via call_id - the candidate's
    funnel bucket is always DERIVED from that Call's live state (see app/services/outreach.py),
    never stored here, so it can never drift out of sync with the call's actual progress.
    """

    __tablename__ = "sourced_candidate"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    campaign_id: UUID = Field(foreign_key="campaign.id", index=True)

    full_name: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    # Nullable: people-search APIs frequently don't return phones (or gate them behind paid
    # enrichment) - a profile without one is "sourced but not dispatchable" until filled in.
    mobile_number: str | None = None
    years_experience: int | None = None
    match_score: float | None = None
    source: str  # "mock" | "apollo" | "pdl"
    profile_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    selected: bool = False
    call_id: UUID | None = Field(default=None, foreign_key="call.id")
    # Normalized name+company, or linkedin_url when present - lets a repeated search append
    # only genuinely new profiles instead of duplicating existing candidates.
    dedupe_key: str = Field(index=True)

    created_at: datetime = Field(default_factory=_utcnow)
