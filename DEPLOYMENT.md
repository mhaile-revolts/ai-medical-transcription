# Deployment Guide – Clinic‑Pilot MVP (Backend + Frontend)

This document describes how to deploy the AI medical transcription clinic‑pilot MVP in three environments:

- **Dev** – local development
- **Staging** – synthetic / de‑identified data, full stack with SQL
- **Pilot** – limited clinic pilot with real PHI

It focuses on the FastAPI backend and the React frontend in `src/frontend/web`.

---

## 1. Components and assumptions

### Backend

- FastAPI app: `src/backend/main.py` → `src.backend.main:app`
- Persistence:
  - Set `APP_MODE=demo` explicitly for in-memory development/testing.
  - Other modes require a durable PostgreSQL `DATABASE_URL`.
- Storage:
  - Durable mode stores private audio blobs in PostgreSQL; demo uses
    `AUDIO_UPLOAD_DIR` (default `uploads/`).
- Security:
  - Clerk JWT authentication with tenant-scoped RBAC and audit logging.

### Frontend (web)

- React + Vite app under `src/frontend/web`.
- Talks to the backend through same-origin `/api` routes.
- Uses Clerk session cookies for individual user authentication.

### Mobile client (Android + iOS)

- Expo React Native app under `src/frontend/mobile`.
- Talks to backend via `EXPO_PUBLIC_API_BASE_URL` (set per build profile in `eas.json`).
- The legacy mobile API-key screen is development-only. Do not distribute a
  PHI-capable mobile build until it uses individual Clerk bearer tokens.
- Supports:
  - HTTP audio upload via `/api/v1/audio/upload`.
  - Live WebSocket transcription via `/api/v1/audio/ws` (with partial transcripts).

---

## 2. Environment variables

### Backend (`src/backend/config.py`)

Key settings:

- **ASR / NLP**
  - `ASR_BACKEND` – e.g. `"demo"`, `"whisper"`, `"llama"` (stub for offline/on-device LLaMA-style models), or `"multi_accent"` (accent-aware wrapper around the default backend).
  - `TRANSLATION_BACKEND` – e.g. `"demo"` or `"llm"`.
  - `NLP_NER_BACKEND`, `NLP_CODING_BACKEND`, `NLP_SOAP_BACKEND` – core NLP pipeline knobs:
    - `NLP_NER_BACKEND` – `"demo"` (default), `"med7"`, or `"clinicalbert"`.
    - `NLP_CODING_BACKEND` – `"demo"` (default) or `"umlscoder"` / `"umls"` for ontology-based terminology mapping.
    - `NLP_SOAP_BACKEND` – `"demo"` (default) or `"llm"` for LLM-generated SOAP notes.
  - `UMLS_CONCEPTS_PATH` – absolute or relative path to a JSON or JSONL file containing concept records with at least a `"name"` field and optionally `"code"` and `"system"` (used by `umlscoder`).
  - `UMLS_MIN_SIMILARITY` – minimum string similarity (0–1, default `0.85`) required to assign a code when using `umlscoder`.
  - `ALLOW_CLOUD_LLM` – `"true"` (default) to permit LLM-based translation when `TRANSLATION_BACKEND=llm`; set to `"false"` to hard-disable cloud LLM usage even if `OPENAI_API_KEY` is set.
  - `REQUIRE_ON_PREM_ONLY` – `"true"` to signal that deployments must avoid external SaaS/cloud dependencies where possible; enforcement is implemented in individual backends and should be combined with infra controls.

- **Audio storage**
  - Durable mode stores private audio in PostgreSQL and exposes only opaque
    `db-audio://` references.
  - `AUDIO_UPLOAD_DIR` – demo-mode upload directory (default: `uploads`).

- **Security / auth**
  - Set `APP_ENV=production` (or `staging`) for any deployed environment.
    Production rejects demo mode, wildcard CORS, missing Clerk issuer, and
    missing JWT verification configuration at startup.
  - `CLERK_ISSUER` – optional expected Clerk issuer URL. When omitted, the
    backend derives it from the provisioned `CLERK_PUBLISHABLE_KEY`.
  - `CLERK_AUDIENCE` – expected token audience (when configured in Clerk).
  - `CLERK_JWKS_URL` – optional Clerk JWKS endpoint (derived from the issuer
    when omitted); alternatively set
    `CLERK_JWT_PUBLIC_KEY` to a PEM public key supplied through a secret
    manager. Send the Clerk session JWT as `Authorization: Bearer <JWT>` or
    the secure `__session` cookie. The verified `sub`, `org_id`/`tenant_id`,
    and `org_role`/`role` claims determine identity, tenant, and role.
  - `X-API-Key` and `X-Tenant-ID` are not authentication controls and are
    ignored for production identity. `X-Test-*` overrides are enabled only
    when `APP_ENV=development` or `test`.

- **Multitenancy**
  - Tenant context comes only from verified JWT organization claims. Data in
    encounters, notes, transcription jobs, and sessions is partitioned by it.

- **Request limits**
  - `MAX_UPLOAD_BYTES` – max HTTP upload size in bytes (default 10 MiB).
  - `MAX_WS_BYTES` – max WebSocket audio bytes per connection (default 10 MiB).

- **CORS**
  - `CORS_ALLOW_ORIGINS` – comma-separated explicit HTTPS origins. `"*"` is
    development-only and is rejected in staging/production.
  - Serve the web app and `/api` from one public origin (use a reverse proxy).
    Clerk web authentication is cookie-based; do not point the browser at a
    separately hosted API origin.

- **PHI retention and deletion**
  - `PHI_AUDIO_RETENTION_DAYS` (default 30), `PHI_TRANSCRIPT_RETENTION_DAYS`
    (default 2555), and `AUDIT_RETENTION_DAYS` (default 2555) are required
    positive values outside development/test. Run a documented, tenant-scoped
    retention worker at least daily by invoking `POST /api/v1/patients/retention/purge`
    as a tenant administrator, and verify backup expiration separately.
  - Patient deletion is an administrator-only, tenant-scoped operation. It
    must delete the patient's encounters, clinical notes, jobs, and private
    audio and emit an ID-only audit event. Keep immutable audit records under
    the configured audit-retention policy unless legal requirements say
    otherwise.
  - Store `CLERK_JWKS_URL`, PEM keys, database credentials, and provider keys
    in the platform secret manager; never commit them, put them in frontend
    builds, or log JWTs/transcripts.
  - Set `AUDIT_LOG_PATH` to a protected persistent path. The app opens it at
    startup with mode `0600` and UTC daily rotation for `AUDIT_RETENTION_DAYS`.
    Ship these files to an append-only, access-controlled archive; production
    startup fails if the local sink cannot be configured.

- **Database / repositories**
  - `DATABASE_URL` – SQLAlchemy database URL. For Postgres (recommended beyond local dev):
    - `postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME`
  - `APP_MODE` – set `"demo"` only for ephemeral development. Durable mode
    fails startup when `DATABASE_URL` is absent or unavailable.
  - `USE_SQL_REPOS` – legacy compatibility switch to enable SQL repositories.
  - Apply schema changes before application startup: `alembic upgrade head`.

- **Optional MultiChain (private blockchain) audit logging**
  - `MULTICHAIN_ENABLED` – `"true"` to enable mirroring of audit events into a MultiChain stream.
  - `MULTICHAIN_RPC_SCHEME` – `"http"` or `"https"` for the JSON-RPC endpoint (default `"http"`).
  - `MULTICHAIN_RPC_HOST` – host of the MultiChain RPC node (e.g. `"multichain"` in Docker, or an external hostname).
  - `MULTICHAIN_RPC_PORT` – RPC port (default `6824`).
  - `MULTICHAIN_RPC_USER` / `MULTICHAIN_RPC_PASSWORD` – RPC basic auth credentials.
  - `MULTICHAIN_CHAIN_NAME` – logical chain name (informational in the app, but should match your node config).
  - `MULTICHAIN_AUDIT_STREAM` – name of the MultiChain stream used for audit events (default `"audit"`).

### Frontend (`src/frontend/web`)

- `VITE_CLERK_PUBLISHABLE_KEY` is provisioned by Replit Clerk Auth.
- The browser always uses same-origin `/api`; configure the reverse proxy, not
  a client-side API base URL.

### Mobile (`src/frontend/mobile`)

- `EXPO_PUBLIC_API_BASE_URL` – base URL of the backend used by the mobile app. This is typically set via `env` in `eas.json` per profile (e.g., staging vs pilot) but can also be provided at runtime for local dev.

---

## 3. Dev environment (local)

### 3.1. Backend – dev

> For dev you can run explicitly in demo mode, or point at Postgres. Staging and pilot must use durable mode.

1. **Install dependencies**

   ```bash
   # from repo root
   pip install -r requirements.txt
   ```

2. **Choose an explicit storage mode**

   For synthetic-data demo development:

   ```bash
   export APP_MODE=demo
   ```

   For durable development, set Postgres and apply migrations:

   ```bash
   export APP_MODE=durable
   export DATABASE_URL="postgresql+psycopg2://meduser:medpass@localhost:5432/med_transcription"
   alembic upgrade head
   ```

   Durable startup fails if the database is unreachable or not at the required
   migration revision.

2. **Run tests (optional but recommended)**

   ```bash
   pytest
   ```

3. **Run FastAPI app**

   ```bash
   uvicorn src.backend.main:app --reload
   ```

   By default:

   - Development requests may use the explicit `X-Test-*` identity headers.
   - `APP_MODE=demo` → in-memory records and `AUDIO_UPLOAD_DIR=uploads`.
   - The test identity defaults to the synthetic `"default"` tenant.

### 3.2. Frontend – dev

1. **Install deps**

   ```bash
   cd src/frontend/web
   npm install
   ```

2. **Run dev server**

   ```bash
   npm run dev
   ```

3. **Use the app**

   - Visit the URL printed by Vite (default `http://localhost:5173`).
   - Sign in with an individual Clerk development account.
   - The account must have `tenant_id` and `role` (or `org_id` and `org_role`)
     in its verified session claims before clinical routes are available.

### 3.3. Mobile – dev

1. **Install deps**

   ```bash
   cd src/frontend/mobile
   npm install
   ```

2. **Run Expo dev server**

   ```bash
   npm run start
   ```

3. **Backend URL & auth**

   - By default the app uses `EXPO_PUBLIC_API_BASE_URL` if set, otherwise `http://localhost:8000`.
   - The current mobile authentication UI is retained only for synthetic local
     development and is rejected by staging/production APIs.

4. **Audio flows**

   - HTTP upload: records audio and POSTs to `/api/v1/audio/upload`.
   - Live transcription: opens a WebSocket to `/api/v1/audio/ws`, streams audio, and displays partial transcripts in real time.

---

## 4. Staging environment (synthetic / de‑identified data)

Staging should mirror pilot as closely as possible, but use only synthetic or de‑identified audio.

### 4.1. Backend – staging

**Goal:** use a real database, but not yet handle real PHI.

1. **Provision a DB**

   - Option A: managed Postgres (recommended).
   - Option B: SQLite file on a persistent disk (for quick tests).

   Example Postgres URL:

   ```text
   postgresql+psycopg2://user:password@host:5432/clinic_mvp_staging
   ```

2. **Set environment variables**

   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:password@host:5432/clinic_mvp_staging"
   export APP_MODE=durable
    export APP_ENV=staging
    export AUDIT_LOG_PATH=/var/log/clinic/audit.jsonl

   export CORS_ALLOW_ORIGINS="https://staging-clinic-ui.example.com"
   alembic upgrade head
   ```

3. **Run backend**

   - Use a process manager or container orchestration (e.g. systemd, Docker, Kubernetes) as you prefer.
- The included Dockerfile and Compose backend command run `alembic upgrade head`
  before Uvicorn. Compose also waits for PostgreSQL's health check first.
   - On startup:
     - `@app.on_event("startup")` calls `init_sql_repositories()`.
     - This:
       - Connects to `DATABASE_URL`.
      - Verifies connectivity and the Alembic schema revision.
      - Wires SQL repositories and private database-backed audio storage.
   - If `MULTICHAIN_ENABLED=true` and the RPC variables are set, audit events
     will also be mirrored into the configured MultiChain stream.

4. **ASR / NLP backends**

   - For staging, you can still use `"demo"` backends, or point to non‑PHI model instances.
   - Set `ASR_BACKEND`, `NLP_*_BACKEND` as needed.

### 4.2. Frontend – staging

1. **Build frontend**

   From `src/frontend/web`:

   ```bash
   npm install
   npm run build
   ```

   This produces static assets in `dist/`.

2. **Serve static files**

   Options:

   - Simple Nginx or Apache serving `dist/` with proper caching.
   - Or use a static host (Netlify, S3+CloudFront, etc.) configured to talk to the backend over HTTPS.

### 4.3. Mobile – staging

Staging mobile builds are typically distributed internally (APK / TestFlight) and pointed at the staging API.

1. **Configure `eas.json`**

   In `src/frontend/mobile/eas.json`, set:

   - `build.preview.env.EXPO_PUBLIC_API_BASE_URL=https://staging-clinic-api.example.com`

2. **Build Android APK (internal)**

   ```bash
   cd src/frontend/mobile
   eas build --platform android --profile preview
   ```

3. **Build iOS app (TestFlight/internal)**

   ```bash
   cd src/frontend/mobile
   eas build --platform ios --profile preview
   ```

---

## 5. Pilot environment (real PHI)

This is where you must be careful: most work here is infra and policy, not code.

### 5.1. Backend – pilot

1. **Infrastructure (high‑level)**

   - Run backend and DB in a **private network** (VPC/VNet), ideally single region.
   - Expose only the HTTPS API via a load balancer or API gateway.
   - Restrict DB access to app nodes only.
   - Enable encryption at rest for PostgreSQL, including its private audio blobs.

2. **Env variables (example)**

   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:password@securedb:5432/clinic_mvp_pilot"
   export APP_MODE=durable
    export APP_ENV=production
    export AUDIT_LOG_PATH=/var/log/clinic/audit.jsonl

   export MAX_UPLOAD_BYTES=$((20 * 1024 * 1024))    # e.g. 20 MiB if needed
   export MAX_WS_BYTES=$((20 * 1024 * 1024))

   export CORS_ALLOW_ORIGINS="https://pilot-clinic-ui.example.com"
   ```

3. **ASR / NLP with PHI**

   - Ensure any external ASR/NLP/LLM providers:
     - Have appropriate agreements (e.g. BAA).
     - Have settings that avoid training on your data by default.
   - For maximum control, consider self‑hosted ASR and NLP in the same private network.

4. **Logging and audit**

   - Configure application logs to go to a PHI‑safe log sink.
   - Ensure logs do NOT include raw transcripts or notes; rely on IDs and metadata.
   - Monitor the `audit` logger output; ensure rotation and retention policies are configured.

5. **Backups and DR**

   - Enable automated DB backups (e.g. daily snapshots).
   - Document a tested restore procedure (at least in staging).
   - Include private audio blobs in database backup and restore tests.

### 5.2. Frontend – pilot

1. **Build the web application**

   ```bash
   cd src/frontend/web
   npm install
   npm run build
   ```

2. **Serve static content over HTTPS**

   - Use an HTTPS-enabled reverse proxy that serves the frontend and forwards
     `/api` and WebSocket traffic to FastAPI on the same public origin.
   - Restrict access (e.g. by clinic IP range, VPN, or SSO gateway).

3. **Device & browser considerations**

   - Use up‑to‑date browsers.
   - Ensure clinic devices are managed (disk encryption, auto‑lock, etc.).

### 5.3. Mobile – pilot

Pilot mobile builds should target the pilot API and be distributed only to approved clinician devices.

The current mobile client is **not approved for PHI** because it still uses a
shared API-key flow that production rejects. Complete individual Clerk mobile
authentication before following the build steps below.

1. **Configure `eas.json`**

   In `src/frontend/mobile/eas.json`, set:

   - `build.production.env.EXPO_PUBLIC_API_BASE_URL=https://pilot-clinic-api.example.com`

2. **Build Android AAB (Play Store) or managed distribution**

   ```bash
   cd src/frontend/mobile
   eas build --platform android --profile production
   ```

3. **Build iOS app (App Store/TestFlight)**

   ```bash
   cd src/frontend/mobile
   eas build --platform ios --profile production
   eas submit --platform ios
   ```

4. **Mobile device considerations**

   - Enroll devices in a mobile device management (MDM) solution where possible.
   - Enforce screen lock, disk encryption, and OS updates.

---

## 6. Operational checklist

Before going live with real PHI:

- [ ] **Auth and access**
  - Individual Clerk identities are provisioned with verified tenant and role claims.
  - Shared API keys and caller-selected tenant headers are rejected.
  - Backend/API not reachable without auth.

- [ ] **Data persistence**
  - `APP_MODE=durable`, `DATABASE_URL` set, and `alembic upgrade head` applied.
  - Encounters, notes, jobs, conversation sessions, users, and private audio
    persist through restarts.
  - Backups configured and restore tested in staging.

- [ ] **Security**
  - HTTPS termination in place.
  - DB and storage volumes encrypted at rest.
  - Network access restricted (firewalls/VPC rules).

- [ ] **Monitoring & audit**
  - Error logs being collected (no raw transcripts or notes in log messages).
  - Basic metrics (requests, errors) available.
  - Alerts for major failures (e.g. DB down, ASR failures, MultiChain RPC failures) configured.
  - Audit logs recording upload, live transcription, analysis, and export events with IDs and timestamps.
  - If MultiChain is enabled, `/api/v1/system/blockchain/health` is returning `{"status": "ok"}`.

- [ ] **Frontend**
  - Frontend and `/api` are served from the same HTTPS origin.
  - Visible environment banner ("Pilot – real PHI") to avoid confusion.
  - Clinician quick‑start guide distributed.

- [ ] **Dry run**
  - Run full flows in staging with realistic (but non‑PHI) data.
  - Shadow‑mode on real but de‑identified audio if allowed.

---

## 7. Commands summary

### Backend (local dev)

```bash
# install
pip install -r requirements.txt

# run tests
pytest

# run server (host Python)
uvicorn src.backend.main:app --reload

# OR: use Docker stack (Postgres + backend)
docker compose up
# or
# docker-compose up
```

### Frontend (local dev)

```bash
cd src/frontend/web
npm install
npm run dev
```

### Frontend (build for staging/pilot)

```bash
cd src/frontend/web
npm run build
# deploy contents of dist/ to your static host
```

### Mobile (build via EAS)

```bash
cd src/frontend/mobile
# preview / staging
EAS_NO_VCS=1 eas build --platform android --profile preview
EAS_NO_VCS=1 eas build --platform ios --profile preview

# production / pilot
EAS_NO_VCS=1 eas build --platform android --profile production
EAS_NO_VCS=1 eas build --platform ios --profile production
```

This document should give you a clear path from local dev to a small, controlled clinic pilot.
