from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4
import base64
from pathlib import Path
import asyncio

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from src.backend.config import settings
from src.backend.domain.models.transcription_job import TranscriptJob
from src.backend.services.conversation.service import conversation_service
from src.backend.services.transcription.service import transcription_service
from src.backend.services.transcription.privacy import (
    DEFAULT_RECORDING_CONSENT_VERSION,
    ELEVENLABS_CONSENT_VERSION,
    external_asr_consent_version,
    require_external_asr_consent,
)
from src.backend.services.encounters.service import encounter_service
from src.backend.infra.storage.audio import audio_storage_backend
from src.backend.services.audit.service import audit_service
from src.backend.security import get_current_user, get_websocket_user, ensure_can_edit_encounter
from src.backend.domain.models.user import User
from src.backend.tenancy import get_current_tenant, reset_current_tenant, set_current_tenant
from src.backend.services.audio_upload_idempotency import audio_upload_idempotency_service
from src.backend.infra.db.inmemory import transcription_job_repository

router = APIRouter(
    prefix="/audio",
    tags=["audio"],
)


@router.get("/capabilities")
async def audio_capabilities(current_user: User = Depends(get_current_user)) -> dict:
    """Describe audio handling so the mobile consent step can be accurate."""
    provider = settings.asr_backend.lower()
    if provider == "elevenlabs":
        return {
            "provider": "elevenlabs",
            "provider_label": "ElevenLabs Scribe v2 Medical (cloud)",
            "external_processing": True,
            "automatic_language_detection": True,
            "consent_version": ELEVENLABS_CONSENT_VERSION,
            "consent_disclosure": (
                "Audio is sent to ElevenLabs for cloud transcription. The organization must have "
                "an active Business Associate Agreement and Zero Retention Mode enabled. "
                "A clinician must review the transcript before it is used clinically."
            ),
        }
    return {
        "provider": provider,
        "provider_label": "Demo transcription (no external service)" if provider == "demo" else provider,
        "external_processing": False,
        "automatic_language_detection": False,
        "consent_version": external_asr_consent_version() or DEFAULT_RECORDING_CONSENT_VERSION,
        "consent_disclosure": "The patient consents to recording and AI transcription.",
    }


# Demo mode has no database by design. Production never uses this map: it uses
# the SQL-backed unique claim configured at bootstrap.
_demo_upload_idempotency: dict[tuple[str, str, str, str], "IngestAudioResponse"] = {}


class IngestAudioResponse(BaseModel):
    job: TranscriptJob
    encounter_id: Optional[UUID] = None


@router.post("/upload", response_model=IngestAudioResponse, status_code=status.HTTP_201_CREATED)
async def upload_audio(
    file: UploadFile = File(...),
    language_code: Optional[str] = None,
    target_language: Optional[str] = None,
    session_id: Optional[UUID] = None,
    encounter_id: Optional[UUID] = None,
    patient_id: Optional[str] = None,
    clinician_id: Optional[str] = None,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
) -> IngestAudioResponse:
    """Ingest an uploaded audio file and create a transcription job.

    The uploaded audio is persisted to a local directory so that on-host ASR
    backends such as Whisper can read it by filesystem path. The effective
    path is used as the job's audio_url.
    """

    suffix = (Path(file.filename).suffix or "").lstrip(".")

    # Basic content-type sanity check for uploaded files.
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type; expected audio/*.",
        )

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file too large.",
        )

    if settings.asr_backend.lower() == "elevenlabs" and encounter_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ElevenLabs transcription requires a confirmed patient encounter and provider-specific consent",
        )

    selected_encounter = None
    if encounter_id is not None:
        selected_encounter = encounter_service.get_encounter(encounter_id)
        if selected_encounter is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")
        ensure_can_edit_encounter(current_user, selected_encounter.clinician_id)
        if not encounter_service.is_confirmed_recording_allowed(selected_encounter):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Encounter requires active SMART confirmation and unrevoked consent",
            )
        require_external_asr_consent(selected_encounter)

    idempotency_scope: Optional[tuple[str, str, str, str]] = None
    if idempotency_key:
        if len(idempotency_key) > 128:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key is too long")
        if encounter_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key requires a confirmed encounter")
        idempotency_scope = (
            get_current_tenant(),
            str(current_user.id),
            str(encounter_id),
            idempotency_key,
        )
        if settings.app_mode == "demo":
            previous = _demo_upload_idempotency.get(idempotency_scope)
            if previous is not None:
                return previous
            claimed_job_id = None
        else:
            claimed_job_id, claim_state = audio_upload_idempotency_service.claim(
                tenant_id=idempotency_scope[0], clinician_id=idempotency_scope[1],
                encounter_id=encounter_id, capture_id=idempotency_key,
            )
            if claim_state == "complete":
                existing_job = transcription_job_repository.get(claimed_job_id)
                if existing_job is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed capture job is unavailable")
                return IngestAudioResponse(job=existing_job, encounter_id=encounter_id)
            if claim_state == "pending":
                for _ in range(20):
                    if audio_upload_idempotency_service.state(claimed_job_id) == "complete":
                        break
                    await asyncio.sleep(0.05)
                if audio_upload_idempotency_service.state(claimed_job_id) != "complete":
                    raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Capture is being processed; retry will reclaim it if the lease expires")
                existing_job = transcription_job_repository.get(claimed_job_id)
                if existing_job is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed capture job is unavailable")
                return IngestAudioResponse(job=existing_job, encounter_id=encounter_id)
    else:
        claimed_job_id = None

    # Persist the upload using the original filename when available so that
    # clients (and tests) can rely on the path ending with the uploaded name.
    # Fall back to a UUID-based filename if the client did not supply one.
    filename = Path(file.filename).name if file.filename else None
    dest_name = filename or (f"{uuid4()}.{suffix}" if suffix else str(uuid4()))
    # Resolve through the module at request time so startup wiring is honored.
    from src.backend.infra.storage import audio as audio_module
    dest_ref = audio_module.audio_storage_backend.save_file(content, suffix=dest_name)

    existing_claimed_job = (
        transcription_job_repository.get(claimed_job_id)
        if claimed_job_id is not None and settings.app_mode != "demo"
        else None
    )
    try:
        job = existing_claimed_job or transcription_service.create_job(
            audio_url=str(dest_ref),
            language_code=language_code,
            target_language=target_language,
            job_id=claimed_job_id,
        )
    except Exception:
        if claimed_job_id is not None and settings.app_mode != "demo":
            audio_upload_idempotency_service.fail(claimed_job_id)
        raise

    attached_session_id: Optional[str] = None
    attached_encounter_id: Optional[UUID] = None

    # Optionally attach this job to an existing conversation session.
    if session_id is not None:
        try:
            session = conversation_service.get_session(session_id)
            if session is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
            conversation_service.attach_job(session_id=session_id, job_id=job.id)
            attached_session_id = str(session_id)
        except Exception:
            if claimed_job_id is not None and settings.app_mode != "demo":
                audio_upload_idempotency_service.fail(claimed_job_id)
            raise

    # Optionally attach this job to an existing clinical encounter or create one.
    try:
        if encounter_id is not None:
            encounter = selected_encounter
            assert encounter is not None
            encounter_service.attach_job(encounter_id=encounter_id, job_id=job.id)
            attached_encounter_id = encounter_id
        else:
            encounter = encounter_service.create_encounter(
                clinician_id=str(current_user.id), patient_id=patient_id, title=file.filename,
            )
            encounter_service.attach_job(encounter_id=encounter.id, job_id=job.id)
            attached_encounter_id = encounter.id
    except Exception:
        if claimed_job_id is not None and settings.app_mode != "demo":
            audio_upload_idempotency_service.fail(claimed_job_id)
        raise

    try:
        audit_service.log_event(
            action="upload_audio", resource_type="transcription_job", resource_id=str(job.id),
            extra={"session_id": attached_session_id,
                   "encounter_id": str(attached_encounter_id) if attached_encounter_id else None,
                   "size_bytes": len(content)},
        )
    except Exception:
        if claimed_job_id is not None and settings.app_mode != "demo":
            audio_upload_idempotency_service.fail(claimed_job_id)
        raise

    response = IngestAudioResponse(job=job, encounter_id=attached_encounter_id)
    if idempotency_scope is not None:
        if settings.app_mode == "demo":
            _demo_upload_idempotency[idempotency_scope] = response
        else:
            audio_upload_idempotency_service.complete(job.id)
    return response


@router.websocket("/ws")
async def live_transcription(websocket: WebSocket) -> None:
    """Prototype live audio ingestion endpoint using WebSocket.

    Clients send binary audio chunks; the server responds with incremental
    "partial" transcripts. For now we buffer audio to a temporary file and
    invoke the configured ASR backend (e.g., Whisper) on the buffered audio
    whenever new data arrives. If ASR fails, we fall back to a byte-count
    message.
    """

    # Extract optional query parameters for language and session association.
    try:
        current_user = await get_websocket_user(websocket)
    except HTTPException as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(exc.detail))
        return
    qp = websocket.query_params
    tenant_token = set_current_tenant(get_current_tenant())
    language_code = qp.get("language_code")
    target_language = qp.get("target_language")
    session_id: Optional[UUID] = None
    session_id_str = qp.get("session_id")
    encounter_id_str = qp.get("encounter_id")
    capture_id = qp.get("capture_id")
    encounter_id: Optional[UUID] = None
    if capture_id is not None and (
        not capture_id or len(capture_id) > 128 or not encounter_id_str
    ):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid capture_id")
        return
    if encounter_id_str:
        try:
            encounter_id = UUID(encounter_id_str)
        except ValueError:
            await websocket.close(code=1008, reason="Invalid encounter_id")
            return
    if encounter_id is not None:
        encounter = encounter_service.get_encounter(encounter_id)
        if encounter is None:
            await websocket.close(code=1008, reason="Encounter not found")
            return
        try:
            ensure_can_edit_encounter(current_user, encounter.clinician_id)
            if not encounter_service.is_confirmed_recording_allowed(encounter):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Encounter requires active SMART confirmation and unrevoked consent")
            require_external_asr_consent(encounter)
        except HTTPException as exc:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(exc.detail))
            return
    else:
        if settings.asr_backend.lower() == "elevenlabs":
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="ElevenLabs transcription requires a confirmed encounter and provider-specific consent",
            )
            return
        # A mobile capture may begin before an encounter exists. Create it only
        # after authentication and assign it to the verified clinician so the
        # caller cannot select another clinician or tenant.
        encounter = encounter_service.create_encounter(
            clinician_id=str(current_user.id),
            title="Mobile live transcription",
        )
        encounter_id = encounter.id
    if capture_id is not None:
        if not capture_id or len(capture_id) > 128 or encounter_id is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid capture_id")
            return
        assert encounter_id is not None
        idempotency_scope = (
            get_current_tenant(), str(current_user.id), str(encounter_id), capture_id,
        )
    else:
        idempotency_scope = None
    if session_id_str:
        try:
            session_id = UUID(session_id_str)
        except ValueError:
            # Invalid session_id format; treat as no session.
            session_id = None

    await websocket.accept()
    audit_service.log_event(
        action="recording_started",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={"encounter_id": str(encounter_id)},
    )
    # Use an opaque durable reference outside demo mode.  Routes import the
    # storage singleton before startup, so resolve it at runtime below.
    from src.backend.infra.storage import audio as audio_module
    temp_path = str(settings.audio_upload_dir / f"ws-{uuid4()}.wav")
    if settings.app_mode != "demo":
        temp_path = audio_module.audio_storage_backend.save_file(b"", suffix=f"ws-{uuid4()}.wav")

    total_bytes = 0
    keep_audio = False
    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"] is not None:
                chunk = message["bytes"]
                total_bytes += len(chunk)

                # Enforce a maximum total stream size per connection.
                if total_bytes > settings.max_ws_bytes:
                    await websocket.send_json(
                        {
                            "error": "Maximum stream size exceeded.",
                            "total_bytes": total_bytes,
                        }
                    )
                    await websocket.close(code=1009)
                    break

                # Append chunk to temp audio file
                audio_module.audio_storage_backend.append_file(str(temp_path), chunk)

                # Default partial text is a simple byte counter
                partial_text = f"Received {total_bytes} bytes of audio (demo)"

                # Try to run ASR backend on the buffered audio for a richer
                # partial transcript. Any errors are swallowed so the stream
                # continues.
                if settings.asr_backend.lower() == "elevenlabs":
                    partial_text = "Audio received; multilingual transcription runs after recording ends."
                else:
                    try:
                        asr_backend = transcription_service._asr_backend  # type: ignore[attr-defined]
                        with audio_module.processing_path(str(temp_path)) as partial_path:
                            transcript = asr_backend.transcribe(
                                partial_path, language_code=language_code
                            )
                        if transcript:
                            partial_text = transcript
                    except Exception:  # pragma: no cover - defensive around external deps
                        pass

                await websocket.send_json(
                    {
                        "partial_text": partial_text,
                        "total_bytes": total_bytes,
                    }
                )
            elif "text" in message and message["text"] is not None:
                text_msg = message["text"]

                # Support base64-encoded audio chunks sent as text frames
                # prefixed with "AUDIO_BASE64:". This is useful for mobile
                # clients that find it easier to stream base64 text instead of
                # raw binary WebSocket frames.
                if text_msg.startswith("AUDIO_BASE64:"):
                    b64_payload = text_msg[len("AUDIO_BASE64:") :]
                    try:
                        chunk = base64.b64decode(b64_payload)
                    except Exception:
                        await websocket.send_json({"error": "Invalid base64 audio chunk"})
                        continue

                    total_bytes += len(chunk)

                    if total_bytes > settings.max_ws_bytes:
                        await websocket.send_json(
                            {
                                "error": "Maximum stream size exceeded.",
                                "total_bytes": total_bytes,
                            }
                        )
                        await websocket.close(code=1009)
                        break

                    audio_module.audio_storage_backend.append_file(str(temp_path), chunk)

                    partial_text = f"Received {total_bytes} bytes of audio (demo)"
                    if settings.asr_backend.lower() == "elevenlabs":
                        partial_text = "Audio received; multilingual transcription runs after recording ends."
                    else:
                        try:
                            asr_backend = transcription_service._asr_backend  # type: ignore[attr-defined]
                            with audio_module.processing_path(str(temp_path)) as partial_path:
                                transcript = asr_backend.transcribe(
                                    partial_path, language_code=language_code
                                )
                            if transcript:
                                partial_text = transcript
                        except Exception:  # pragma: no cover - defensive around external deps
                            pass

                    await websocket.send_json(
                        {
                            "partial_text": partial_text,
                            "total_bytes": total_bytes,
                        }
                    )
                # Allow clients to send a "stop" message to close the stream.
                elif text_msg.lower() == "stop":
                    # On stop, optionally create a persisted transcription job
                    # from the buffered audio and attach it to a session.
                    job_payload = None
                    if total_bytes > 0:
                        job = None
                        claimed_job_id = None
                        claim_state = None
                        if idempotency_scope is not None:
                            if settings.app_mode == "demo":
                                previous = _demo_upload_idempotency.get(idempotency_scope)
                                if previous is not None:
                                    job = previous.job
                            else:
                                assert encounter_id is not None
                                claimed_job_id, claim_state = audio_upload_idempotency_service.claim(
                                    tenant_id=idempotency_scope[0],
                                    clinician_id=idempotency_scope[1],
                                    encounter_id=encounter_id,
                                    capture_id=capture_id,
                                )
                                if claim_state != "claimed":
                                    job = transcription_job_repository.get(claimed_job_id)
                                    if job is None:
                                        await websocket.send_json({
                                            "type": "retry",
                                            "capture_id": capture_id,
                                            "error": "This capture is still being processed. Keep the local recording and retry shortly.",
                                        })
                                        await websocket.close(code=1013)
                                        break

                        if job is None:
                            try:
                                job = transcription_service.create_job(
                                    audio_url=str(temp_path),
                                    language_code=language_code,
                                    target_language=target_language,
                                    job_id=claimed_job_id,
                                )
                                keep_audio = True
                            except Exception:
                                if claimed_job_id is not None and settings.app_mode != "demo":
                                    audio_upload_idempotency_service.fail(claimed_job_id)
                                raise

                        if session_id is not None:
                            session = conversation_service.get_session(session_id)
                            if session is not None and job.id not in session.transcription_job_ids:
                                conversation_service.attach_job(session_id=session_id, job_id=job.id)
                        if encounter_id is not None:
                            encounter_service.attach_job(encounter_id=encounter_id, job_id=job.id)

                        if idempotency_scope is not None:
                            if settings.app_mode == "demo":
                                _demo_upload_idempotency[idempotency_scope] = IngestAudioResponse(
                                    job=job, encounter_id=encounter_id,
                                )
                            elif claim_state in ("claimed", "pending"):
                                audio_upload_idempotency_service.complete(job.id)

                        audit_service.log_event(
                            action="live_transcription_complete",
                            resource_type="transcription_job",
                            resource_id=str(job.id),
                            extra={"total_bytes": total_bytes},
                        )
                        # Use JSON mode so UUIDs and other types are serialized
                        # into JSON-compatible primitives for the WebSocket
                        # payload.
                        job_payload = job.model_dump(mode="json")

                    await websocket.send_json(
                        {
                            "type": "final",
                            "job": job_payload,
                            "encounter_id": str(encounter_id),
                            "capture_id": capture_id,
                        }
                    )

                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                    break
    except WebSocketDisconnect:
        # Client disconnected; nothing else to do for this prototype.
        return
    finally:
        if not keep_audio:
            audio_module.audio_storage_backend.delete_file(str(temp_path))
        reset_current_tenant(tenant_token)
