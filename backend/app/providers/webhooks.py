import base64
import hashlib
import hmac
import time

MAX_TIMESTAMP_SKEW_SECONDS = 300


def _sign(secret: str, timestamp: str, raw_body: bytes) -> str:
    """HMAC-SHA256 over `f"{timestamp}." + raw_body`, base64-encoded."""
    signed_payload = f"{timestamp}.".encode() + raw_body
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def verify_hunar_signature(
    signature_header: str,
    timestamp_header: str,
    raw_body: bytes,
    trusted_keys: list[str],
) -> bool:
    """Verify a Hunar webhook request.

    `signature_header` may contain one or more comma-separated base64 signatures
    (Hunar rotates keys by sending multiple candidates). A request is valid if
    any signature matches any trusted key AND the timestamp is within
    MAX_TIMESTAMP_SKEW_SECONDS of now, which guards against replay attacks.
    """
    try:
        timestamp = int(timestamp_header)
    except (TypeError, ValueError):
        return False

    if abs(time.time() - timestamp) > MAX_TIMESTAMP_SKEW_SECONDS:
        return False

    provided_signatures = [s.strip() for s in signature_header.split(",") if s.strip()]
    if not provided_signatures:
        return False

    for key in trusted_keys:
        expected = _sign(key, timestamp_header, raw_body)
        for provided in provided_signatures:
            if hmac.compare_digest(expected, provided):
                return True

    return False
