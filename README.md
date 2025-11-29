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
- For environment-by-environment validation steps, see `TESTING_CHECKLIST.md`.
- For a deep-dive on architecture, multitenancy, and persistence, see `TECHNICAL_OVERVIEW.md`.

## Key capabilities (clinic-pilot MVP)

At the backend API level, the system currently supports:

- Audio ingestion via HTTP upload and WebSocket live streaming
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
