import base64
import hashlib
import hmac
import time

from fastapi.testclient import TestClient

from app.main import app
from app.providers.webhooks import verify_hunar_signature


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "mock"


def test_verify_hunar_signature_known_vector():
    secret = "whsec_test_secret"
    timestamp = str(int(time.time()))
    raw_body = b'{"event": "call.completed"}'

    signed_payload = f"{timestamp}.".encode() + raw_body
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()

    assert verify_hunar_signature(signature, timestamp, raw_body, [secret]) is True

    # wrong signature
    assert verify_hunar_signature("not-the-signature", timestamp, raw_body, [secret]) is False

    # wrong key
    assert verify_hunar_signature(signature, timestamp, raw_body, ["some-other-key"]) is False

    # stale timestamp (>300s old)
    stale_timestamp = str(int(time.time()) - 400)
    assert verify_hunar_signature(signature, stale_timestamp, raw_body, [secret]) is False

    # supports comma-separated signatures, matches the second one
    combined = f"garbage-sig,{signature}"
    assert verify_hunar_signature(combined, timestamp, raw_body, [secret]) is True
