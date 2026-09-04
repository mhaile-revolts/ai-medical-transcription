# Running on Replit

The main workflow starts the FastAPI backend on internal port 8000 and the Vite/React web app on public port 5000.

- Start or restart the **Start application** workflow to run the project.
- Open the web preview to use the clinic frontend.
- The frontend sends `/api` requests through Vite's same-origin development proxy to FastAPI.
- The backend runs with the repository's default demo/in-memory settings, so no external credentials are required.
- Data stored in memory is reset when the workflow restarts. Uploaded audio uses the local `uploads/` directory.
- API health check: `/health`
- Interactive API documentation: `/docs` on backend port 8000 (internal during the combined development workflow).

The Expo mobile app is not started by the main workflow.

## OCHIN Epic mobile workflow

The mobile app uses a safety-gated visit flow: patient ID lookup, demographic
confirmation, active Epic encounter selection, recording-consent confirmation,
then recording. Audio cannot be attached to the selected visit until the
backend has revalidated the patient and encounter and created a local encounter
with consent evidence.

- `APP_MODE=demo` uses clearly labeled synthetic SMART/FHIR fixtures.
- Non-demo environments fail closed unless `OCHIN_SMART_FHIR_BASE_URL`,
  `OCHIN_SMART_ISSUER`, and `OCHIN_SMART_CLIENT_ID` are configured.
- Clerk authenticates the clinician to this application. OCHIN SMART
  authorization is a separate production integration and must use an
  OCHIN-approved app registration, redirect URI, scopes, and token flow.
- Never place OCHIN client credentials or access tokens in frontend code.