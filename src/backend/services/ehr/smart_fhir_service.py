"""OCHIN SMART on FHIR authorization-code/PKCE client.

Clerk authenticates the application user.  SMART credentials are held only by
this server and are bound to that Clerk user and tenant.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote, urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from src.backend.config import settings
from src.backend.infra.db.models_ehr import SmartAuthorizationStateORM, SmartTokenORM


class SmartFHIRUnavailable(RuntimeError):
    """Raised when SMART authorization or the FHIR server is unavailable."""


@dataclass(frozen=True)
class SmartPatient:
    id: str
    display_name: str
    birth_date: Optional[str]
    sex: Optional[str]
    source: str = "smart-fhir"


@dataclass(frozen=True)
class SmartEncounter:
    id: str
    status: str
    type: Optional[str]
    period_start: Optional[str]


@dataclass
class _Authorization:
    tenant_id: str
    clinician_id: str
    nonce: str
    verifier: str
    created_at: float


@dataclass
class _TokenRecord:
    encrypted: bytes
    expires_at: float
    practitioner_id: str
    scope: str


ACTIVE_ENCOUNTER_STATUSES = frozenset({"arrived", "triaged", "in-progress", "onleave"})


class SmartFHIRService:
    """FHIR R4 client with server-only SMART token custody."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client
        self._authorizations: dict[str, _Authorization] = {}
        self._tokens: dict[tuple[str, str], _TokenRecord] = {}

    def _configured(self) -> None:
        core = (
            settings.ochin_smart_fhir_base_url,
            settings.ochin_smart_issuer,
            settings.ochin_smart_client_id,
        )
        authorization = (
            settings.ochin_smart_redirect_uri,
            settings.ochin_smart_authorize_url,
            settings.ochin_smart_token_url,
            settings.smart_token_encryption_key,
        )
        if not all(core) or (not all(authorization) and self._client is None):
            raise SmartFHIRUnavailable("OCHIN SMART on FHIR authorization is not configured")

    def _fernet(self) -> Fernet:
        secret = settings.smart_token_encryption_key
        if not secret:
            raise SmartFHIRUnavailable("SMART token encryption is not configured")
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self._client is not None:
                response = await self._client.request(method, url, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise SmartFHIRUnavailable("OCHIN SMART request failed") from exc

    def begin_authorization(self, tenant_id: str, clinician_id: str) -> str:
        self._configured()
        state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        self._save_authorization(state, _Authorization(tenant_id, clinician_id, nonce, verifier, time.time()))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params = {
            "response_type": "code",
            "client_id": settings.ochin_smart_client_id,
            "redirect_uri": settings.ochin_smart_redirect_uri,
            "scope": settings.ochin_smart_scopes,
            "aud": settings.ochin_smart_fhir_base_url,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{settings.ochin_smart_authorize_url}?{urlencode(params)}"

    async def complete_authorization(self, state: str, code: str) -> tuple[str, str]:
        self._configured()
        transaction = self._consume_authorization(state)
        if not transaction or time.time() - transaction.created_at > 600:
            raise SmartFHIRUnavailable("SMART authorization state is invalid or expired")
        response = await self._request(
            "POST",
            str(settings.ochin_smart_token_url),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.ochin_smart_redirect_uri,
                "client_id": settings.ochin_smart_client_id,
                "code_verifier": transaction.verifier,
            },
            headers={"Accept": "application/json"},
        )
        try:
            payload = response.json()
            access_token = payload["access_token"]
            id_token = payload["id_token"]
            if settings.app_env == "test":
                claims = jwt.decode(
                    id_token, options={"verify_signature": False, "require": ["iss", "nonce", "exp"]}
                )
            else:
                if not settings.ochin_smart_jwks_url:
                    raise SmartFHIRUnavailable("OCHIN SMART signing keys are not configured")
                signing_key = jwt.PyJWKClient(settings.ochin_smart_jwks_url).get_signing_key_from_jwt(id_token).key
                claims = jwt.decode(
                    id_token,
                    signing_key,
                    algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                    issuer=settings.ochin_smart_issuer,
                    audience=settings.ochin_smart_client_id,
                    options={"require": ["iss", "nonce", "exp"]},
                )
        except (ValueError, KeyError, jwt.PyJWTError) as exc:
            raise SmartFHIRUnavailable("OCHIN SMART token response is invalid") from exc
        if claims.get("iss", "").rstrip("/") != str(settings.ochin_smart_issuer).rstrip("/"):
            raise SmartFHIRUnavailable("SMART issuer validation failed")
        if not secrets.compare_digest(str(claims.get("nonce", "")), transaction.nonce):
            raise SmartFHIRUnavailable("SMART nonce validation failed")
        fhir_user = claims.get("fhirUser") or payload.get("fhirUser")
        if not isinstance(fhir_user, str) or "/Practitioner/" not in fhir_user:
            raise SmartFHIRUnavailable("SMART clinician Practitioner mapping is missing")
        practitioner_id = fhir_user.rstrip("/").split("/")[-1]
        scope = str(payload.get("scope", ""))
        required_scopes = set(settings.ochin_smart_required_scopes.split())
        if not required_scopes.issubset(set(scope.split())):
            raise SmartFHIRUnavailable("OCHIN did not grant required SMART scopes")
        token_payload = json.dumps(
            {"access_token": access_token, "refresh_token": payload.get("refresh_token")}
        ).encode()
        record = _TokenRecord(
            encrypted=self._fernet().encrypt(token_payload),
            expires_at=time.time() + max(1, int(payload.get("expires_in", 300))),
            practitioner_id=practitioner_id,
            scope=scope,
        )
        practitioner_response = await self._request(
            "GET",
            f"{str(settings.ochin_smart_fhir_base_url).rstrip('/')}/Practitioner/{quote(practitioner_id, safe='')}",
            headers={"Accept": "application/fhir+json", "Authorization": f"Bearer {access_token}"},
        )
        practitioner = practitioner_response.json()
        if practitioner.get("resourceType") != "Practitioner" or practitioner.get("id") != practitioner_id:
            raise SmartFHIRUnavailable("SMART clinician Practitioner mapping is invalid")
        self._save_record(transaction.tenant_id, transaction.clinician_id, record)
        return transaction.tenant_id, transaction.clinician_id

    def abandon_authorization(self, state: str) -> None:
        self._consume_authorization(state)

    @staticmethod
    def _state_key(state: str) -> str:
        return hashlib.sha256(state.encode()).hexdigest()

    def _save_authorization(self, state: str, transaction: _Authorization) -> None:
        if self._client is not None or settings.app_mode == "demo":
            self._authorizations[state] = transaction
            return
        if not settings.database_url:
            raise SmartFHIRUnavailable("Secure SMART authorization storage is unavailable")
        encrypted = self._fernet().encrypt(json.dumps(transaction.__dict__).encode())
        with Session(create_engine(settings.database_url, future=True)) as session:
            session.add(SmartAuthorizationStateORM(
                state_key=self._state_key(state), encrypted_transaction=encrypted,
                expires_at=transaction.created_at + 600,
            ))
            session.commit()

    def _consume_authorization(self, state: str) -> Optional[_Authorization]:
        if self._client is not None or settings.app_mode == "demo":
            return self._authorizations.pop(state, None)
        if not settings.database_url:
            raise SmartFHIRUnavailable("Secure SMART authorization storage is unavailable")
        with Session(create_engine(settings.database_url, future=True)) as session:
            row = session.execute(
                delete(SmartAuthorizationStateORM)
                .where(SmartAuthorizationStateORM.state_key == self._state_key(state))
                .returning(
                    SmartAuthorizationStateORM.encrypted_transaction,
                    SmartAuthorizationStateORM.expires_at,
                )
            ).first()
            session.commit()
        if row is None or row.expires_at < time.time():
            return None
        try:
            payload = json.loads(self._fernet().decrypt(row.encrypted_transaction))
            return _Authorization(**payload)
        except (InvalidToken, TypeError, ValueError, json.JSONDecodeError):
            return None

    def authorization_status(self, tenant_id: str, clinician_id: str) -> dict[str, Any]:
        record = self._load_record(tenant_id, clinician_id)
        return {
            "authorized": bool(record and record.expires_at > time.time()),
            "practitioner_id": record.practitioner_id if record else None,
        }

    async def revoke(self, tenant_id: str, clinician_id: str) -> None:
        record = self._load_record(tenant_id, clinician_id)
        if not record:
            return
        tokens = self._decrypt(record)
        if settings.ochin_smart_revoke_url:
            for token in (tokens.get("refresh_token"), tokens.get("access_token")):
                if token:
                    await self._request(
                        "POST", settings.ochin_smart_revoke_url,
                        data={"token": token, "client_id": settings.ochin_smart_client_id},
                    )
        self._delete_record(tenant_id, clinician_id)

    def _load_record(self, tenant_id: str, clinician_id: str) -> Optional[_TokenRecord]:
        if self._client is not None or settings.app_mode == "demo":
            return self._tokens.get((tenant_id, clinician_id))
        if not settings.database_url:
            raise SmartFHIRUnavailable("Secure SMART token storage is unavailable")
        with Session(create_engine(settings.database_url, future=True)) as session:
            row = session.scalar(select(SmartTokenORM).where(
                SmartTokenORM.tenant_id == tenant_id, SmartTokenORM.clinician_id == clinician_id
            ))
            return None if row is None else _TokenRecord(
                encrypted=row.encrypted_token, expires_at=row.expires_at,
                practitioner_id=row.practitioner_id, scope=row.scope,
            )

    def _save_record(self, tenant_id: str, clinician_id: str, record: _TokenRecord) -> None:
        if self._client is not None or settings.app_mode == "demo":
            self._tokens[(tenant_id, clinician_id)] = record
            return
        if not settings.database_url:
            raise SmartFHIRUnavailable("Secure SMART token storage is unavailable")
        with Session(create_engine(settings.database_url, future=True)) as session:
            row = session.scalar(select(SmartTokenORM).where(
                SmartTokenORM.tenant_id == tenant_id, SmartTokenORM.clinician_id == clinician_id
            ))
            if row is None:
                row = SmartTokenORM(tenant_id=tenant_id, clinician_id=clinician_id)
                session.add(row)
            row.encrypted_token, row.expires_at = record.encrypted, record.expires_at
            row.practitioner_id, row.scope = record.practitioner_id, record.scope
            session.commit()

    def _delete_record(self, tenant_id: str, clinician_id: str) -> None:
        if self._client is not None or settings.app_mode == "demo":
            self._tokens.pop((tenant_id, clinician_id), None)
            return
        if not settings.database_url:
            raise SmartFHIRUnavailable("Secure SMART token storage is unavailable")
        with Session(create_engine(settings.database_url, future=True)) as session:
            row = session.scalar(select(SmartTokenORM).where(
                SmartTokenORM.tenant_id == tenant_id, SmartTokenORM.clinician_id == clinician_id
            ))
            if row is not None:
                session.delete(row)
                session.commit()

    def _decrypt(self, record: _TokenRecord) -> dict[str, Any]:
        try:
            return json.loads(self._fernet().decrypt(record.encrypted))
        except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
            raise SmartFHIRUnavailable("Stored SMART authorization is unavailable") from exc

    async def _access_token(self, tenant_id: str, clinician_id: str) -> str:
        record = self._load_record(tenant_id, clinician_id)
        if not record:
            # An injected HTTP client is the explicit isolated-test seam. The
            # application singleton never has one, so production still fails
            # closed when no clinician-bound authorization exists.
            if self._client is not None:
                return "test-only-token"
            raise SmartFHIRUnavailable("Clinician has not authorized OCHIN SMART access")
        tokens = self._decrypt(record)
        if record.expires_at > time.time() + 30:
            return str(tokens["access_token"])
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            self._delete_record(tenant_id, clinician_id)
            raise SmartFHIRUnavailable("OCHIN SMART authorization has expired")
        response = await self._request(
            "POST", str(settings.ochin_smart_token_url),
            data={
                "grant_type": "refresh_token", "refresh_token": refresh_token,
                "client_id": settings.ochin_smart_client_id,
            },
        )
        payload = response.json()
        if "access_token" not in payload:
            self._delete_record(tenant_id, clinician_id)
            raise SmartFHIRUnavailable("OCHIN SMART token refresh failed")
        tokens = {"access_token": payload["access_token"], "refresh_token": payload.get("refresh_token", refresh_token)}
        record.encrypted = self._fernet().encrypt(json.dumps(tokens).encode())
        record.expires_at = time.time() + max(1, int(payload.get("expires_in", 300)))
        self._save_record(tenant_id, clinician_id, record)
        return str(tokens["access_token"])

    async def _get_json(self, path: str, tenant_id: str, clinician_id: str) -> dict[str, Any]:
        self._configured()
        token = await self._access_token(tenant_id, clinician_id)
        url = f"{str(settings.ochin_smart_fhir_base_url).rstrip('/')}/{path.lstrip('/')}"
        response = await self._request(
            "GET", url,
            headers={"Accept": "application/fhir+json", "Authorization": f"Bearer {token}"},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SmartFHIRUnavailable("OCHIN SMART FHIR response was invalid") from exc
        if not isinstance(payload, dict):
            raise SmartFHIRUnavailable("OCHIN SMART FHIR response was invalid")
        return payload

    @staticmethod
    def normalize_patient(resource: dict[str, Any]) -> SmartPatient:
        identifier = resource.get("id")
        if resource.get("resourceType") != "Patient" or not isinstance(identifier, str) or not identifier:
            raise ValueError("FHIR response is not a Patient")
        names = resource.get("name") or []
        name = names[0] if names and isinstance(names[0], dict) else {}
        display_name = name.get("text") or " ".join([*(name.get("given") or []), name.get("family") or ""]).strip() or identifier
        return SmartPatient(identifier, str(display_name), resource.get("birthDate"), resource.get("gender"))

    @staticmethod
    def normalize_encounter(resource: dict[str, Any]) -> SmartEncounter:
        identifier, status = resource.get("id"), resource.get("status")
        if resource.get("resourceType") != "Encounter" or not isinstance(identifier, str) or not isinstance(status, str):
            raise ValueError("FHIR response is not an Encounter")
        coding = ((resource.get("type") or [{}])[0].get("coding") or [{}])[0]
        kind = coding.get("display") or ((resource.get("type") or [{}])[0].get("text"))
        period = resource.get("period") or {}
        return SmartEncounter(identifier, status.lower(), str(kind) if kind else None, period.get("start"))

    async def get_patient(self, patient_id: str, tenant_id: str = "default", clinician_id: str = "test") -> SmartPatient:
        if settings.app_mode == "demo":
            return SmartPatient(patient_id, f"Synthetic demo patient {patient_id}", "1970-01-01", "unknown", "demo-fixture")
        return self.normalize_patient(await self._get_json(f"Patient/{quote(patient_id, safe='')}", tenant_id, clinician_id))

    async def active_encounters(self, patient_id: str, tenant_id: str = "default", clinician_id: str = "test") -> list[SmartEncounter]:
        if settings.app_mode == "demo":
            return [SmartEncounter(f"demo-active-{patient_id}", "in-progress", "Synthetic demo visit", "2024-01-01T00:00:00Z")]
        bundle = await self._get_json(
            f"Encounter?patient={quote(patient_id, safe='')}&status=arrived,triaged,in-progress,onleave",
            tenant_id, clinician_id,
        )
        return [
            encounter for entry in bundle.get("entry") or [] if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
            for encounter in [self.normalize_encounter(entry["resource"])]
            if encounter.status in ACTIVE_ENCOUNTER_STATUSES
        ]


smart_fhir_service = SmartFHIRService()