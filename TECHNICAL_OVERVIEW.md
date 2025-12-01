# AI Medical Transcription Detector – Technical Overview

## 1. System Overview

This system ingests clinical audio (upload + live), performs medical transcription and NLP, and generates structured clinical artifacts (encounters, notes, FHIR bundles) in a multitenant, clinic‑ready architecture.

Key capabilities:

- Audio ingestion
  - HTTP upload (`/api/v1/audio/upload`)
  - WebSocket live transcription (`/api/v1/audio/ws`)
- Transcription (ASR) + optional translation
- Clinical NLP (entities + SOAP note)
- Clinical coding + naive billing risk assessment
- Encounters / notes / sessions grouping with review/finalization workflow
- Patient timelines and basic clinical analytics
- Advisory clinical decision support (rule-based demo)
- FHIR export
- Multitenant, Postgres‑backed persistence
- API key–based auth, audit logging with optional MultiChain mirroring for tamper-evident trails (no PHI on-chain)
- Web SPA + mobile apps

---

## 2. Architecture

### 2.1 High-level components

- **Backend API**: FastAPI (`src/backend/main.py`)
  - Versioned API under `/api/v1`
  - Routers:
    - System: `/api/v1/health`, `/api/v1/system/blockchain/health` (MultiChain health)
    - Transcriptions: `/api/v1/transcriptions`, `/transcriptions/async`
    - Audio ingestion: `/api/v1/audio/...` (upload + WebSocket)
    - NLP & export: transcription analysis, FHIR export
    - Sessions: conversation grouping + multi-job analysis
    - Encounters + SOAP notes + decision support + review workflow
    - Templates: specialty-specific note templates
    - Patients: patient summary timelines
    - Analytics: clinic- and clinician-level metrics
- **Domain models**:
  - `User`, `ClinicalEncounter`, `ClinicalNote`, `TranscriptJob`, `ConversationSession`
- **Services**:
  - `services/transcription`: ASR + translation backends, in‑memory orchestration
  - `services/nlp`: entities + SOAP note generation (demo models)
    - `coding_orchestrator`: derives code assignments + billing risk summary
    - `relevance_classifier`: segments transcripts with relevance labels
    - `emotion_classifier`: attaches coarse emotion/tone labels to segments
    - `decision_support_service`: rule-based clinical suggestions
  - `services/encounters`: encounter + note lifecycle (including READY_FOR_REVIEW/FINALIZED)
  - `services/conversation`: sessions grouping jobs
  - `services/patients`: patient summary timelines
  - `services/analytics`: clinic and clinician metrics
  - `services/ehr`: FHIR export
  - `services/users`: subject→User mapping
  - `services/audit`: structured audit logging
  - `services/templates`: in-memory note templates per tenant

### 2.2 Cultural, Accent, and Sovereignty-aware components

In addition to the core services above, the backend includes a set of components
focused on cultural safety, Indigenous data sovereignty, and accent-aware ASR:

- `services/nlp/cultural_phrase_normalizer.py` and
  `services/nlp/indigenous_phrase_normalizer.py` – map culturally specific
  expressions (e.g., "my blood is hot") into parallel clinical wording for the
  NLP pipeline while preserving original phrases for clinicians.
- `services/governance/indigenous_data_sovereignty_guard.py` – evaluates
  patient/tenant consent flags (e.g., consent for cultural AI features and
  training reuse) and produces a `CulturalConsentContext` used by NLP/ML
  backends.
- `services/nlp/cultural_risk_engine.py` and
  `services/nlp/indigenous_risk_engine.py` – optional, conservative engines that
  add advisory risk hints for specific regions/communities when explicit
  metadata is provided (never based on inferred race/ethnicity).
- `services/nlp/bias_auditor.py` – logs aggregate CDS suggestion patterns for
  later bias analysis without changing clinical output.
- `services/nlp/cultural_safety_guard.py` – post-processes CDS suggestions to
  add cultural-safety advisories in edge cases (e.g., spiritual language plus
  high-severity alerts).
- `core/accent_classifier.py` – heuristic `AccentLabel` classifier based on
  language codes and optional region hints.
- `core/multi_accent_asr_backend.py` – wrapper ASR backend that classifies
  accent before delegating to the configured ASR implementation; currently used
  for observability and future accent-specific tuning.
- **Persistence layer**:
  - In‑memory services for early prototyping
  - Pluggable repositories:
    - `infra/db/inmemory.py` – in‑memory repository adapters
    - `infra/db/models.py`, `models_notes_jobs.py` – SQLAlchemy ORM models
    - `infra/db/sql_encounters.py`, `sql_notes_jobs.py` – SQL repos
    - `infra/db/bootstrap.py` – wiring to Postgres
- **Storage**:
  - `infra/storage/audio.py`: local filesystem for audio (`AUDIO_UPLOAD_DIR`)

- **Frontend**:
  - Web: React/Vite SPA (`src/frontend/web`)
  - Mobile: Expo React Native (`src/frontend/mobile`)

---

## 3. Multitenancy Model

### 3.1 Tenant concept

- Logical tenants are typically **clinics** or **organizations**.
- Backend is **row‑level multitenant**:
  - Each record is tagged with a `tenant_id: str`.
  - Data access is always scoped to the current tenant context.

### 3.2 Tenant propagation

Tenant is determined per request via HTTP header:

- `X-Tenant-ID: <tenant_id>`
  - If **omitted**, the backend uses the default tenant `"default"`.
  - This ensures backward compatibility for single‑tenant clients/tests.

Tenant context is held in:

- `src/backend/tenancy.py`
  - `current_tenant: ContextVar[str]` (default `"default"`)
  - `get_current_tenant() -> str`
  - `tenant_dependency()` – FastAPI dependency that:
    - Reads `X-Tenant-ID`
    - Sets the context var for the lifetime of the request

All v1 routers include:

- `Depends(tenant_dependency)` so every request is tenant‑scoped.

### 3.3 Tenant-aware domain models

The following domain models include `tenant_id: str`:

- `User` (`domain/models/user.py`)
- `ClinicalEncounter` (`domain/models/clinical_encounter.py`)
- `ClinicalNote` (`domain/models/clinical_note.py`)
- `TranscriptJob` (`domain/models/transcription_job.py`)
- `ConversationSession` (`domain/models/conversation_session.py`)

Each is persisted with its `tenant_id` in both in‑memory and SQL repositories.

### 3.4 Tenant scoping rules

- **In‑memory services** (encounters, jobs, sessions, users) set `tenant_id` from `get_current_tenant()` at creation time and restrict `get`/`list`/`attach` to the current tenant.
- **In‑memory repositories** (encounters, notes, jobs) always filter by `tenant_id` of the current tenant before applying business filters (clinician, patient, status).
- **SQL repositories**:
  - `SqlEncounterRepository.get/list_by_filters` filter on `EncounterORM.tenant_id == current_tenant`.
  - `SqlClinicalNoteRepository.get/get_by_encounter` filter on `ClinicalNoteORM.tenant_id == current_tenant`.
  - `SqlTranscriptionJobRepository.get` requires `TranscriptJobORM.tenant_id == current_tenant`.

This ensures complete isolation of data between tenants at the application layer.

---

## 4. Authentication, Users, and Authorization

### 4.1 API key auth

Configured via env:

- `ENABLE_API_AUTH` – `"true"` or `"false"` (default `"false"`).
- `API_KEYS` – comma‑separated allowed API keys.

Mechanism:

- `X-API-Key` header is read by `security.get_api_key` (FastAPI dependency).
- When `ENABLE_API_AUTH=true`:
  - Request must supply a valid key from `API_KEYS`.
  - A stable “subject” identifier is derived (SHA‑256 hash prefix of the key).
  - Subject is stored in a `ContextVar` for use by downstream services (audit, users).
- When `ENABLE_API_AUTH=false`:
  - Auth is treated as disabled (for dev/tests).
  - `get_current_user` synthesizes a single admin user.

### 4.2 User model and mapping

- `User` domain model: `id`, `email`, `role`, `tenant_id`.
- `InMemoryUserService`:
  - Maps **subject** → `User`.
  - On first use of a subject:
    - Creates a new `User` with `tenant_id=get_current_tenant()` and appropriate role (admin/clinician).
  - Subsequent requests with same subject reuse the same `User`.

### 4.3 Authorization for encounters

- Helper functions in `security.py`:
  - `ensure_can_view_encounter(user, clinician_id)`
  - `ensure_can_edit_encounter(user, clinician_id)`
- Rules:
  - Admins can view/edit any encounter within their tenant.
  - Clinicians can only view/edit encounters where `encounter.clinician_id == user.id`.

---

## 5. Persistence and Postgres Integration

### 5.1 Repository abstraction

- `infra/db/repositories.py` defines abstract interfaces:
  - `EncounterRepository`
  - `ClinicalNoteRepository`
  - `TranscriptionJobRepository`

Two concrete implementations:

1. **In-memory** (`infra/db/inmemory.py`)
2. **SQL (Postgres)**:
   - `SqlEncounterRepository` (`sql_encounters.py`)
   - `SqlClinicalNoteRepository` and `SqlTranscriptionJobRepository` (`sql_notes_jobs.py`)

### 5.2 ORM models

In `infra/db/models.py` and `infra/db/models_notes_jobs.py`:

- `EncounterORM`:
  - Columns: `id`, `created_at`, `clinician_id`, `patient_id`, `status`, `title`, `transcription_job_ids`, `tenant_id`.
- `ClinicalNoteORM`:
  - Columns: `id`, `encounter_id`, `created_at`, `updated_at`, `created_by`, `last_edited_by`, `is_finalized`, `subjective`, `objective`, `assessment`, `plan`, `tenant_id`.
- `TranscriptJobORM`:
  - Columns: `id`, `created_at`, `status`, `audio_url`, `language_code`, `target_language`, `result_text`, `translated_text`, `tenant_id`.

`from_domain` / `to_domain` methods map `tenant_id` and all other fields to/from Pydantic models.

### 5.3 Switching to SQL (Postgres)

`infra/db/bootstrap.py`:

- `init_sql_repositories(database_url: Optional[str] = None)`:
  - No‑ops if `USE_SQL_REPOS=false` or `DATABASE_URL` is unset.
  - If enabled:
    - Creates an engine via SQLAlchemy.
    - Calls `Base.metadata.create_all(engine)` to create tables.
    - Builds a `SessionFactory`.
    - Swaps the in‑memory repository singletons to SQL‑backed ones.

Called on FastAPI startup:

- `@app.on_event("startup")` in `main.py`.

### 5.4 Postgres configuration

Environment variables:

- `DATABASE_URL` – e.g.:

  ```text
  postgresql+psycopg2://meduser:medpass@db:5432/med_transcription
  ```

- `USE_SQL_REPOS` – `"true"` to enable SQL repositories.

For local host Postgres (no Docker):

```bash
export DATABASE_URL="postgresql+psycopg2://meduser:medpass@localhost:5432/med_transcription"
export USE_SQL_REPOS=true
```

With `USE_SQL_REPOS=false`, repositories stay in-memory.

---

## 6. Audio Ingestion and Transcription

### 6.1 HTTP upload – `/api/v1/audio/upload`

- Validates `content_type` starts with `audio/`.
- Enforces size limits via `MAX_UPLOAD_BYTES`.
- Persists audio to `AUDIO_UPLOAD_DIR` using `LocalAudioStorageBackend`.
- Creates a `TranscriptJob` via `transcription_service.create_job` (synchronous).
- Optionally:
  - Attaches job to an existing session.
  - Attaches to an existing encounter; or auto‑creates an encounter if not provided.
- Audit event is logged with job ID, encounter ID, filename, size, and subject (if available).

### 6.2 WebSocket live transcription – `/api/v1/audio/ws`

- Accepts binary frames or base64 `AUDIO_BASE64:` text frames.
- Streams audio into a temporary file under `AUDIO_UPLOAD_DIR`.
- Enforces `MAX_WS_BYTES`.
- On each chunk:
  - Invokes ASR backend on buffered audio for a “partial transcript”.
  - Sends JSON payload with `partial_text` and `total_bytes`.
- On `"stop"` text frame:
  - Finalizes by creating a `TranscriptJob` from the buffered audio.
  - Optionally attaches to an existing session.
  - Sends a final JSON payload with job details.
  - Audit event recorded.

---

## 7. Deployment

### 7.1 Local development

Backend:

```bash
pip install -r requirements.txt

# Optional: use Postgres locally
export DATABASE_URL="postgresql+psycopg2://meduser:medpass@localhost:5432/med_transcription"
export USE_SQL_REPOS=true

# Run tests
pytest

# Run API server
uvicorn src.backend.main:app --reload
```

Default behavior:

- `ENABLE_API_AUTH=false` – no auth required.
- `USE_SQL_REPOS=false` – in‑memory repositories.
- `AUDIO_UPLOAD_DIR=uploads`.
- `X-Tenant-ID` defaults to `"default"` if the header is absent.

Web frontend (local):

```bash
cd src/frontend/web
npm install
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev
```

Mobile (local):

```bash
cd src/frontend/mobile
npm install
npm run start   # Expo dev server
```

### 7.2 Docker Compose stack (local / staging)

`docker-compose.yml` defines:

- `db`:
  - `image: postgres:16`
  - `POSTGRES_USER=meduser`, `POSTGRES_PASSWORD=medpass`, `POSTGRES_DB=med_transcription`
  - Exposes `5432` and persists data in `pgdata` volume.

- `backend`:
  - `image: python:3.11-slim`
  - Mounts repo into `/app`.
  - Env:
    - `DATABASE_URL=postgresql+psycopg2://meduser:medpass@db:5432/med_transcription`
    - `USE_SQL_REPOS=true`
    - `ENABLE_API_AUTH=false` (toggle in shared envs)
    - `AUDIO_UPLOAD_DIR=/app/uploads`
  - Command:
    - `pip install -r requirements.txt && uvicorn src.backend.main:app --host 0.0.0.0 --port 8000`
  - Ports:
    - `8000:8000` (optionally `127.0.0.1:8000:8000` for VM deployments)

Start:

```bash
docker compose up
# or: docker-compose up
```

### 7.3 EC2/VM + Nginx + Let’s Encrypt (pilot/staging)

On a VM:

1. **Backend**: run via Docker compose or system `uvicorn`, listening on `127.0.0.1:8000`.
2. **Postgres**: either Docker `db` service or a managed/hosted Postgres.
3. **Nginx**:
   - Terminate TLS on `clinic.example.com`.
   - Serve SPA from `/var/www/clinic-ui`.
   - Proxy `/api/...` (incl. WebSocket `/api/v1/audio/ws`) to `http://127.0.0.1:8000`.

Example Nginx TLS server:

```nginx
server {
    listen 443 ssl http2;
    server_name clinic.example.com;

    ssl_certificate     /etc/letsencrypt/live/clinic.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/clinic.example.com/privkey.pem;

    root /var/www/clinic-ui;
    index index.html;

    location /assets/ {
        try_files $uri =404;
    }

    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        "upgrade";
        proxy_read_timeout  600s;
        proxy_send_timeout  600s;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

Let’s Encrypt with `certbot --nginx -d clinic.example.com` manages certs + renewal.

---

## 8. Tooling and Automation

### 8.1 `setup_all.sh`

Convenience script at repo root to orchestrate:

- Docker checks
- Python dependency install
- Web + mobile Node dependency install
- Backend tests (pytest)
- Web build
- Docker stack startup
- Mobile builds via EAS (optional)

Usage:

```bash
chmod +x setup_all.sh

# Everything: deps, tests, Docker, web build, mobile builds
./setup_all.sh --all

# Only start Docker stack (Postgres + backend)
./setup_all.sh --docker-only

# Backend-only (deps + tests)
./setup_all.sh --backend-only

# Mobile-only (Expo deps + EAS builds)
./setup_all.sh --mobile-only
```

---

## 9. Multitenant API Usage Examples

### 9.1 Create an encounter for tenant A

```bash
curl -X POST https://clinic.example.com/api/v1/encounters/ \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Tenant-ID: tenant-a" \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "pat-123", "title": "Visit 1"}'
```

### 9.2 List encounters for tenant B

```bash
curl "https://clinic.example.com/api/v1/encounters/?status=CREATED" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Tenant-ID: tenant-b"
```

### 9.3 Upload audio and create transcription (tenant A)

```bash
curl -X POST https://clinic.example.com/api/v1/audio/upload \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Tenant-ID: tenant-a" \
  -F "file=@demo.wav;type=audio/wav" \
  -F "language_code=en-US"
```

---

## 10. Future Enhancements (Outline)

- Replace demo ASR/NLP with production‑grade models (self‑hosted or via HIPAA‑eligible cloud).
- Introduce a first‑class Tenant/Organization model and admin UI.
- Add proper DB migrations (Alembic) instead of `create_all`.
- Add RBAC with roles/permissions beyond clinician/admin.
- Implement structured observability (metrics, traces) and hardened logging with PHI scrubbing.

This document describes the current target architecture, multitenancy model, and deployment path from local development through a clinic pilot on a VM with Postgres and Nginx in front of FastAPI.
