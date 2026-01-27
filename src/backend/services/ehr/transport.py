from __future__ import annotations

from typing import Dict, Optional

import httpx

from src.backend.domain.models.ehr_connection import EHRConnection


class EHRTransportError(Exception):
    """Raised when an EHR transport operation fails."""


class EHRTransport:
    """Abstract base for EHR transport implementations.

    For now this is a lightweight protocol-style class; additional transports
    (e.g. HL7 v2 over MLLP) can follow the same interface.
    """

    async def send_bundle(self, connection: EHRConnection, bundle: Dict) -> None:
        raise NotImplementedError


class HttpFHIRTransport(EHRTransport):
    """HTTP-based FHIR transport using JSON POSTs.

    Assumes the remote system exposes a FHIR endpoint under the connection's
    base_url. The exact path can be customized via auth_config if needed.
    """

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client or httpx.AsyncClient()

    async def send_bundle(self, connection: EHRConnection, bundle: Dict) -> None:
        if not connection.base_url:
            raise EHRTransportError("EHRConnection.base_url is required for HTTP transport")

        url_path = connection.auth_config.get("fhir_path", "/fhir")
        url = str(connection.base_url).rstrip("/") + url_path

        headers: Dict[str, str] = {"Content-Type": "application/fhir+json"}

        if connection.auth_type == "api_key":
            header_name = connection.auth_config.get("api_key_header", "Authorization")
            # The actual secret should be provided via environment or secret
            # manager and injected into auth_config at runtime by the caller.
            api_key_value = connection.auth_config.get("api_key_value")
            if not api_key_value:
                raise EHRTransportError("Missing api_key_value in auth_config for api_key auth")
            headers[header_name] = api_key_value

        try:
            resp = await self._client.post(url, json=bundle, headers=headers, timeout=connection.auth_config.get("timeout_seconds", 30))
        except httpx.HTTPError as exc:
            raise EHRTransportError(f"HTTP error talking to EHR: {exc}") from exc

        if resp.status_code >= 400:
            raise EHRTransportError(f"EHR responded with {resp.status_code}: {resp.text}")
