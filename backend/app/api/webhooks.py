import json
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models.enums import CallEventSource
from app.providers.webhooks import verify_hunar_signature
from app.services.calls import CallUpdate, apply_call_update

logger = logging.getLogger("app.api.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/hunar")
async def hunar_webhook(request: Request) -> dict[str, bool]:
    """Real Hunar webhook receiver. Verifies the signature, normalizes the payload into a
    CallUpdate, and hands it to the same apply_call_update the poller uses - so this endpoint
    and the polling fallback always converge on identical state.
    """
    raw_body = await request.body()
    signature_header = request.headers.get("x-hunar-signature", "")
    timestamp_header = request.headers.get("x-hunar-timestamp", "")

    trusted_keys = [settings.HUNAR_API_KEY]
    if settings.VOICE_PROVIDER == "mock":
        trusted_keys.append(settings.MOCK_WEBHOOK_SECRET)

    is_valid = verify_hunar_signature(
        signature_header=signature_header,
        timestamp_header=timestamp_header,
        raw_body=raw_body,
        trusted_keys=trusted_keys,
        tolerance_seconds=settings.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = json.loads(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    call_id = body.get("call_id")
    if not call_id:
        raise HTTPException(status_code=400, detail="Missing call_id in webhook payload")

    update = CallUpdate(
        provider_call_id=call_id,
        request_id=body.get("request_id"),
        event_type=body.get("event_type", "unknown"),
        status=body.get("status", "UNKNOWN"),
        lifecycle_status=body.get("lifecycle_status"),
        engagement_status=body.get("engagement_status"),
        answered_by=body.get("answered_by"),
        call_ended_by=body.get("call_ended_by"),
        recording_url=body.get("recording_url"),
        result=body.get("result"),
        duration_seconds=body.get("duration_seconds"),
        started_at=body.get("started_at"),
        ended_at=body.get("ended_at"),
    )

    with Session(engine) as session:
        call = apply_call_update(session, update, source=CallEventSource.webhook)

    if call is None:
        logger.warning(
            "Webhook received for unknown call (provider_call_id=%s, request_id=%s)",
            call_id,
            update.request_id,
        )

    return {"received": True}
