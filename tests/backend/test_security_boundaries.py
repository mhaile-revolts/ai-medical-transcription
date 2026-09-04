import json
import logging
import stat

import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.backend.config import settings
from src.backend.main import app, _validate_security_configuration
from src.backend.services.audit.service import (
    SecureTimedRotatingFileHandler,
    configure_audit_sink,
)


pytestmark = pytest.mark.asyncio


def identity(subject: str, tenant: str, role: str = "clinician") -> dict[str, str]:
    return {
        "X-Test-Subject": subject,
        "X-Test-Tenant": tenant,
        "X-Test-Role": role,
    }


async def test_cross_tenant_and_clinician_boundaries() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/encounters/",
            json={"patient_id": "security-patient", "title": "Private"},
            headers=identity("clinician-a", "clinic-a"),
        )
        assert created.status_code == status.HTTP_201_CREATED
        encounter_id = created.json()["id"]

        cross_tenant = await client.get(
            f"/api/v1/encounters/{encounter_id}",
            headers=identity("admin-b", "clinic-b", "admin"),
        )
        assert cross_tenant.status_code == status.HTTP_404_NOT_FOUND

        other_clinician = await client.get(
            f"/api/v1/encounters/{encounter_id}",
            headers=identity("clinician-b", "clinic-a"),
        )
        assert other_clinician.status_code == status.HTTP_403_FORBIDDEN

        bypass = await client.get(
            "/api/v1/encounters/?own_only=false",
            headers=identity("clinician-b", "clinic-a"),
        )
        assert bypass.status_code == status.HTTP_200_OK
        assert all(item["id"] != encounter_id for item in bypass.json())


async def test_patient_timeline_and_deletion_are_role_and_tenant_scoped(caplog) -> None:
    patient_id = "delete-me"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/encounters/",
            json={"patient_id": patient_id},
            headers=identity("clinician-owner", "clinic-delete"),
        )
        encounter_id = created.json()["id"]

        denied = await client.get(
            f"/api/v1/patients/{patient_id}/timeline",
            headers=identity("other-clinician", "clinic-delete"),
        )
        assert denied.status_code == status.HTTP_403_FORBIDDEN

        delete_denied = await client.delete(
            f"/api/v1/patients/{patient_id}",
            headers=identity("clinician-owner", "clinic-delete"),
        )
        assert delete_denied.status_code == status.HTTP_403_FORBIDDEN

        with caplog.at_level("INFO", logger="audit"):
            deleted = await client.delete(
                f"/api/v1/patients/{patient_id}",
                headers=identity("clinic-admin", "clinic-delete", "admin"),
            )
        assert deleted.status_code == status.HTTP_204_NO_CONTENT

        missing = await client.get(
            f"/api/v1/encounters/{encounter_id}",
            headers=identity("clinic-admin", "clinic-delete", "admin"),
        )
        assert missing.status_code == status.HTTP_404_NOT_FOUND
        payload = json.loads(caplog.records[-1].message)
        assert payload["action"] == "delete_patient_data"
        assert payload["tenant_id"] == "clinic-delete"
        assert patient_id not in json.dumps(payload.get("extra"))


async def test_production_rejects_header_identity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/encounters/",
            headers=identity("forged", "clinic-forged", "admin"),
        )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_verified_jwt_requires_explicit_tenant_and_role(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setattr(settings, "clerk_jwt_public_key", public_pem)
    monkeypatch.setattr(settings, "clerk_jwks_url", None)
    monkeypatch.setattr(settings, "clerk_issuer", "https://identity.test")
    monkeypatch.setattr(settings, "clerk_audience", None)
    monkeypatch.setattr(settings, "app_env", "production")

    from datetime import datetime, timedelta, timezone

    base_claims = {
        "sub": "signed-user",
        "tenant_id": "signed-clinic",
        "iss": "https://identity.test",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    missing_role = jwt.encode(base_claims, private_key, algorithm="RS256")
    valid = jwt.encode({**base_claims, "role": "admin"}, private_key, algorithm="RS256")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get(
            "/api/v1/encounters/", headers={"Authorization": f"Bearer {missing_role}"}
        )
        allowed = await client.get(
            "/api/v1/encounters/", headers={"Authorization": f"Bearer {valid}"}
        )
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert allowed.status_code == status.HTTP_200_OK


async def test_production_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "app_mode", "demo")
    monkeypatch.setattr(settings, "cors_allow_origins", "*")
    monkeypatch.setattr(settings, "clerk_issuer", None)
    monkeypatch.setattr(settings, "clerk_jwks_url", None)
    monkeypatch.setattr(settings, "clerk_jwt_public_key", None)
    monkeypatch.setattr(settings, "audit_log_path", None)
    with pytest.raises(RuntimeError) as exc:
        _validate_security_configuration()
    message = str(exc.value)
    assert "demo" in message
    assert "CORS" in message
    assert "CLERK" in message
    assert "AUDIT_LOG_PATH" in message


async def test_audit_sink_keeps_exact_retention_and_private_rollover_permissions(
    monkeypatch, tmp_path
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "audit_log_path", audit_path)
    monkeypatch.setattr(settings, "audit_retention_days", 3)
    configure_audit_sink()

    audit_logger = logging.getLogger("audit")
    handler = next(
        item for item in audit_logger.handlers if isinstance(item, SecureTimedRotatingFileHandler)
    )
    assert handler.backupCount == 2
    audit_logger.info('{"action":"permission_test"}')
    handler.doRollover()
    assert stat.S_IMODE(audit_path.stat().st_mode) == 0o600
    for archived in tmp_path.glob("audit.jsonl.*"):
        assert stat.S_IMODE(archived.stat().st_mode) == 0o600
    handler.close()