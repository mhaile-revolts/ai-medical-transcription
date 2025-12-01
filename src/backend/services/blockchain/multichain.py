from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

import httpx

from src.backend.config import settings


logger = logging.getLogger("multichain")


@dataclass
class MultiChainConfig:
    """Configuration for connecting to a MultiChain JSON-RPC endpoint.

    This client is intentionally minimal and focused on publishing non-PHI audit
    events into a single configured stream. It assumes that the underlying
    MultiChain node and blockchain have already been created and configured
    (including the audit stream and required permissions).
    """

    enabled: bool
    scheme: str
    host: str
    port: int
    rpc_user: Optional[str]
    rpc_password: Optional[str]
    chain_name: Optional[str]
    audit_stream: str
    timeout_seconds: float

    @classmethod
    def from_settings(cls) -> "MultiChainConfig":
        return cls(
            enabled=settings.multichain_enabled,
            scheme=settings.multichain_rpc_scheme,
            host=settings.multichain_rpc_host,
            port=settings.multichain_rpc_port,
            rpc_user=settings.multichain_rpc_user,
            rpc_password=settings.multichain_rpc_password,
            chain_name=settings.multichain_chain_name,
            audit_stream=settings.multichain_audit_stream,
            timeout_seconds=settings.multichain_rpc_timeout_seconds,
        )

    @property
    def base_url(self) -> str:
        # MultiChain typically exposes a Bitcoin-style JSON-RPC endpoint over
        # HTTP(S) with basic auth, e.g. http://user:pass@host:port.
        return f"{self.scheme}://{self.host}:{self.port}"


class MultiChainClient:
    """Very small JSON-RPC client focused on publishing audit events.

    The client deliberately avoids any PHI and expects callers to pass only
    minimal, structured metadata (IDs, types, timestamps, flags). Failures are
    logged but not raised by default, so that blockchain mirroring cannot break
    the main application flow.
    """

    def __init__(self, config: MultiChainConfig) -> None:
        self._config = config
        self._client = httpx.Client(timeout=config.timeout_seconds)

    def _rpc(self, method: str, params: list[Any]) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": "audit",
            "method": method,
            "params": params,
        }

        auth = None
        if self._config.rpc_user and self._config.rpc_password:
            auth = (self._config.rpc_user, self._config.rpc_password)

        try:
            response = self._client.post(self._config.base_url, json=payload, auth=auth)
        except Exception:
            logger.exception("Error calling MultiChain RPC method %s", method)
            return None

        if response.status_code != 200:
            logger.error(
                "MultiChain RPC %s failed with status %s: %s",
                method,
                response.status_code,
                response.text,
            )
            return None

        try:
            data = response.json()
        except ValueError:
            logger.error("MultiChain RPC %s returned non-JSON response", method)
            return None

        if data.get("error"):
            logger.error("MultiChain RPC %s returned error: %s", method, data["error"])
            return None

        return data.get("result")

    def get_info(self) -> Optional[Dict[str, Any]]:
        """Return basic node info via MultiChain's `getinfo` RPC.

        This is used for simple health checks from the system API.
        """

        return self._rpc("getinfo", [])

    def publish_audit_event(self, payload: Dict[str, Any], key: Optional[str] = None) -> None:
        """Publish a single audit event into the configured stream.

        The event is wrapped using MultiChain's JSON notation for stream items,
        where the third parameter contains a `{ "json": <payload> }` object.

        Parameters
        ----------
        payload:
            A JSON-serializable dictionary representing the audit event. This
            should not contain PHI – only IDs, types, and other metadata.
        key:
            Optional stream key. If omitted, we fall back to
            `payload.get("resource_type")` or a generic "audit" key.
        """

        if not self._config.enabled:
            return

        # Prefer a stable, low-cardinality key for efficient lookup.
        stream_key = key or str(payload.get("resource_type") or "audit")

        params = [
            self._config.audit_stream,
            stream_key,
            {"json": payload},
        ]

        self._rpc("publish", params)


_client_lock: Lock = Lock()
_client_instance: Optional[MultiChainClient] = None


def get_multichain_client() -> Optional[MultiChainClient]:
    """Return a singleton MultiChainClient if enabled and configured.

    If MULTICHAIN_ENABLED=false or required RPC credentials are missing, this
    returns ``None`` and no blockchain calls are made. This function is safe to
    call from within request handlers or services.
    """

    if not settings.multichain_enabled:
        return None

    global _client_instance
    if _client_instance is not None:
        return _client_instance

    with _client_lock:
        if _client_instance is None:
            cfg = MultiChainConfig.from_settings()
            if not cfg.rpc_user or not cfg.rpc_password:
                logger.error(
                    "MULTICHAIN_ENABLED is true but RPC credentials are missing; "
                    "skipping MultiChain client initialization.",
                )
                return None
            _client_instance = MultiChainClient(cfg)

    return _client_instance
