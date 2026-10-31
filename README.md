# AI/ML Medical Transcription Detection App

This project is an AI/ML-powered application for detecting and analyzing medical transcriptions.

It focuses on:
- Identifying medically relevant content in transcripts
- Flagging potential issues or anomalies
- Providing structured outputs for downstream clinical workflows
- Assisting with clinical coding (ICD-10, CPT-style demo), billing risk hints, and basic decision support
- Surfacing encounter timelines and analytics for clinics

## Structure
- `src/backend/` – FastAPI backend and domain/services.
- `src/frontend/web/` – React web frontend.
- `src/frontend/mobile/` – Expo React Native mobile client (Android + iOS).

## Getting Started

- For backend and web deployment details, see `DEPLOYMENT.md`.
- For mobile build profiles and commands, see `src/frontend/mobile/README.md`.
- For clinician usage (pilot), including mobile recording and analysis, see `CLINICIAN_QUICKSTART.md`.
- For required physical iPhone and Android recording sign-off, see `docs/mobile-clinician-validation.md`.
- For environment-by-environment validation steps, see `TESTING_CHECKLIST.md`.
- For a deep-dive on architecture, multitenancy, and persistence, see `TECHNICAL_OVERVIEW.md`.

## Key capabilities (clinic-pilot MVP)

At the backend API level, the system currently supports:

- Audio ingestion via HTTP upload and WebSocket live streaming
- Encounter-bound mobile capture with interruption recovery and idempotent upload retries
- Synchronous transcription jobs with optional translation
- Clinical NLP pipeline producing entities and SOAP-style notes
- Clinical coding suggestions + naive billing risk summary
- Encounter and note lifecycle (draft → review → finalized) plus optional scribe review
- Session-level analysis across multiple transcription jobs
- Patient timelines aggregated from encounters/notes
- Advisory clinical decision-support suggestions (rule-based demo)
- Segment-level relevance and emotion/tone scaffolding for ambient understanding
- Basic analytics per clinic and per clinician

These features are exposed via FastAPI routes under `/api/v1`; see `TECHNICAL_OVERVIEW.md` for details.

## Multilingual transcription with ElevenLabs

The backend can use the connected ElevenLabs account with Scribe v2 Medical:

- Set `ASR_BACKEND=elevenlabs` to select the provider.
- Apply the latest database migration with `alembic upgrade head` before
  starting a durable deployment; the detected-language confidence is stored
  with the transcription job.
- Keep the mobile source-language override blank for automatic language
  detection; a clinician can optionally enter a language to guide recognition.
- The app displays the detected language and confidence after the recording is
  transcribed. The current recorder uploads a completed file, so detection is
  not an in-recording, word-by-word language indicator.
- Every request asks ElevenLabs for Zero Retention Mode
  (`enable_logging=false`). Startup fails unless
  `ELEVENLABS_BAA_CONFIRMED=true` and
  `ELEVENLABS_ZERO_RETENTION_ENABLED=true` are explicitly configured.

ElevenLabs states that Scribe v2 Medical is HIPAA-eligible only for Enterprise
customers with a Business Associate Agreement and Zero Retention Mode enabled.
Do not enable this backend for protected health information until the
organization has verified those contractual and account settings. Transcripts
remain drafts for clinician review; they are not a substitute for clinical
judgment. See `src/frontend/mobile/README.md` for configuration details.
