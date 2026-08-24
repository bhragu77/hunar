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

logger = logging.getLogger("app.integrations.people_search.apollo")

_APOLLO_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/search"


class ApolloProvider(PeopleSearchProvider):
    """Apollo.io people-search client.

    Apollo's free/base search tier returns profile + company data but generally NOT direct
    dial/mobile numbers or verified emails - those need per-contact enrichment credits, which
    this minimal client does not spend automatically. A profile that comes back without a
    phone is exactly the "sourced but not dispatchable" case app/models/sourced_candidate.py
    is designed around; HR fills the number in manually. Not exercised by the automated test
    suite, since it needs a live key - see the module's manual verification note.
    """

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"X-Api-Key": settings.APOLLO_API_KEY, "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )

    def search(self, criteria: SearchCriteria, limit: int) -> list[SourcedProfile]:
        body: dict[str, Any] = {"page": 1, "per_page": max(1, min(limit, 100))}
        if criteria.titles:
            body["person_titles"] = criteria.titles
        if criteria.locations:
            body["person_locations"] = criteria.locations
        if criteria.seniorities:
            body["person_seniorities"] = criteria.seniorities
        keywords = [*criteria.skills, *criteria.keywords]
        if keywords:
            body["q_keywords"] = " ".join(keywords)

        try:
            response = self._client.post(_APOLLO_SEARCH_URL, json=body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PeopleSearchError(f"Apollo search failed: {exc}") from exc

        people = response.json().get("people", [])
        return [_normalize(person) for person in people[:limit]]


def _normalize(person: dict[str, Any]) -> SourcedProfile:
    organization = person.get("organization") or {}
    full_name = person.get("name") or " ".join(filter(None, [person.get("first_name"), person.get("last_name")]))
    return SourcedProfile(
        full_name=full_name or "Unknown",
        title=person.get("title"),
        company=organization.get("name"),
        location=", ".join(filter(None, [person.get("city"), person.get("state"), person.get("country")])) or None,
        linkedin_url=person.get("linkedin_url"),
        # Only present when the search response happens to include an unlocked contact -
        # otherwise phone/email require a separate paid enrichment call this client doesn't make.
        email=person.get("email"),
        mobile_number=(person.get("phone_numbers") or [None])[0],
        years_experience=None,
        raw=person,
    )
