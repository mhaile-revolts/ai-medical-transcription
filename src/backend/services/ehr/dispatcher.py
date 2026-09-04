from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

from src.backend.config import settings
from src.backend.infra.db.ehr_inmemory import ehr_message_repository
from src.backend.services.ehr.integration_service import ehr_integration_service

logger = logging.getLogger(__name__)


class EHRDeliveryDispatcher:
    def __init__(self) -> None:
        self.worker_id = f"ehr-dispatcher-{uuid4()}"
        self._stop = asyncio.Event()

    async def run_once(self) -> int:
        claimed = ehr_message_repository.claim_due(
            worker_id=self.worker_id,
            now=datetime.now(timezone.utc),
            limit=settings.ehr_dispatch_batch_size,
            lease_duration=timedelta(seconds=settings.ehr_dispatch_lease_seconds),
            max_retries=settings.ehr_retry_max_attempts,
        )
        for message in claimed:
            try:
                await ehr_integration_service.retry_claimed_message(message, self.worker_id)
            except Exception:
                logger.exception("Unexpected error dispatching EHR message %s", message.id)
        return len(claimed)

    async def run(self) -> None:
        self._stop = asyncio.Event()
        while not self._stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), settings.ehr_dispatch_poll_seconds)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()


ehr_delivery_dispatcher = EHRDeliveryDispatcher()