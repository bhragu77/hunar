from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class PeopleSearchError(Exception):
    """Raised when a PeopleSearchProvider call fails in a way the caller should handle
    explicitly (bad key, rate limit, validation error, ...)."""


class SearchCriteria(BaseModel):
    """Structured search criteria, derived from a JD by app/services/jd_parser.py and editable
    by HR before running a search."""

    titles: list[str] = []
    seniorities: list[str] = []
    skills: list[str] = []
    locations: list[str] = []
    industries: list[str] = []
    min_years: int | None = None
    max_years: int | None = None
    keywords: list[str] = []


class SourcedProfile(BaseModel):
    """A candidate profile normalized to one shape regardless of which provider sourced it.

    `mobile_number`/`email` are nullable on purpose: real people-search APIs frequently don't
    return them (or gate them behind paid enrichment) - see app/models/sourced_candidate.py for
    how a phone-less profile is handled downstream. `raw` keeps the provider's own payload
    (e.g. a mock/apollo match confidence score) for anything not worth promoting to a
    first-class field.
    """

    full_name: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    mobile_number: str | None = None
    years_experience: int | None = None
    raw: dict[str, Any] = {}


class PeopleSearchProvider(ABC):
    """Common interface every people-search provider (mock, Apollo, PDL, ...) must implement."""

    @abstractmethod
    def search(self, criteria: SearchCriteria, limit: int) -> list[SourcedProfile]: ...
