from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.providers.webhooks import verify_hunar_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/hunar")
async def hunar_webhook(request: Request) -> dict[str, bool]:
    """Stub webhook endpoint. Verifies the signature; no event processing yet (Phase 2)."""
    raw_body = await request.body()
    signature_header = request.headers.get("x-hunar-signature", "")
    timestamp_header = request.headers.get("x-hunar-timestamp", "")

    is_valid = verify_hunar_signature(
        signature_header=signature_header,
        timestamp_header=timestamp_header,
        raw_body=raw_body,
        trusted_keys=[settings.HUNAR_API_KEY],
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # TODO(phase2): parse and process the event payload.
    return {"received": True}
