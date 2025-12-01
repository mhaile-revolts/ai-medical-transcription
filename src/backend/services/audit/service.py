from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.backend.config import settings

logger = logging.getLogger("audit")


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
    extra: Optional[Dict[str, Any]] = None


class AuditService:
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

        event = AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            subject=subject,
            extra=extra,
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
