import random

from app.core.config import settings
from app.integrations.people_search.base import PeopleSearchProvider, SearchCriteria, SourcedProfile

_FIRST_NAMES = [
    "Aarav",
    "Vivaan",
    "Isha",
    "Ananya",
    "Priya",
    "Rohan",
    "Kabir",
    "Diya",
    "Aditi",
    "Karan",
    "Sara",
    "Ethan",
    "Olivia",
    "Liam",
    "Noah",
    "Emma",
    "Maya",
    "Arjun",
    "Neha",
    "Rahul",
]

_LAST_NAMES = [
    "Sharma",
    "Verma",
    "Patel",
    "Iyer",
    "Nair",
    "Gupta",
    "Reddy",
    "Khanna",
    "Mehta",
    "Chatterjee",
    "Smith",
    "Johnson",
    "Brown",
    "Fernandes",
    "Rao",
    "Malhotra",
]

_COMPANIES = [
    "Northwind Systems",
    "BluePeak Technologies",
    "Everstone Digital",
    "Cobalt Analytics",
    "Vertex Labs",
    "Skyline Software",
    "Meridian Cloud",
    "Fusion Works",
    "Orbit Consulting",
    "Zenith Data",
]

_FALLBACK_LOCATIONS = [
    "Bengaluru, India",
    "Mumbai, India",
    "Gurugram, India",
    "Pune, India",
    "Hyderabad, India",
    "Remote",
]


class MockPeopleSearchProvider(PeopleSearchProvider):
    """Generates believable candidate profiles with NO network calls, so the whole People
    Search & Reachout module demos end-to-end with zero external keys.

    Deterministic per (criteria, index): the same criteria always generate the same profile
    set, which is what makes re-running a search over unchanged criteria a true no-op for
    app/services/sourced_candidates.py's dedupe-by-key upsert, while an edited criteria set
    naturally produces a mostly-new set of profiles.
    """

    def search(self, criteria: SearchCriteria, limit: int) -> list[SourcedProfile]:
        limit = limit or settings.PEOPLE_SEARCH_MAX_RESULTS
        seed = "|".join([*criteria.titles, *criteria.locations, *criteria.skills, *criteria.keywords]) or "default"

        profiles: list[SourcedProfile] = []
        for i in range(limit):
            rng = random.Random(f"{seed}::{i}")
            first = rng.choice(_FIRST_NAMES)
            last = rng.choice(_LAST_NAMES)
            title = rng.choice(criteria.titles) if criteria.titles else "Professional"
            location = rng.choice(criteria.locations) if criteria.locations else rng.choice(_FALLBACK_LOCATIONS)
            company = rng.choice(_COMPANIES)

            lo = criteria.min_years if criteria.min_years is not None else 1
            hi = criteria.max_years if criteria.max_years is not None else lo + 6
            years = rng.randint(lo, max(hi, lo))

            # ~15% of sourced profiles have no phone at all - the real-world gap this whole
            # module is designed around (see app/models/sourced_candidate.py).
            has_phone = rng.random() > 0.15
            mobile_number = f"+1{rng.randint(2_000_000_000, 9_999_999_999)}" if has_phone else None

            match_score = round(rng.uniform(0.55, 0.98), 2)
            slug = f"{first.lower()}-{last.lower()}-{i}"

            profiles.append(
                SourcedProfile(
                    full_name=f"{first} {last}",
                    title=title,
                    company=company,
                    location=location,
                    linkedin_url=f"https://www.linkedin.com/in/{slug}",
                    email=f"{first.lower()}.{last.lower()}@{company.lower().replace(' ', '')}.example.com",
                    mobile_number=mobile_number,
                    years_experience=years,
                    raw={"match_score": match_score, "mock_index": i},
                )
            )
        return profiles
