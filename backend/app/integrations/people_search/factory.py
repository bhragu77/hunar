from functools import lru_cache

from app.core.config import settings
from app.integrations.people_search.apollo import ApolloProvider
from app.integrations.people_search.base import PeopleSearchProvider
from app.integrations.people_search.mock import MockPeopleSearchProvider
from app.integrations.people_search.pdl import PDLProvider


@lru_cache
def get_people_search_provider() -> PeopleSearchProvider:
    """Return the configured PeopleSearchProvider singleton, chosen by
    settings.PEOPLE_SEARCH_PROVIDER. Cached since every provider here is stateless."""
    if settings.PEOPLE_SEARCH_PROVIDER == "mock":
        return MockPeopleSearchProvider()
    if settings.PEOPLE_SEARCH_PROVIDER == "apollo":
        return ApolloProvider()
    if settings.PEOPLE_SEARCH_PROVIDER == "pdl":
        return PDLProvider()
    raise ValueError(f"Unknown PEOPLE_SEARCH_PROVIDER: {settings.PEOPLE_SEARCH_PROVIDER!r}")
