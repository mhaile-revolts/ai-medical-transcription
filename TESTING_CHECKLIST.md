# Testing & Validation Checklist

This checklist describes how to validate the system end-to-end in each environment: **dev**, **staging**, and **pilot**.

Use it when promoting a new build or before starting a clinic session.

---

## 1. Local dev

### 1.1 Backend

1. Start the backend:
   ```bash
   uvicorn src.backend.main:app --reload
   ```
2. Check health:
   - `GET http://localhost:8000/health` → `{ "status": "ok" }`.
   - `GET http://localhost:8000/api/v1/health` → `{ "status": "ok", "version": "v1" }`.
3. Run tests (optional but recommended):
   ```bash
   pytest
   ```

### 1.2 Web app

1. Start the dev server:
   ```bash
   cd src/frontend/web
   npm install
   npm run dev
   ```
2. In the browser:
   - Confirm you can load the app.
   - If API auth is enabled, enter your API key and confirm calls succeed.

### 1.3 Mobile app (simulator or device)

1. Run Expo dev server:
   ```bash
   cd src/frontend/mobile
   npm install
   npm run start
   ```
2. Launch on a simulator or device.
3. In the **Authentication** section of the app:
   - If API auth is enabled, enter a valid API key.
4. Validate flows:
   - **Backend Health** shows `{ "status": "ok" }`.
   - **Record & Upload Audio**:
     - Start Recording → speak → Stop & Upload.
     - A job appears in the **Uploaded Job** and **Job** cards.
   - **Live Transcription (WebSocket)**:
     - Start Live Session → speak → Stop & Send.
     - Partial Transcript updates during recording.
     - A final job appears in the **Job** card.
   - **Analyze Transcription**:
     - With a job selected, tap Analyze Job.
     - Analysis card displays entities / SOAP-style information.
     - Confirm additional analysis details are present in responses (codes, billing risk, segments with emotion) via logs or API inspector when needed.

---

## 2. Staging

Goal: validate with staging DB, staging API URL, and staging mobile builds.

### 2.1 Backend

1. Ensure env vars are set for staging (example):
   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:password@host:5432/clinic_mvp_staging"
   export USE_SQL_REPOS=true
   export ENABLE_API_AUTH=true
   export API_KEYS="staging-key-1,staging-key-2"
   ```
2. Deploy or start the backend using your staging process (Docker, Kubernetes, etc.).
3. From a machine that can reach staging:
   - `GET https://staging-clinic-api.example.com/health`
   - `GET https://staging-clinic-api.example.com/api/v1/health`.
   - Confirm `401` when missing/invalid API key on protected routes.

### 2.2 Web app (staging)

1. Build with staging API base URL:
   ```bash
   cd src/frontend/web
   VITE_API_BASE_URL=https://staging-clinic-api.example.com npm run build
   ```
2. Deploy `dist/` to your staging static host.
3. In the browser (staging URL):
   - Enter a staging API key.
   - Exercise core flows (upload audio, view encounters, run analysis).

### 2.3 Mobile app (staging)

1. Ensure `src/frontend/mobile/eas.json` has:
   - `build.preview.env.EXPO_PUBLIC_API_BASE_URL=https://staging-clinic-api.example.com`.
2. Build and distribute staging mobile apps:
   ```bash
   cd src/frontend/mobile
   eas build --platform android --profile preview
   eas build --platform ios --profile preview
   ```
3. On staging devices:
   - Enter a staging API key in Authentication.
   - Repeat the **Local dev** mobile checks, but against the staging URL.

Additional staging checks:

- Verify request/response logs show no PHI in logs beyond what is expected.
- Confirm DB entries are created for encounters, jobs, and notes.
- Validate new analysis and intelligence endpoints:
  - `POST /api/v1/transcriptions/{job_id}/analyze` returns entities, SOAP note, codes, billing_risk, and segments (with `emotion` populated).
  - `POST /api/v1/encounters/{encounter_id}/decision-support` returns at least zero or more suggestions without errors.
  - `POST /api/v1/encounters/{encounter_id}/decision-support/regulated` returns `enabled=false` and no suggestions.
  - `GET /api/v1/patients/{patient_id}/timeline` returns a stable, time-ordered list of events.
  - `GET /api/v1/analytics/clinic-overview` and `/analytics/clinician-summary` return sensible metrics for synthetic data.
  - `GET /api/v1/scribe/queue` and related scribe endpoints work as expected for users with the SCRIBE role.

---

## 3. Pilot (real PHI)

Run these checks before any new pilot rollout.

### 3.1 Backend

1. Confirm pilot env vars (example):
   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:password@securedb:5432/clinic_mvp_pilot"
   export USE_SQL_REPOS=true
   export ENABLE_API_AUTH=true
   export API_KEYS="pilot-clinic-key-1,pilot-clinic-key-2"
   export CORS_ALLOW_ORIGINS="https://pilot-clinic-ui.example.com"
   ```
2. Confirm:
   - `/health` and `/api/v1/health` return OK over HTTPS.
   - All protected routes require a valid API key.

### 3.2 Web app (pilot)

1. Build with pilot API base URL:
   ```bash
   cd src/frontend/web
   VITE_API_BASE_URL=https://pilot-clinic-api.example.com npm run build
   ```
2. Deploy to the pilot frontend host.
3. From a pilot workstation:
   - Log in / enter API key.
   - Run a **full encounter flow** with synthetic or non-identifying data first:
     - Upload audio.
     - Wait for transcription completion.
     - Run analysis.
     - Review the generated note.

### 3.3 Mobile app (pilot)

1. Ensure `eas.json` has:
   - `build.production.env.EXPO_PUBLIC_API_BASE_URL=https://pilot-clinic-api.example.com`.
2. Build pilot mobile apps:
   ```bash
   cd src/frontend/mobile
   eas build --platform android --profile production
   eas build --platform ios --profile production
   ```
3. On pilot devices:
   - Enter a pilot API key.
   - Use non-identifying test audio to run through:
     - Record & Upload Audio.
     - Live Transcription.
     - Analyze Transcription.
4. Once satisfied, switch to real PHI per your clinic policy.

### 3.4 Monitoring, analytics & audit checks

For any environment handling PHI (pilot, and possibly staging):

- Verify that:
  - Error logs do not contain raw transcripts or notes.
  - Audit logs record key actions (upload, live transcription, analyze, decision-support, export) with IDs and timestamps.
  - Analytics endpoints return non-empty but PHI-free aggregates.
  - Alerting is configured for major failures (backend down, DB connectivity issues).

Run these checks after each backend or mobile release to catch issues before clinicians do.
