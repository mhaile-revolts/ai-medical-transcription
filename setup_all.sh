#!/usr/bin/env bash
set -euo pipefail

# setup_all.sh
#
# Helper script to:
# - Check/install core tooling (Docker, Node, Python deps) where possible
# - Start Postgres + backend via docker-compose
# - Run backend/frontend tests
# - Trigger Android (APK/AAB) and iOS builds via EAS (if configured)
#
# NOTE:
# - This script targets macOS + Homebrew for optional installs.
# - It will NOT install Xcode, Android Studio, or EAS credentials for you.
# - For production/pilot mobile builds, make sure your EAS config and
#   credentials are already set up.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[setup] WARN:${NC} $*"; }
err() { echo -e "${RED}[setup] ERROR:${NC} $*" >&2; }

have_cmd() { command -v "$1" >/dev/null 2>&1; }

maybe_install_with_brew() {
  local pkg="$1"
  if ! have_cmd brew; then
    warn "Homebrew not found; please install $pkg manually. See https://brew.sh/"
    return 0
  fi
  if brew list "$pkg" >/dev/null 2>&1; then
    log "$pkg already installed via Homebrew"
  else
    log "Installing $pkg via Homebrew..."
    brew install "$pkg"
  fi
}

check_or_install_docker() {
  if have_cmd docker; then
    log "Docker is installed: $(docker --version 2>/dev/null || true)"
  else
    warn "Docker is not installed. On macOS, install Docker Desktop from https://www.docker.com/products/docker-desktop/"
  fi

  if have_cmd docker-compose; then
    log "docker-compose is installed: $(docker-compose --version 2>/dev/null || true)"
  else
    if have_cmd docker; then
      warn "docker-compose not found; modern Docker may support 'docker compose' subcommand instead."
    else
      warn "Docker and docker-compose missing; skipping container checks."
    fi
  fi
}

install_python_deps() {
  if ! have_cmd python3; then
    warn "python3 is not installed; install via Homebrew (brew install python) or from python.org."
    return 0
  fi
  if ! have_cmd pip3; then
    warn "pip3 not found; ensure your Python installation includes pip."
    return 0
  fi
  if [ -f "requirements.txt" ]; then
    log "Installing Python dependencies from requirements.txt..."
    pip3 install -r requirements.txt
  else
    warn "requirements.txt not found; skipping Python deps install."
  fi
}

run_backend_tests() {
  if ! have_cmd pytest; then
    warn "pytest not found; install with 'pip install pytest' if you want to run backend tests. Skipping."
    return 0
  fi
  log "Running backend tests with pytest..."
  pytest
}

install_node_deps_web() {
  if ! have_cmd npm; then
    warn "npm not found; install Node.js (e.g., via Homebrew: brew install node). Skipping web deps."
    return 0
  fi
  if [ -d "src/frontend/web" ]; then
    log "Installing web frontend dependencies (npm install)..."
    (cd src/frontend/web && npm install)
  else
    warn "src/frontend/web not found; skipping web deps."
  fi
}

run_web_tests_and_build() {
  if [ ! -d "src/frontend/web" ]; then
    warn "src/frontend/web not found; skipping web tests/build."
    return 0
  fi
  if ! have_cmd npm; then
    warn "npm not available; cannot run web tests/build."
    return 0
  fi
  log "Running web build (npm run build)..."
  (cd src/frontend/web && npm run build)
}

install_node_deps_mobile() {
  if ! have_cmd npm; then
    warn "npm not found; install Node.js to work on mobile builds. Skipping mobile deps."
    return 0
  fi
  if [ -d "src/frontend/mobile" ]; then
    log "Installing mobile (Expo) dependencies (npm install)..."
    (cd src/frontend/mobile && npm install)
  else
    warn "src/frontend/mobile not found; skipping mobile deps."
  fi
}

check_eas_cli() {
  if have_cmd eas; then
    log "EAS CLI found: $(eas --version 2>/dev/null || true)"
  else
    warn "EAS CLI not found. Install with: npm install -g eas-cli"
  fi
}

build_android() {
  if [ ! -d "src/frontend/mobile" ]; then
    warn "src/frontend/mobile not found; skipping Android build."
    return 0
  fi
  if ! have_cmd eas; then
    warn "EAS CLI not available; cannot trigger Android build."
    return 0
  fi
  log "Triggering Android build via EAS (preview profile)..."
  (cd src/frontend/mobile && EAS_NO_VCS=1 eas build --platform android --profile preview)
}

build_ios() {
  if [ ! -d "src/frontend/mobile" ]; then
    warn "src/frontend/mobile not found; skipping iOS build."
    return 0
  fi
  if ! have_cmd eas; then
    warn "EAS CLI not available; cannot trigger iOS build."
    return 0
  fi
  log "Triggering iOS build via EAS (preview profile)..."
  (cd src/frontend/mobile && EAS_NO_VCS=1 eas build --platform ios --profile preview)
}

start_docker_stack() {
  if [ ! -f "docker-compose.yml" ]; then
    warn "docker-compose.yml not found; skipping Docker stack startup."
    return 0
  fi

  if have_cmd docker-compose; then
    log "Starting Docker stack with docker-compose up -d..."
    docker-compose up -d
  elif have_cmd docker; then
    log "Starting Docker stack with docker compose up -d..."
    docker compose up -d
  else
    warn "Docker not available; cannot start DB/backend containers."
  fi
}

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --backend-only     Install Python deps, run backend tests (no Docker, no frontend/mobile).
  --docker-only      Only start the Docker stack (Postgres + backend) via docker-compose.
  --mobile-only      Only install mobile deps and trigger Android/iOS builds (requires EAS).
  --all              Do everything: deps, tests, Docker stack, web build, mobile builds.
  -h, --help         Show this help.

If no option is provided, --all is assumed.
EOF
}

MODE="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-only) MODE="backend"; shift ;;
    --docker-only) MODE="docker"; shift ;;
    --mobile-only) MODE="mobile"; shift ;;
    --all) MODE="all"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) err "Unknown option: $1"; usage; exit 1 ;;
  esac
done

log "Running setup in mode: $MODE"

case "$MODE" in
  backend)
    check_or_install_docker
    install_python_deps
    run_backend_tests
    ;;
  docker)
    check_or_install_docker
    start_docker_stack
    ;;
  mobile)
    install_node_deps_mobile
    check_eas_cli
    build_android
    build_ios
    ;;
  all)
    check_or_install_docker
    install_python_deps
    install_node_deps_web
    install_node_deps_mobile
    run_backend_tests || true
    run_web_tests_and_build || true
    start_docker_stack
    check_eas_cli
    # Comment out one or both of these if you don't want to auto-trigger builds
    build_android || true
    build_ios || true
    ;;
esac

log "Setup script completed."
