# Node runtime is needed only for the server-side Replit connector SDK used by
# the optional ElevenLabs ASR backend.
FROM node:20-bookworm-slim AS node-runtime

# Base Python image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Replit's connector SDK is a zero-secret bridge to connected provider APIs.
COPY --from=node-runtime /usr/local /usr/local
RUN npm install --prefix /app --no-save --package-lock=false @replit/connectors-sdk

# Environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System dependencies (build tools for any compiled Python deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the API and migrations without root privileges.
RUN useradd --create-home --uid 10001 clinic \
    && chown -R clinic:clinic /app
USER clinic

# Expose FastAPI default port
EXPOSE 8000

# Apply schema migrations before accepting traffic. Startup still verifies the
# exact revision and fails closed if migration or database readiness fails.
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.backend.main:app --host 0.0.0.0 --port 8000"]
