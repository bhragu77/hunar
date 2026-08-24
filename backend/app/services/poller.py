import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models.call import Call
from app.models.enums import CallEventSource
from app.providers.base import ProviderError
from app.providers.factory import get_voice_provider
from app.services.calls import CallUpdate, apply_call_update, provider_call_to_update

logger = logging.getLogger("app.services.poller")

_TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


def poll_stale_calls() -> None:
    """APScheduler job: reconcile any non-terminal call whose last known update is older than
    POLL_STALE_AFTER_SECONDS against the provider's current view. This is the fallback path -
    it converges to exactly the same state a webhook would have produced, via the same
    apply_call_update function.
    """
    provider = get_voice_provider()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.POLL_STALE_AFTER_SECONDS)

    with Session(engine) as session:
        stmt = select(Call).where(
            Call.status.not_in(_TERMINAL_STATUSES),
            Call.provider_call_id.is_not(None),
            Call.updated_at < cutoff,
        )
        stale_calls = list(session.exec(stmt).all())

        for call in stale_calls:
            try:
                provider_call = provider.get_call(call.provider_call_id)
            except ProviderError:
                logger.warning("Poll failed for call %s", call.id, exc_info=True)
                continue

            update: CallUpdate = provider_call_to_update(provider_call, event_type="poll_snapshot")
            apply_call_update(session, update, source=CallEventSource.poll)
