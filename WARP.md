# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.
``

## Project overview and current state

This repository is an AI/ML-powered application for detecting and analyzing medical transcriptions.

High-level capabilities the system is intended to support:
- Real-time and batch audio transcription with strong medical vocabulary support (ICD-10, SNOMED CT, RxNorm, meds, dosages, vitals) and robustness to accents/noise.
- Medical intent and entity detection (patient info, symptoms, diagnoses with ICD-10 mapping, medications with dose/frequency, vitals, allergies, procedures, lab/imaging orders, follow-up recommendations).
- Conversation/dictation analysis into SOAP-format notes, free-text notes, structured EHR fields, and derived tasks/risks.
- Export to clinical formats and systems (FHIR/HL7 + PDF/DOCX) and integration with hospital/clinic EHRs.
- Operation under strong security/compliance constraints (HIPAA, GDPR, PHI encryption, RBAC, audit logging).

Currently, the repository has a small but functional clinic-pilot MVP implementation:
- `README.md` describing high-level goals and current capabilities.
- `TECHNICAL_OVERVIEW.md` documenting architecture, multitenancy, and persistence.
- `src/backend/main.py` providing a FastAPI app with root and `/api/v1` health endpoints and wiring all routers.
- `src/backend/api/v1/routes_system.py` and `routes_transcription*.py` defining versioned system and transcription routes, including analysis and FHIR export.
- `src/backend/api/v1/routes_audio_ingestion.py` defining endpoints for audio upload and a live WebSocket ingestion endpoint.
- `src/backend/domain/models/transcription_job.py` defining a Pydantic `TranscriptJob` domain model including optional translation fields, basic job state, and tenant ID.
- `src/backend/services/transcription/backends.py` defining pluggable ASR and translation backend interfaces with demo, Whisper, and LLaMA-stub implementations.
- `src/backend/services/transcription/service.py` providing an in-memory transcription job service wired to the ASR/translation backends.
- `src/backend/domain/nlp/models.py` and `src/backend/services/nlp/service.py` defining a clinical NLP layer for entities and SOAP notes.
- `src/backend/domain/nlp/coding_models.py` and `services/nlp/coding_orchestrator.py` providing code assignments and naive billing risk assessment.
- `src/backend/domain/nlp/decision_support.py` and `services/nlp/decision_support_service.py` providing simple rule-based clinical decision support (including a stub endpoint for a future regulated CDS lane).
- `src/backend/services/nlp/relevance_classifier.py` labeling transcript segments by relevance.
- `src/backend/services/nlp/emotion_classifier.py` attaching coarse emotion/tone labels to segments.
- `src/backend/services/ehr/service.py` defining a demo FHIR exporter used to build lightweight FHIR bundles from analyzed transcriptions.
- `src/backend/domain/models/clinical_encounter.py`, `clinical_note.py`, `conversation_session.py` and corresponding services/repositories defining encounters, notes, and sessions with review/finalization.
- `src/backend/domain/models/note_template.py` and `services/templates/service.py` implementing in-memory specialty note templates.
- `src/backend/domain/models/patient_timeline.py` and `services/patients/summary_service.py` implementing simple patient timelines.
- `src/backend/domain/models/analytics.py` and `services/analytics/service.py` exposing basic clinic/clinician metrics.
- `src/backend/api/v1/routes_scribe.py` exposing a simple scribe queue and note-editing API for human-in-the-loop review.
- `src/backend/infra/db/*` providing in-memory and SQL-backed repositories with multitenant row-level scoping.
- `tests/backend/*` covering health, transcription (sync/async), audio ingestion, analysis, FHIR export, sessions, and encounters.
- `requirements.txt` listing backend and test dependencies.

The sections below describe the intended *target* architecture and recommended stack so future agents can align new code and tooling with the design as it grows.

## Target tech stack (recommended)

These are recommended, not yet enforced by the codebase. Before relying on them, confirm that the corresponding files (`pyproject.toml`, `package.json`, `Dockerfile`, etc.) exist and match.

- **Backend API**: Python + FastAPI.
- **ML/AI services**: Python ecosystem (HuggingFace, PyTorch, etc.) for ASR, NER, LLM integration, and RAG.
- **Primary data store**: PostgreSQL for structured clinical data; optional MongoDB for document-style storage.
- **Caching**: Redis.
- **Object storage**: MinIO/S3 for audio and large artifacts.
- **Search / vectors**: ElasticSearch or Weaviate for semantic search and vector storage.
- **Frontends**: React web app; optional React Native/Flutter mobile app.
- **Deployment**: Docker containers orchestrated by Kubernetes; CI/CD via GitHub Actions or GitLab CI.

If the implementation uses a different stack, update this section and the commands section below to reflect reality.

## Code layout and architecture (conceptual)

Planned top-level structure under `src/` (adjust as the implementation solidifies):
- `src/backend/` – API server(s) and microservices.
  - `api/` – HTTP endpoints, auth middleware, RBAC, request/response schemas.
  - `services/` – domain services, roughly aligned with the major capabilities:
    - `audio_ingestion/` – upload/record endpoints, buffering, audio normalization, job enqueueing.
    - `transcription/` – integration with ASR (Whisper / cloud medical ASR / custom models).
    - `nlp/` – NER, relation extraction, diagnosis/intent classification, terminology mapping.
    - `llm_interpreter/` – LLM-based medical interpretation, SOAP generation, red-flag detection, task generation.
    - `summarization/` – clinical note formatting (SOAP, free-text, structured EHR fields).
    - `ehr_integration/` – FHIR/HL7 adapters, EHR synchronization.
    - `audit_logging/` – immutable audit trail, access logs.
    - `auth/` – authentication, authorization, role management.
  - `domain/` – core domain models and shared logic.
    - `models/` – patients, encounters, observations, meds, orders, risks, tasks.
    - `terminology/` – helpers for ICD-10/SNOMED/RxNorm/UMLS mapping.
  - `infra/` – infrastructure abstractions.
    - `db/` – database session management, migrations, repositories.
    - `storage/` – S3/MinIO access.
    - `cache/` – Redis.
    - `search/` – ElasticSearch/Weaviate integration.
- `src/frontend/web/` – React SPA for audio upload/recording, real-time transcription, note editing, exports, and admin views.
- `src/frontend/mobile/` – optional mobile client for recording and viewing notes/tasks.
- `ml/` – training/evaluation code and configs for ASR, NER, LLM/RAG.

Conceptual request flow to keep in mind when implementing:
- Audio Input → ASR Service → Medical NER/Relations → LLM Medical Interpreter → Structured Clinical Output (FHIR/HL7/DB models) → EHR/Export → Storage & Analytics.

Focus future architectural notes in this file on cross-cutting concerns that span multiple modules (e.g., shared data models, validation layers, terminology mapping, or orchestration logic), rather than listing individual files.

## Build, lint, and test commands

Current concrete commands supported by this scaffold:
- Install backend/test dependencies (development):
  - `uv pip install -r requirements.txt` or `pip install -r requirements.txt`.
- Run the FastAPI backend locally (after installing dependencies):
  - `uvicorn src.backend.main:app --reload`.
- Run all Python tests:
  - `pytest` (current tests live under `tests/backend/`).
- Run a single backend test file:
  - `pytest tests/backend/test_health.py`.

No frontend, container, or CI tooling has been added yet; those remain conceptual until supporting files exist.

Before running or adding commands, future agents should:
- Re-scan the repository for language/tooling indicators (e.g., Python, Node, or other ecosystems) once implementation files exist.
- Check `README.md` and any new documentation for canonical commands.
- Infer commands from manifest files or configuration (for example, `pyproject.toml`, `package.json`, `Makefile`, or task runner configs) once they are added, and then update this `WARP.md` with those canonical build/lint/test commands.

### Recommended command conventions (once tooling exists)

When you introduce tooling, prefer to align with these conventions so other agents can rely on predictable commands. Only use these after verifying that the corresponding files and scripts exist.

**Backend (Python + FastAPI)**
- Install dependencies (development):
  - `uv`/`pip` example: `uv pip install -r requirements.txt` or `pip install -e .` if using `pyproject.toml`/`setup.cfg`.
- Run API server locally:
  - `uvicorn src.backend.main:app --reload` (or via `make run-backend` / `poetry run uvicorn ...`).
- Run all tests:
  - `pytest` (or `make test-backend`).
- Run a single test file:
  - `pytest tests/backend/test_transcription.py`.
- Run a single test by node:
  - `pytest tests/backend/test_transcription.py::test_basic_transcription_flow`.
- Lint and format:
  - `ruff check src tests` and `ruff format src tests`, or equivalent via `make lint`.
- Type checking (if using mypy/pyright):
  - `mypy src` or `pyright`.

**Frontend (React)**
- Install dependencies:
  - `cd src/frontend/web && npm install` or `pnpm install`.
- Run dev server:
  - `cd src/frontend/web && npm run dev` (Vite) or `npm start` (Create React App).
- Run frontend tests:
  - `cd src/frontend/web && npm test`.
- Lint frontend:
  - `cd src/frontend/web && npm run lint`.

**Containers / orchestration**
- Build images (once Dockerfiles exist):
  - `docker compose build`.
- Run the full stack locally (DB, cache, storage, backend, frontend):
  - `docker compose up`.

When tests and tooling are later introduced, replace or refine the examples above with the exact commands defined by the project (e.g., `make` targets, `poetry` scripts, `npm` scripts) so they accurately reflect the live setup:
- How to run the full test suite.
- How to run a single test or a focused subset (e.g., via test file name or marker).
- How to run linters/formatters and any type-checking tools.
- How to start the main application for local development (backend API, NLP/LLM services, and frontends).

## Guidance for future updates to this file

As the codebase grows, keep this file focused on information that requires reading multiple files to understand, such as:
- Overall architecture (how backend, models, and utilities collaborate)
- Shared domain models and how medical transcription data is represented and validated
- Any non-obvious conventions around directory layout, module boundaries, or dependency structure
- Key development commands that are not immediately obvious from a single config file

Avoid duplicating easily discoverable file listings; instead, capture the high-level design and the minimal set of commands needed to be productive.
