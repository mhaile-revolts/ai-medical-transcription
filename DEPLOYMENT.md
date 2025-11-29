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
  - In‑memory by default (dev/tests).
  - Optional SQLAlchemy + DB when `USE_SQL_REPOS=true` and `DATABASE_URL` is set.
- Storage:
  - Local filesystem via `AUDIO_UPLOAD_DIR` (default `uploads/`).
- Security:
  - API key auth via `ENABLE_API_AUTH` + `API_KEYS`.
  - Basic RBAC (clinician/admin) and audit logging.

### Frontend (web)

- React + Vite app under `src/frontend/web`.
- Talks to backend via `VITE_API_BASE_URL`.
- Uses `X-API-Key` header for auth (when enabled).

### Mobile client (Android + iOS)

- Expo React Native app under `src/frontend/mobile`.
- Talks to backend via `EXPO_PUBLIC_API_BASE_URL` (set per build profile in `eas.json`).
- Uses `X-API-Key` header for auth (when enabled) entered by the user in the mobile UI.
- Supports:
  - HTTP audio upload via `/api/v1/audio/upload`.
  - Live WebSocket transcription via `/api/v1/audio/ws` (with partial transcripts).

---

## 2. Environment variables

### Backend (`src/backend/config.py`)

Key settings:

- **ASR / NLP**
  - `ASR_BACKEND` – e.g. `"demo"`, `"whisper"`, or `"llama"` (stub for offline/on-device LLaMA-style models).
  - `TRANSLATION_BACKEND` – e.g. `"demo"` or `"llm"`.
  - `NLP_NER_BACKEND`, `NLP_CODING_BACKEND`, `NLP_SOAP_BACKEND` – currently `"demo"`.

- **Audio storage**
  - `AUDIO_UPLOAD_DIR` – directory for uploaded audio (default: `uploads`).

- **Security / auth**
  - `ENABLE_API_AUTH` – `"true"` or `"false"` (default `"false"`).
  - `API_KEYS` – comma‑separated list of allowed API keys when auth is enabled.
  - `X-API-Key` – HTTP header used by clients to authenticate when API auth is enabled.

- **Multitenancy**
  - `X-Tenant-ID` – HTTP header that selects the logical tenant/clinic for each request.
    - If omitted, the backend uses a default tenant ("default").
    - Data in encounters, notes, transcription jobs, and sessions is partitioned by tenant.

- **Request limits**
  - `MAX_UPLOAD_BYTES` – max HTTP upload size in bytes (default 10 MiB).
  - `MAX_WS_BYTES` – max WebSocket audio bytes per connection (default 10 MiB).

- **CORS**
  - `CORS_ALLOW_ORIGINS` – comma‑separated allowed origins (default `"*"`).

- **Database / repositories**
  - `DATABASE_URL` – SQLAlchemy database URL. For Postgres (recommended beyond local dev):
    - `postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME`
  - `USE_SQL_REPOS` – `"true"` to enable SQL‑backed repositories for encounters, notes, and jobs; otherwise in‑memory.

### Frontend (`src/frontend/web`)

- `VITE_API_BASE_URL` – base URL of the backend, e.g. `http://localhost:8000` or your staging/pilot URL.

### Mobile (`src/frontend/mobile`)

- `EXPO_PUBLIC_API_BASE_URL` – base URL of the backend used by the mobile app. This is typically set via `env` in `eas.json` per profile (e.g., staging vs pilot) but can also be provided at runtime for local dev.

---

## 3. Dev environment (local)

### 3.1. Backend – dev

> For dev you can run entirely in‑memory, or point at a local Postgres instance. The recommended DB for staging/pilot is Postgres.

1. **Install dependencies**

   ```bash
   # from repo root
   pip install -r requirements.txt
   ```

2. **(Optional) Configure Postgres for local dev**

   If you prefer Postgres without Docker, set for example:

   ```bash
   export DATABASE_URL="postgresql+psycopg2://meduser:medpass@localhost:5432/med_transcription"
   export USE_SQL_REPOS=true
   ```

   With `USE_SQL_REPOS=false` (default), encounters/notes/jobs are stored in memory only.

2. **Run tests (optional but recommended)**

   ```bash
   pytest
   ```

3. **Run FastAPI app**

   ```bash
   uvicorn src.backend.main:app --reload
   ```

   By default:

   - `ENABLE_API_AUTH=false` → no auth required.
   - `USE_SQL_REPOS=false` → in‑memory storage for encounters/notes/jobs.
   - `AUDIO_UPLOAD_DIR=uploads` in the project root.
   - Multitenancy: if `X-Tenant-ID` is omitted, all requests use the "default" tenant.

### 3.2. Frontend – dev

1. **Install deps**

   ```bash
   cd src/frontend/web
   npm install
   ```

2. **Configure API base URL**

   Create `.env.local` in `src/frontend/web`:

   ```env
   VITE_API_BASE_URL=http://localhost:8000
   ```

3. **Run dev server**

   ```bash
   npm run dev
   ```

4. **Use the app**

   - Visit the URL printed by Vite (default `http://localhost:5173`).
   - If auth is disabled, you can go directly to `/encounters`.
   - Otherwise, go to `/settings` and enter your API key.

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
   - If API key auth is enabled on the backend, enter your key in the mobile app under the **Authentication** section; it is sent as `X-API-Key` for HTTP and WebSocket calls.

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
   export USE_SQL_REPOS=true

   export ENABLE_API_AUTH=true
   export API_KEYS="staging-key-1,staging-key-2"

   export AUDIO_UPLOAD_DIR=/var/lib/clinic-mvp-staging/uploads
   export CORS_ALLOW_ORIGINS="https://staging-clinic-ui.example.com"
   ```

3. **Run backend**

   - Use a process manager or container orchestration (e.g. systemd, Docker, Kubernetes) as you prefer.
   - On startup:
     - `@app.on_event("startup")` calls `init_sql_repositories()`.
     - This:
       - Connects to `DATABASE_URL`.
       - Calls `Base.metadata.create_all(engine)` for `encounters`, `clinical_notes`, `transcription_jobs`.
       - Swaps repository singletons to their SQL implementations.

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

2. **Set staging API base URL**

   In staging CI/deploy pipeline, set:

   ```env
   VITE_API_BASE_URL=https://staging-clinic-api.example.com
   ```

   Then rebuild for staging.

3. **Serve static files**

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
   - Enable encryption at rest for DB and disk/volume where `AUDIO_UPLOAD_DIR` lives.

2. **Env variables (example)**

   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:password@securedb:5432/clinic_mvp_pilot"
   export USE_SQL_REPOS=true

   export ENABLE_API_AUTH=true
   export API_KEYS="pilot-clinic-key-1,pilot-clinic-key-2"

   export AUDIO_UPLOAD_DIR=/var/lib/clinic-mvp-pilot/uploads
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
   - Consider periodic snapshots of `AUDIO_UPLOAD_DIR` as per retention policy.

### 5.2. Frontend – pilot

1. **Build with pilot API URL**

   ```env
   VITE_API_BASE_URL=https://pilot-clinic-api.example.com
   ```

   Then:

   ```bash
   cd src/frontend/web
   npm install
   npm run build
   ```

3. **Serve static content over HTTPS**

   - Use an HTTPS‑enabled frontend (e.g. Nginx with TLS) or a managed static host that meets your PHI/infrastructure requirements.
   - Restrict access (e.g. by clinic IP range, VPN, or SSO gateway).

3. **Device & browser considerations**

   - Use up‑to‑date browsers.
   - Ensure clinic devices are managed (disk encryption, auto‑lock, etc.).

### 5.3. Mobile – pilot

Pilot mobile builds should target the pilot API and be distributed only to approved clinician devices.

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
  - `ENABLE_API_AUTH=true` in pilot.
  - API keys issued and safely stored.
  - Backend/API not reachable without auth.

- [ ] **Data persistence**
  - `USE_SQL_REPOS=true` and `DATABASE_URL` set.
  - Encounters, notes, and jobs persist through restarts.
  - Backups configured and restore tested in staging.

- [ ] **Security**
  - HTTPS termination in place.
  - DB and storage volumes encrypted at rest.
  - Network access restricted (firewalls/VPC rules).

- [ ] **Monitoring & audit**
  - Error logs being collected (no raw transcripts or notes in log messages).
  - Basic metrics (requests, errors) available.
  - Alerts for major failures (e.g. DB down, ASR failures) configured.
  - Audit logs recording upload, live transcription, analysis, and export events with IDs and timestamps.

- [ ] **Frontend**
  - Correct `VITE_API_BASE_URL` for pilot.
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
VITE_API_BASE_URL=https://your-api.example.com npm run build
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
