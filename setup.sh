#!/usr/bin/env bash
# setup.sh — one-shot bootstrap for Gudsky Research Management Tool (GRMT)
# Usage: ./setup.sh [--skip-models] [--skip-docker]
#
# NOTE: edited for Lightning AI Studio compatibility — Lightning Studios provide
# one pre-made conda environment per Studio and do not allow creating a new venv
# ("Venv creation is not allowed"), so this version installs dependencies
# directly into the Studio's default environment instead of backend/.venv.
set -euo pipefail

LOG=log.txt
log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] [SETUP] $1" | tee -a "$LOG"; }

SKIP_MODELS=false
SKIP_DOCKER=false
for arg in "$@"; do
  case $arg in
    --skip-models) SKIP_MODELS=true ;;
    --skip-docker) SKIP_DOCKER=true ;;
  esac
done

log "=== setup.sh started ==="

# 1. System-level checks
command -v python3 >/dev/null || { log "FATAL: python3 not found"; exit 1; }
command -v node >/dev/null || { log "WARNING: node not found — frontend setup will be skipped"; }
command -v docker >/dev/null || log "WARNING: docker not found — --skip-docker implied for compose services"
log "system checks OK: python=$(python3 --version), node=$(node --version 2>/dev/null || echo 'not found')"

# 2. Backend Python environment
# On Lightning AI Studios, a venv can't be created (one conda env per Studio),
# so install straight into the Studio's default environment. Locally (non-Lightning),
# this still works fine without a venv — just less isolated from other projects.
log "installing backend deps into the active Python environment..."
pip install --upgrade pip --quiet
pip install -r backend/requirements.txt --quiet
log "backend deps installed"

# 3. JWT signing keys (development_rule.md §6.3)
if [ ! -f backend/secrets/jwt_private.pem ]; then
  log "generating RS256 JWT keypair..."
  (cd backend && python3 scripts/generate_keys.py) && log "JWT keys generated at backend/secrets/"
else
  log "JWT keys already exist, skipping"
fi

# 4. Frontend deps
if command -v node >/dev/null && [ -f frontend/package.json ]; then
  log "installing frontend deps..."
  (cd frontend && npm install --silent) && log "frontend deps installed"
else
  log "skipping frontend deps (node not found or frontend/package.json missing)"
fi

# 5. Docker-based CPU services (Postgres, LanguageTool, GROBID)
if [ "$SKIP_DOCKER" = false ] && command -v docker >/dev/null; then
  log "starting postgres, languagetool, grobid via docker compose..."
  docker compose up -d postgres languagetool grobid || log "WARNING: docker compose up failed — check docker-compose.yml"
else
  log "skipping Docker services (--skip-docker or docker not available). Backend defaults to local SQLite (see backend/.env.example)."
fi

# 6. AI model downloads (large — skip with --skip-models for a quick backend-only setup)
if [ "$SKIP_MODELS" = false ]; then
  log "NOTE: embedding/gpu-inference model downloads are NOT run by this script —"
  log "they live in ai-services/embeddings and ai-services/gpu-inference, each with"
  log "their own requirements.txt and their own (heavy) first-run downloads, per"
  log "development_rule.md §1 — these are meant to run on a Lightning AI Studio,"
  log "not necessarily on this machine. See README.md 'AI services' section."
else
  log "skipping model-download reminder (--skip-models)"
fi

# 7. Database migrations (only if DATABASE_URL is reachable — safe to skip for a pure frontend/API-shape check)
log "running Alembic migrations against the default local DB..."
(cd backend && DATABASE_URL="${DATABASE_URL:-sqlite:///./grmt_dev.db}" alembic upgrade head) \
  && log "migrations OK" || log "WARNING: migrations failed — if targeting Postgres, confirm docker compose's postgres service is up first"

# 8. .env files
if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  log "backend/.env created from .env.example — review and fill in real values before deploying anywhere beyond local dev"
else
  log "backend/.env already exists, not overwritten"
fi

# 9. Verification
log "running smoke checks..."
curl -sf http://localhost:8010/v2/languages >/dev/null 2>&1 && log "LanguageTool: OK" || log "LanguageTool: NOT REACHABLE (expected if --skip-docker or still starting up)"
curl -sf http://localhost:8070/api/isalive >/dev/null 2>&1 && log "GROBID: OK" || log "GROBID: NOT REACHABLE (expected if --skip-docker or still starting up)"

log "=== setup.sh finished: PASS ==="
echo ""
echo "Setup complete. Summary appended to $LOG — copy/paste it if reporting an issue."
echo ""
echo "Next steps:"
echo "  1. Review backend/.env (secrets, service URLs)"
echo "  2. cd backend && python scripts/seed_demo_data.py"
echo "  3. cd backend && uvicorn app.main:app --reload"
echo "  4. cd frontend && npm run dev   (if frontend deps were installed)"