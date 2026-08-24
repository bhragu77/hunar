from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.db import get_session
from app.modules.people_search.router import campaign_summary_response
from app.schemas.outreach import OutreachOverviewResponse
from app.services import outreach as outreach_service

# Read-only executive overview aggregating ALL outreach campaigns - the CRUD lives in
# app/modules/people_search/router.py, which shares the same /api/outreach prefix.
router = APIRouter(prefix="/outreach", tags=["outreach"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/overview", response_model=OutreachOverviewResponse)
def get_overview(session: SessionDep) -> OutreachOverviewResponse:
    campaigns = outreach_service.list_outreach_campaigns(session)
    summaries = [campaign_summary_response(session, c) for c in campaigns]

    totals: dict[str, int] = {}
    total_candidates = 0
    for summary in summaries:
        total_candidates += summary.funnel.total
        for bucket, count in summary.funnel.counts.items():
            totals[bucket] = totals.get(bucket, 0) + count

    return OutreachOverviewResponse(total_candidates=total_candidates, totals=totals, campaigns=summaries)
