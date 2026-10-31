from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import status
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.backend.config import settings
from src.backend.main import app
from src.backend.services.encounters.service import encounter_service


ISSUER = "https://identity.mobile.test"


@pytest.fixture
def mobile_signing_key(monkeypatch, tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setattr(settings, "clerk_jwt_public_key", public_pem)
    monkeypatch.setattr(settings, "clerk_jwks_url", None)
    monkeypatch.setattr(settings, "clerk_issuer", ISSUER)
    monkeypatch.setattr(settings, "clerk_audience", None)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "audio_upload_dir", tmp_path)
    return private_key


def mobile_token(private_key, *, subject: str, tenant: str, expires_in: timedelta) -> str:
    return jwt.encode(
        {
            "sub": subject,
            "tenant_id": tenant,
            "role": "clinician",
            "iss": ISSUER,
            "exp": datetime.now(timezone.utc) + expires_in,
        },
        private_key,
        algorithm="RS256",
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_mobile_bearer_token_cannot_cross_tenants(mobile_signing_key) -> None:
    owner_token = mobile_token(
        mobile_signing_key,
        subject="mobile-owner",
        tenant="mobile-clinic-a",
        expires_in=timedelta(minutes=5),
    )
    other_tenant_token = mobile_token(
        mobile_signing_key,
        subject="mobile-other",
        tenant="mobile-clinic-b",
        expires_in=timedelta(minutes=5),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/encounters/",
            json={"patient_id": "mobile-private"},
            headers=bearer(owner_token),
        )
        assert created.status_code == status.HTTP_201_CREATED

        denied = await client.get(
            f"/api/v1/encounters/{created.json()['id']}",
            headers=bearer(other_tenant_token),
        )

    assert denied.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_mobile_expired_bearer_token_is_rejected(mobile_signing_key) -> None:
    expired_token = mobile_token(
        mobile_signing_key,
        subject="expired-mobile-user",
        tenant="mobile-clinic",
        expires_in=timedelta(minutes=-1),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/encounters/", headers=bearer(expired_token))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_mobile_upload_duplicate_capture_id_returns_original_job(
    mobile_signing_key, monkeypatch
) -> None:
    token = mobile_token(
        mobile_signing_key,
        subject="mobile-idempotent-upload-owner",
        tenant="mobile-idempotent-upload-clinic",
        expires_in=timedelta(minutes=5),
    )
    monkeypatch.setattr(encounter_service, "is_confirmed_recording_allowed", lambda encounter: True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        encounter = await client.post(
            "/api/v1/encounters/",
            json={"patient_id": "patient-upload-lock"},
            headers=bearer(token),
        )
        assert encounter.status_code == status.HTTP_201_CREATED
        request = {
            "files": {"file": ("capture.m4a", b"audio-bytes", "audio/m4a")},
            "params": {"encounter_id": encounter.json()["id"]},
            "headers": {**bearer(token), "Idempotency-Key": "capture-immutable-123"},
        }
        first = await client.post("/api/v1/audio/upload", **request)
        second = await client.post("/api/v1/audio/upload", **request)

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_201_CREATED
    assert second.json()["job"]["id"] == first.json()["job"]["id"]
    assert second.json()["encounter_id"] == encounter.json()["id"]


def test_mobile_websocket_accepts_bearer_and_preserves_tenant(mobile_signing_key) -> None:
    token = mobile_token(
        mobile_signing_key,
        subject="mobile-stream-owner",
        tenant="mobile-stream-clinic",
        expires_in=timedelta(minutes=5),
    )

    client = TestClient(app)
    try:
        with client.websocket_connect(
            "/api/v1/audio/ws",
            headers=bearer(token),
        ) as websocket:
            websocket.send_bytes(b"mobile audio")
            websocket.receive_json()
            websocket.send_text("stop")
            final = websocket.receive_json()
    finally:
        client.close()

    assert final["job"]["tenant_id"] == "mobile-stream-clinic"
    assert final["encounter_id"]


def test_mobile_websocket_keeps_audio_on_the_requested_confirmed_encounter(
    mobile_signing_key, monkeypatch
) -> None:
    """A live client cannot silently receive a new encounter after it locks one."""
    token = mobile_token(
        mobile_signing_key,
        subject="mobile-bound-stream-owner",
        tenant="mobile-bound-stream-clinic",
        expires_in=timedelta(minutes=5),
    )
    monkeypatch.setattr(encounter_service, "is_confirmed_recording_allowed", lambda encounter: True)
    client = TestClient(app)
    try:
        encounter = client.post(
            "/api/v1/encounters/",
            json={"patient_id": "patient-locked-at-capture"},
            headers=bearer(token),
        )
        assert encounter.status_code == status.HTTP_201_CREATED
        encounter_id = encounter.json()["id"]
        with client.websocket_connect(
            f"/api/v1/audio/ws?encounter_id={encounter_id}",
            headers=bearer(token),
        ) as websocket:
            websocket.send_bytes(b"encounter-bound-audio")
            websocket.receive_json()
            websocket.send_text("stop")
            final = websocket.receive_json()
    finally:
        client.close()

    assert final["encounter_id"] == encounter_id


def test_mobile_websocket_retry_reuses_upload_idempotency_claim(
    mobile_signing_key, monkeypatch
) -> None:
    token = mobile_token(
        mobile_signing_key,
        subject="mobile-live-retry-owner",
        tenant="mobile-live-retry-clinic",
        expires_in=timedelta(minutes=5),
    )
    monkeypatch.setattr(encounter_service, "is_confirmed_recording_allowed", lambda encounter: True)
    client = TestClient(app)
    try:
        encounter = client.post(
            "/api/v1/encounters/",
            json={"patient_id": "patient-live-retry"},
            headers=bearer(token),
        )
        assert encounter.status_code == status.HTTP_201_CREATED
        encounter_id = encounter.json()["id"]
        capture_id = "capture-live-retry-immutable-1"

        with client.websocket_connect(
            f"/api/v1/audio/ws?encounter_id={encounter_id}&capture_id={capture_id}",
            headers=bearer(token),
        ) as websocket:
            websocket.send_bytes(b"live-retry-audio")
            websocket.receive_json()
            websocket.send_text("stop")
            final = websocket.receive_json()

        uploaded = client.post(
            "/api/v1/audio/upload",
            params={"encounter_id": encounter_id},
            files={"file": ("retry.m4a", b"live-retry-audio", "audio/m4a")},
            headers={**bearer(token), "Idempotency-Key": capture_id},
        )
    finally:
        client.close()

    assert final["capture_id"] == capture_id
    assert final["encounter_id"] == encounter_id
    assert uploaded.status_code == status.HTTP_201_CREATED
    assert uploaded.json()["job"]["id"] == final["job"]["id"]
    assert uploaded.json()["encounter_id"] == encounter_id


def test_mobile_websocket_rejects_expired_bearer(mobile_signing_key) -> None:
    expired_token = mobile_token(
        mobile_signing_key,
        subject="expired-mobile-stream",
        tenant="mobile-stream-clinic",
        expires_in=timedelta(minutes=-1),
    )

    client = TestClient(app)
    try:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                "/api/v1/audio/ws?encounter_id=00000000-0000-0000-0000-000000000000",
                headers=bearer(expired_token),
            ):
                pass
    finally:
        client.close()

    assert exc.value.code == status.WS_1008_POLICY_VIOLATION


def test_mobile_websocket_cannot_open_cross_tenant_encounter(mobile_signing_key) -> None:
    owner_token = mobile_token(
        mobile_signing_key,
        subject="mobile-ws-owner",
        tenant="mobile-ws-clinic-a",
        expires_in=timedelta(minutes=5),
    )
    other_tenant_token = mobile_token(
        mobile_signing_key,
        subject="mobile-ws-other",
        tenant="mobile-ws-clinic-b",
        expires_in=timedelta(minutes=5),
    )

    client = TestClient(app)
    try:
        encounter = client.post(
            "/api/v1/encounters/",
            json={"patient_id": "mobile-ws-private"},
            headers=bearer(owner_token),
        )
        assert encounter.status_code == status.HTTP_201_CREATED

        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                f"/api/v1/audio/ws?encounter_id={encounter.json()['id']}",
                headers=bearer(other_tenant_token),
            ):
                pass
    finally:
        client.close()

    assert exc.value.code == status.WS_1008_POLICY_VIOLATION