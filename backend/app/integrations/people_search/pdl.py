import logging
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.people_search.base import (
    PeopleSearchError,
    PeopleSearchProvider,
    SearchCriteria,
    SourcedProfile,
)

logger = logging.getLogger("app.integrations.people_search.pdl")

_PDL_SEARCH_URL = "https://api.peopledatalabs.com/v5/person/search"


class PDLProvider(PeopleSearchProvider):
    """People Data Labs person-search client.

    Like Apollo, PDL's base search response frequently omits `mobile_phone`/`work_email` -
    those fields depend on the record's own data coverage. Not exercised by the automated
    test suite, since it needs a live key - see the module's manual verification note.
    """

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"X-Api-Key": settings.PDL_API_KEY, "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )

    def search(self, criteria: SearchCriteria, limit: int) -> list[SourcedProfile]:
        must: list[dict[str, Any]] = []
        if criteria.titles:
            must.append({"terms": {"job_title": [t.lower() for t in criteria.titles]}})
        if criteria.locations:
            must.append({"terms": {"location_name": [loc.lower() for loc in criteria.locations]}})
        if criteria.skills:
            must.append({"terms": {"skills": [s.lower() for s in criteria.skills]}})
        if criteria.min_years is not None:
            must.append({"range": {"inferred_years_experience": {"gte": criteria.min_years}}})
        if criteria.max_years is not None:
            must.append({"range": {"inferred_years_experience": {"lte": criteria.max_years}}})

        query = {"query": {"bool": {"must": must}}} if must else {"query": {"match_all": {}}}
        body = {**query, "size": max(1, min(limit, 100))}

        try:
            response = self._client.post(_PDL_SEARCH_URL, json=body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PeopleSearchError(f"PDL search failed: {exc}") from exc

        records = response.json().get("data", [])
        return [_normalize(record) for record in records[:limit]]


def _normalize(record: dict[str, Any]) -> SourcedProfile:
    phone_numbers = record.get("phone_numbers") or []
    return SourcedProfile(
        full_name=record.get("full_name") or "Unknown",
        title=record.get("job_title"),
        company=record.get("job_company_name"),
        location=record.get("location_name"),
        linkedin_url=record.get("linkedin_url"),
        email=record.get("work_email"),
        mobile_number=phone_numbers[0] if phone_numbers else None,
        years_experience=record.get("inferred_years_experience"),
        raw=record,
    )
