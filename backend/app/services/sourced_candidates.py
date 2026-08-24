import re
from collections.abc import Iterable
from uuid import UUID

from sqlmodel import Session, select

from app.integrations.people_search.base import SourcedProfile
from app.models.sourced_candidate import SourcedCandidate


def make_dedupe_key(full_name: str, company: str | None, linkedin_url: str | None) -> str:
    """A LinkedIn URL is the strongest identity signal when present; otherwise fall back to
    normalized name+company. Used to make re-running a search over unchanged criteria append
    only genuinely new candidates instead of duplicating existing rows."""
    if linkedin_url:
        return f"li:{linkedin_url.strip().lower()}"
    normalized_name = re.sub(r"\s+", " ", full_name.strip().lower())
    normalized_company = re.sub(r"\s+", " ", (company or "").strip().lower())
    return f"nc:{normalized_name}|{normalized_company}"


def upsert_sourced_candidates(
    session: Session, *, campaign_id: UUID, profiles: Iterable[SourcedProfile], source: str
) -> list[SourcedCandidate]:
    """Insert only the profiles not already sourced for this campaign (by dedupe_key); leave
    existing rows untouched so re-searching never clobbers a candidate's selection/dispatch
    state. Returns ALL of the campaign's candidates, old and new."""
    existing = list_candidates(session, campaign_id)
    seen_keys = {c.dedupe_key for c in existing}

    for profile in profiles:
        dedupe_key = make_dedupe_key(profile.full_name, profile.company, profile.linkedin_url)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        session.add(
            SourcedCandidate(
                campaign_id=campaign_id,
                full_name=profile.full_name,
                title=profile.title,
                company=profile.company,
                location=profile.location,
                linkedin_url=profile.linkedin_url,
                email=profile.email,
                mobile_number=profile.mobile_number,
                years_experience=profile.years_experience,
                match_score=_extract_match_score(profile),
                source=source,
                profile_data=profile.raw,
                dedupe_key=dedupe_key,
            )
        )

    session.commit()
    return list_candidates(session, campaign_id)


def _extract_match_score(profile: SourcedProfile) -> float | None:
    value = (profile.raw or {}).get("match_score")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def list_candidates(session: Session, campaign_id: UUID) -> list[SourcedCandidate]:
    stmt = (
        select(SourcedCandidate)
        .where(SourcedCandidate.campaign_id == campaign_id)
        .order_by(SourcedCandidate.created_at)
    )
    return list(session.exec(stmt).all())


def get_candidate(session: Session, candidate_id: UUID) -> SourcedCandidate | None:
    return session.get(SourcedCandidate, candidate_id)


def set_selected(session: Session, candidate_ids: list[UUID], *, selected: bool) -> list[SourcedCandidate]:
    updated: list[SourcedCandidate] = []
    for candidate_id in candidate_ids:
        candidate = session.get(SourcedCandidate, candidate_id)
        if candidate is None:
            continue
        candidate.selected = selected
        session.add(candidate)
        updated.append(candidate)
    session.commit()
    for candidate in updated:
        session.refresh(candidate)
    return updated
