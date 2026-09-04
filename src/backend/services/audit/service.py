from __future__ import annotations

import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.backend.config import settings
from src.backend.tenancy import get_current_tenant

logger = logging.getLogger("audit")


class SecureTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Keep the active and archived audit files owner-readable only."""

    def _secure_active_file(self) -> None:
        os.chmod(self.baseFilename, 0o600)

    def doRollover(self) -> None:
        super().doRollover()
        self._secure_active_file()


def configure_audit_sink() -> None:
    """Open the production audit sink and enforce local access/retention."""
    if settings.app_env in {"development", "test"}:
        return
    if settings.audit_log_path is None:
        raise RuntimeError("AUDIT_LOG_PATH is required")
    path = settings.audit_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = SecureTimedRotatingFileHandler(
        path,
        when="midnight",
        # The active file is one retained day; archives cover the remainder.
        backupCount=max(0, settings.audit_retention_days - 1),
        encoding="utf-8",
        utc=True,
    )
    handler._secure_active_file()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@dataclass
class AuditEvent:
    """Structured representation of an audit event.

    Intentionally keeps payload minimal and avoids PHI: focus on IDs, types,
    and high-level actions rather than raw transcript text or audio content.
    """

    timestamp: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    subject: Optional[str] = None
    tenant_id: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class AuditService:
    # Only operational metadata belongs in an audit event.  Free text often
    # contains PHI, so unknown keys and text-like values are discarded.
    _allowed_extra = {
        "user_id", "role", "count", "finalize", "status", "enabled",
        "suggestion_count", "has_codes", "billing_risk_level", "segment_count",
        "bundle_entry_count", "async", "size_bytes", "total_bytes",
        "session_id", "encounter_id",
    }

    @classmethod
    def _sanitize_extra(cls, extra: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not extra:
            return None
        safe: Dict[str, Any] = {}
        for key, value in extra.items():
            if key not in cls._allowed_extra or value is None:
                continue
            if isinstance(value, (bool, int, float)):
                safe[key] = value
            elif key in {"role", "status", "billing_risk_level"} and isinstance(value, str) and len(value) <= 64:
                safe[key] = value
            elif key in {"user_id", "session_id", "encounter_id"} and isinstance(value, str) and len(value) <= 128:
                safe[key] = value
        return safe or None

    def log_event(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        subject: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a structured audit event.

        - `action`: high-level verb, e.g., "create", "analyze", "export".
        - `resource_type`: coarse type, e.g., "transcription_job", "session".
        - `resource_id`: stable identifier (UUID string) when available.
        - `subject`: optional identifier for the caller (e.g., API key- or
          user-derived). If omitted, we attempt to infer it from the current
          security context (when API auth is enabled).
        - `extra`: optional small dict of non-PHI metadata (counts, flags).
        """

        if subject is None:
            # Best-effort subject inference from the security layer. This keeps
            # audit logging decoupled from specific auth mechanisms while still
            # allowing correlation of actions by the same caller.
            try:
                from src.backend.security import get_current_subject

                subject = get_current_subject()
            except Exception:
                subject = None

        try:
            tenant_id = get_current_tenant()
        except RuntimeError:
            tenant_id = None
        event = AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            subject=subject,
            tenant_id=tenant_id,
            extra=self._sanitize_extra(extra),
        )

        # Always log to the local structured logger first.
        try:
            payload = asdict(event)
            logger.info(json.dumps(payload))
        except TypeError:
            # Fallback: log a simpler representation if something in extra is
            # not JSON serializable.
            safe_event = asdict(event)
            safe_event["extra"] = None
            payload = safe_event
            logger.info(json.dumps(safe_event))

        # Optionally mirror the audit event into a MultiChain stream when
        # enabled. Any failures here are non-fatal and only logged, so audit
        # logging never breaks the main request flow.
        if settings.multichain_enabled:
            try:
                from src.backend.services.blockchain.multichain import get_multichain_client

                client = get_multichain_client()
                if client is not None:
                    client.publish_audit_event(payload)
            except Exception:
                logger.exception("Failed to publish audit event to MultiChain")


audit_service = AuditService()
