from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4
import base64

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from src.backend.config import settings
from src.backend.domain.models.transcription_job import TranscriptJob
from src.backend.services.conversation.service import conversation_service
from src.backend.services.transcription.service import transcription_service
from src.backend.services.encounters.service import encounter_service
from src.backend.infra.storage.audio import audio_storage_backend
from src.backend.services.audit.service import audit_service
from src.backend.security import get_api_key
from src.backend.tenancy import tenant_dependency

router = APIRouter(
    prefix="/audio",
    tags=["audio"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


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

    dest_ref = audio_storage_backend.save_file(content, suffix=f"{uuid4()}.{suffix}" if suffix else f"{uuid4()}" )

    job = transcription_service.create_job(
        audio_url=str(dest_ref),
        language_code=language_code,
        target_language=target_language,
    )

    attached_session_id: Optional[str] = None
    attached_encounter_id: Optional[UUID] = None

    # Optionally attach this job to an existing conversation session.
    if session_id is not None:
        session = conversation_service.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        conversation_service.attach_job(session_id=session_id, job_id=job.id)
        attached_session_id = str(session_id)

    # Optionally attach this job to an existing clinical encounter or create one.
    if encounter_id is not None:
        encounter = encounter_service.get_encounter(encounter_id)
        if encounter is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")
        encounter_service.attach_job(encounter_id=encounter_id, job_id=job.id)
        attached_encounter_id = encounter_id
    else:
        encounter = encounter_service.create_encounter(
            clinician_id=clinician_id,
            patient_id=patient_id,
            title=file.filename,
        )
        encounter_service.attach_job(encounter_id=encounter.id, job_id=job.id)
        attached_encounter_id = encounter.id

    audit_service.log_event(
        action="upload_audio",
        resource_type="transcription_job",
        resource_id=str(job.id),
        extra={
            "session_id": attached_session_id,
            "encounter_id": str(attached_encounter_id) if attached_encounter_id else None,
            "filename": file.filename,
            "size_bytes": len(content),
        },
    )

    return IngestAudioResponse(job=job, encounter_id=attached_encounter_id)


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
    qp = websocket.query_params
    language_code = qp.get("language_code")
    target_language = qp.get("target_language")
    session_id: Optional[UUID] = None
    session_id_str = qp.get("session_id")
    if session_id_str:
        try:
            session_id = UUID(session_id_str)
        except ValueError:
            # Invalid session_id format; treat as no session.
            session_id = None

    await websocket.accept()
    upload_dir = settings.audio_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / f"ws-{uuid4()}.wav"

    total_bytes = 0
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
                audio_storage_backend.append_file(str(temp_path), chunk)

                # Default partial text is a simple byte counter
                partial_text = f"Received {total_bytes} bytes of audio (demo)"

                # Try to run ASR backend on the buffered audio for a richer
                # partial transcript. Any errors are swallowed so the stream
                # continues.
                try:
                    asr_backend = transcription_service._asr_backend  # type: ignore[attr-defined]
                    transcript = asr_backend.transcribe(str(temp_path), language_code=language_code)
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

                    audio_storage_backend.append_file(str(temp_path), chunk)

                    partial_text = f"Received {total_bytes} bytes of audio (demo)"
                    try:
                        asr_backend = transcription_service._asr_backend  # type: ignore[attr-defined]
                        transcript = asr_backend.transcribe(str(temp_path), language_code=language_code)
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
                        job = transcription_service.create_job(
                            audio_url=str(temp_path),
                            language_code=language_code,
                            target_language=target_language,
                        )
                        if session_id is not None:
                            session = conversation_service.get_session(session_id)
                            if session is not None:
                                conversation_service.attach_job(session_id=session_id, job_id=job.id)
                        job_payload = job.model_dump()

                    await websocket.send_json({"type": "final", "job": job_payload})

                    audit_service.log_event(
                        action="live_transcription_complete",
                        resource_type="transcription_job",
                        resource_id=str(job.id) if job_payload else None,
                        extra={"total_bytes": total_bytes},
                    )

                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                    break
    except WebSocketDisconnect:
        # Client disconnected; nothing else to do for this prototype.
        return
    finally:
        if temp_path.exists():
            audio_storage_backend.delete_file(str(temp_path))
