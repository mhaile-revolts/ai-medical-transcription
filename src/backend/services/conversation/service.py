from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional
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

    def create_session(self, title: Optional[str] = None) -> ConversationSession:
        session_id = uuid4()
        session = ConversationSession(
            id=session_id,
            created_at=datetime.utcnow(),
            title=title,
            tenant_id=get_current_tenant(),
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: UUID) -> Optional[ConversationSession]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.tenant_id != get_current_tenant():
            return None
        return session

    def attach_job(self, session_id: UUID, job_id: UUID) -> ConversationSession:
        session = self._sessions[session_id]
        if session.tenant_id != get_current_tenant():
            raise KeyError("Session does not belong to current tenant")
        if job_id not in session.transcription_job_ids:
            session.transcription_job_ids.append(job_id)
            self._sessions[session_id] = session
        return session


conversation_service = InMemoryConversationService()
