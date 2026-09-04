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