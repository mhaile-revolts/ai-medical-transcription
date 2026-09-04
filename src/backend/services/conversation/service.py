from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from src.backend.domain.models.conversation_session import ConversationSession
from src.backend.tenancy import get_current_tenant


class InMemoryConversationService:
    """Simple in-memory service for managing conversation sessions.

    A session groups one or more transcription jobs that belong to the same
    clinical encounter or conversation.
    """

    def __init__(self) -> None:
        self._sessions: Dict[UUID, ConversationSession] = {}
        self._session_factory: Any = None

    def configure_persistence(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def _save(self, conversation: ConversationSession) -> None:
        if self._session_factory is None:
            self._sessions[conversation.id] = conversation
            return
        from src.backend.infra.db.models import ConversationSessionORM

        db = self._session_factory()
        try:
            existing = db.get(ConversationSessionORM, conversation.id)
            if existing is None:
                db.add(ConversationSessionORM.from_domain(conversation))
            else:
                existing.created_at = conversation.created_at
                existing.ended_at = conversation.ended_at
                existing.title = conversation.title
                existing.transcription_job_ids = (
                    ",".join(str(job_id) for job_id in conversation.transcription_job_ids) or None
                )
                existing.tenant_id = conversation.tenant_id
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create_session(self, title: Optional[str] = None) -> ConversationSession:
        session_id = uuid4()
        session = ConversationSession(
            id=session_id,
            created_at=datetime.now(timezone.utc),
            title=title,
            tenant_id=get_current_tenant(),
        )
        self._save(session)
        return session

    def get_session(self, session_id: UUID) -> Optional[ConversationSession]:
        if self._session_factory is not None:
            from src.backend.infra.db.models import ConversationSessionORM

            db = self._session_factory()
            try:
                row = db.get(ConversationSessionORM, session_id)
                session = row.to_domain() if row is not None else None
            finally:
                db.close()
        else:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.tenant_id != get_current_tenant():
            return None
        return session

    def attach_job(self, session_id: UUID, job_id: UUID) -> ConversationSession:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        if session.tenant_id != get_current_tenant():
            raise KeyError("Session does not belong to current tenant")
        if job_id not in session.transcription_job_ids:
            session.transcription_job_ids.append(job_id)
            self._save(session)
        return session


conversation_service = InMemoryConversationService()
