import logging
import re
from typing import Any

from app.core.config import settings
from app.integrations.llm import LLMError, generate_json
from app.integrations.people_search.base import SearchCriteria

logger = logging.getLogger("app.services.jd_parser")

_SYSTEM_PROMPT = (
    "You are an experienced technical recruiter. Extract structured people-search criteria "
    "from a job description. Respond with ONLY a single JSON object matching this exact "
    'shape: {"titles": string[], "seniorities": string[], "skills": string[], '
    '"locations": string[], "industries": string[], "min_years": number|null, '
    '"max_years": number|null, "keywords": string[]}'
)

_TITLE_CANDIDATES = [
    "Software Engineer",
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Engineer",
    "Data Scientist",
    "Data Analyst",
    "Data Engineer",
    "Machine Learning Engineer",
    "DevOps Engineer",
    "Site Reliability Engineer",
    "Cloud Engineer",
    "Security Engineer",
    "Mobile Engineer",
    "QA Automation Engineer",
    "Automation Test Engineer",
    "Automation Engineer",
    "Test Engineer",
    "SDET",
    "QA Engineer",
    "Product Manager",
    "Project Manager",
    "Business Analyst",
    "Sales Executive",
    "Business Development Manager",
    "Account Manager",
    "HR Manager",
    "Recruiter",
    "Talent Acquisition Specialist",
    "Marketing Manager",
    "Content Writer",
    "UI/UX Designer",
    "Customer Success Manager",
    "Operations Manager",
    "Finance Manager",
]

_SENIORITY_WORDS = [
    "intern",
    "trainee",
    "junior",
    "associate",
    "mid-level",
    "senior",
    "lead",
    "principal",
    "staff",
    "director",
    "vp",
    "head",
]

_SKILL_WORDS = [
    "python",
    "java",
    "javascript",
    "typescript",
    "react",
    "node.js",
    "django",
    "fastapi",
    "sql",
    "postgresql",
    "mongodb",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "excel",
    "powerpoint",
    "salesforce",
    "sap",
    "seo",
    "sem",
    "figma",
    "communication",
    "negotiation",
    "stakeholder management",
    "recruitment",
    "sourcing",
]

_LOCATION_WORDS = [
    "bengaluru",
    "bangalore",
    "mumbai",
    "delhi",
    "gurugram",
    "gurgaon",
    "noida",
    "pune",
    "hyderabad",
    "chennai",
    "kolkata",
    "ahmedabad",
    "remote",
    "hybrid",
    "new york",
    "san francisco",
    "london",
]

_YEARS_RANGE_RE = re.compile(r"(\d+)\s*(?:-|to)\s*(\d+)\+?\s*years?", re.IGNORECASE)
_YEARS_MIN_RE = re.compile(r"(\d+)\+?\s*years?", re.IGNORECASE)

# Fallback title extraction when no known title matches: strip common JD lead-ins ("We are
# hiring a...", "Looking for a...") and trailing qualifier clauses ("...with 3 years of...",
# "...based in Pune"), so an unrecognized title still reads like a role name, not a JD dump.
_TITLE_PREFIX_RE = re.compile(r"^(?:we\s*(?:'re|\s+are)?\s+)?(?:hiring|looking\s+for|seeking)\s+(?:an?\s+)?", re.IGNORECASE)
_TITLE_SUFFIX_RE = re.compile(r"\s+(?:with|who|based|for|to|that)\b.*$", re.IGNORECASE)


def parse_jd_to_criteria(job_description: str) -> SearchCriteria:
    """Derive structured search criteria from a free-text job description.

    Uses the real LLM provider when configured; always falls back to deterministic keyword/
    title extraction if that fails, or immediately if LLM_PROVIDER=mock - so this never needs
    a real key to demo the module end to end.
    """
    if settings.LLM_PROVIDER == "mock":
        return _mock_parse(job_description)
    try:
        raw = generate_json(_SYSTEM_PROMPT, job_description)
        return _normalize(raw)
    except LLMError:
        logger.exception("JD parsing LLM call failed; falling back to keyword extraction")
        return _mock_parse(job_description)


def _mock_parse(job_description: str) -> SearchCriteria:
    text = job_description or ""
    lower = text.lower()

    titles = [t for t in _TITLE_CANDIDATES if t.lower() in lower]
    if not titles:
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        trimmed = _TITLE_SUFFIX_RE.sub("", _TITLE_PREFIX_RE.sub("", first_line)).strip()
        titles = [trimmed[:80]] if trimmed else ["Open Role"]

    seniorities = [s for s in _SENIORITY_WORDS if s in lower]
    skills = [s for s in _SKILL_WORDS if s in lower]
    locations = [loc.title() for loc in _LOCATION_WORDS if loc in lower]

    min_years: int | None = None
    max_years: int | None = None
    range_match = _YEARS_RANGE_RE.search(text)
    if range_match:
        min_years, max_years = int(range_match.group(1)), int(range_match.group(2))
    else:
        min_match = _YEARS_MIN_RE.search(text)
        if min_match:
            min_years = int(min_match.group(1))

    keywords = list(dict.fromkeys([*skills, *titles]))[:15] or ["general hiring"]

    return SearchCriteria(
        titles=titles,
        seniorities=seniorities,
        skills=skills,
        locations=locations,
        industries=[],
        min_years=min_years,
        max_years=max_years,
        keywords=keywords,
    )


def _normalize(raw: dict[str, Any]) -> SearchCriteria:
    def _str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value]
        return []

    def _int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return SearchCriteria(
        titles=_str_list(raw.get("titles")) or ["Open Role"],
        seniorities=_str_list(raw.get("seniorities")),
        skills=_str_list(raw.get("skills")),
        locations=_str_list(raw.get("locations")),
        industries=_str_list(raw.get("industries")),
        min_years=_int(raw.get("min_years")),
        max_years=_int(raw.get("max_years")),
        keywords=_str_list(raw.get("keywords")),
    )
