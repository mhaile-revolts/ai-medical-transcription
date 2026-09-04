from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from src.backend.config import settings
from src.backend.main import app
from src.backend.services.ehr.smart_fhir_service import SmartFHIRService, SmartFHIRUnavailable


def configure(monkeypatch) -> None:
    values = {
        "app_mode": "durable",
        "app_env": "test",
        "ochin_smart_fhir_base_url": "https://fhir.example.test",
        "ochin_smart_issuer": "https://issuer.example.test",
        "ochin_smart_client_id": "client",
        "ochin_smart_redirect_uri": "https://api.example.test/api/v1/ehr/smart/callback",
        "ochin_smart_authorize_url": "https://issuer.example.test/authorize",
        "ochin_smart_token_url": "https://issuer.example.test/token",
        "ochin_smart_jwks_url": "https://issuer.example.test/jwks",
        "ochin_smart_revoke_url": "https://issuer.example.test/revoke",
        "ochin_smart_scopes": "openid fhirUser offline_access patient/Patient.read patient/Encounter.read",
        "ochin_smart_required_scopes": "openid fhirUser patient/Patient.read patient/Encounter.read",
        "smart_token_encryption_key": "unit-test-key",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


@pytest.mark.asyncio
async def test_pkce_callback_binds_tenant_clinician_and_uses_bearer(monkeypatch) -> None:
    configure(monkeypatch)
    seen: list[httpx.Request] = []
    nonce = ""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/token":
            token = jwt.encode(
                {"iss": settings.ochin_smart_issuer, "aud": settings.ochin_smart_client_id,
                 "nonce": nonce, "exp": 4102444800,
                 "fhirUser": "https://fhir.example.test/Practitioner/practitioner-7"},
                "not-used-but-long-enough-for-unit-tests", algorithm="HS256",
            )
            return httpx.Response(200, json={
                "access_token": "access-secret", "refresh_token": "refresh-secret", "id_token": token,
                "expires_in": 300, "scope": settings.ochin_smart_scopes,
            })
        if request.url.path.endswith("/Practitioner/practitioner-7"):
            assert request.headers["authorization"] == "Bearer access-secret"
            return httpx.Response(200, json={"resourceType": "Practitioner", "id": "practitioner-7"})
        if request.url.path.endswith("/Patient/patient-1"):
            assert request.headers["authorization"] == "Bearer access-secret"
            return httpx.Response(200, json={"resourceType": "Patient", "id": "patient-1", "name": [{"text": "Test Patient"}]})
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = SmartFHIRService(client)
        authorization_url = service.begin_authorization("tenant-a", "clinician-a")
        query = parse_qs(urlparse(authorization_url).query)
        state, nonce = query["state"][0], query["nonce"][0]
        transaction = service._authorizations[state]
        expected = base64.urlsafe_b64encode(hashlib.sha256(transaction.verifier.encode()).digest()).rstrip(b"=").decode()
        assert query["code_challenge"] == [expected]
        await service.complete_authorization(state, "authorization-code")
        assert service.authorization_status("tenant-a", "clinician-a") == {
            "authorized": True, "practitioner_id": "practitioner-7"
        }
        assert service.authorization_status("tenant-b", "clinician-a")["authorized"] is False
        patient = await service.get_patient("patient-1", "tenant-a", "clinician-a")
        assert patient.display_name == "Test Patient"
        body = seen[0].content.decode()
        assert "code_verifier=" in body
        assert "access-secret" not in authorization_url
        with pytest.raises(SmartFHIRUnavailable, match="state"):
            await service.complete_authorization(state, "second-authorization-code")


@pytest.mark.asyncio
async def test_callback_rejects_replayed_or_unknown_state(monkeypatch) -> None:
    configure(monkeypatch)
    async with httpx.AsyncClient() as client:
        service = SmartFHIRService(client)
        with pytest.raises(SmartFHIRUnavailable, match="state"):
            await service.complete_authorization("unknown", "code")


@pytest.mark.parametrize("role", ["admin", "scribe"])
def test_non_clinicians_cannot_access_smart_authorization(role: str) -> None:
    client = TestClient(app)
    response = client.get(
        "/api/v1/ehr/smart/status",
        headers={"X-Test-Subject": f"{role}-smart-test", "X-Test-Tenant": "smart-tenant", "X-Test-Role": role},
    )
    assert response.status_code == 403


def test_clinician_can_check_smart_authorization_status(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_mode", "demo")
    client = TestClient(app)
    response = client.get(
        "/api/v1/ehr/smart/status",
        headers={"X-Test-Subject": "clinician-smart-test", "X-Test-Tenant": "smart-tenant", "X-Test-Role": "clinician"},
    )
    assert response.status_code == 200
    assert response.json()["authorized"] is False


def test_oauth_denial_returns_mobile_failure_instead_of_validation_error() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/ehr/smart/callback?error=access_denied", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].endswith("?status=failed")