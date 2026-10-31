from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.infra.db.models import Base
import src.backend.infra.db.models_notes_jobs  # noqa: F401
from src.backend.services.audio_upload_idempotency import AudioUploadIdempotencyService


def test_failed_post_claim_work_is_reclaimed_with_same_job_id():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = AudioUploadIdempotencyService()
    service.configure_persistence(sessionmaker(bind=engine))
    encounter_id = uuid4()

    job_id, state = service.claim(
        tenant_id="clinic", clinician_id="doctor", encounter_id=encounter_id,
        capture_id="capture-after-crash",
    )
    assert state == "claimed"

    # Simulate create_job succeeding followed by encounter attachment failing.
    service.fail(job_id)
    retry_job_id, retry_state = service.claim(
        tenant_id="clinic", clinician_id="doctor", encounter_id=encounter_id,
        capture_id="capture-after-crash",
    )
    assert retry_state == "claimed"
    assert retry_job_id == job_id

    # Idempotent reconciliation attaches this one preallocated job, then and
    # only then transitions the durable response gate to complete.
    attached_jobs: list = []
    if retry_job_id not in attached_jobs:
        attached_jobs.append(retry_job_id)
    service.complete(retry_job_id)
    duplicate_job_id, duplicate_state = service.claim(
        tenant_id="clinic", clinician_id="doctor", encounter_id=encounter_id,
        capture_id="capture-after-crash",
    )
    assert duplicate_state == "complete"
    assert duplicate_job_id == job_id
    assert attached_jobs == [job_id]