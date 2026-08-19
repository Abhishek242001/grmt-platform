#!/usr/bin/env bash
# lightning_configure.sh — one-shot fixup for Lightning AI Studio public URLs.
#
# Every time you start a NEW Studio, its public port URLs change (the
# "01m0ddm7yyqc6b8109t15d88bc" part is per-Studio, not per-port). This
# script takes the ONE thing that actually changes — your Studio's public
# hostname suffix — and derives + writes every config file that needs it,
# then restarts both servers for you.
#
# Usage:
#   ./lightning_configure.sh <studio-suffix>
#
# <studio-suffix> is everything AFTER "3000-" and BEFORE ".cloudspaces..."
# in the URL your frontend gave you, e.g. if your frontend URL is:
#   https://3000-01m0ddm7yyqc6b8109t15d88bc.cloudspaces.litng.ai
# then run:
#   ./lightning_configure.sh 01m0ddm7yyqc6b8109t15d88bc
#
# Find this suffix from the Ports panel or the URL you already opened for
# port 3000 — that's the one manual step this script can't remove, since
# Lightning does not expose it as a predictable environment variable.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <studio-suffix>"
  echo "Example: $0 01m0ddm7yyqc6b8109t15d88bc"
  exit 1
fi

SUFFIX="$1"
DOMAIN="cloudspaces.litng.ai"
FRONTEND_URL="https://3000-${SUFFIX}.${DOMAIN}"
BACKEND_URL="https://8000-${SUFFIX}.${DOMAIN}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "Frontend public URL: $FRONTEND_URL"
echo "Backend  public URL: $BACKEND_URL"
echo ""

echo "NEXT_PUBLIC_API_BASE_URL=${BACKEND_URL}/api" > "$FRONTEND_DIR/.env.local"
echo "[OK] wrote $FRONTEND_DIR/.env.local"

if [ ! -f "$BACKEND_DIR/.env" ]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  echo "[OK] created $BACKEND_DIR/.env from .env.example"
fi

if grep -q "^CORS_ALLOW_ORIGINS=" "$BACKEND_DIR/.env"; then
  sed -i.bak "s|^CORS_ALLOW_ORIGINS=.*|CORS_ALLOW_ORIGINS=${FRONTEND_URL}|" "$BACKEND_DIR/.env"
  rm -f "$BACKEND_DIR/.env.bak"
else
  echo "CORS_ALLOW_ORIGINS=${FRONTEND_URL}" >> "$BACKEND_DIR/.env"
fi
echo "[OK] updated CORS_ALLOW_ORIGINS in $BACKEND_DIR/.env"

echo ""
echo "Stopping any existing servers on :8000 / :3000..."
pkill -f "uvicorn app.main:app" 2>/dev/null && echo "[OK] stopped old uvicorn" || echo "[..] no uvicorn was running"
pkill -f "next dev" 2>/dev/null && echo "[OK] stopped old next dev" || echo "[..] no next dev was running"
sleep 2

echo ""
echo "Starting backend..."
(cd "$BACKEND_DIR" && nohup uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > "$SCRIPT_DIR/backend.log" 2>&1 &)
sleep 3

echo "Starting frontend..."
(cd "$FRONTEND_DIR" && nohup npm run dev > "$SCRIPT_DIR/frontend.log" 2>&1 &)
sleep 3

echo ""
echo "=== Done ==="
echo "Backend log:  tail -f $SCRIPT_DIR/backend.log"
echo "Frontend log: tail -f $SCRIPT_DIR/frontend.log"
echo ""
echo "Open in your browser: $FRONTEND_URL"
echo "(hard-refresh with Ctrl+Shift+R to clear any cached JS)"
