# Gudsky Research Management Tool — Development Rules & Engineering Standards

## Branding

| | |
|---|---|
| **Software name** | Gudsky Research Management Tool (**GRMT**) *(the short form "GRMT" is used interchangeably in code comments, log lines, Studio/service names, and informal references — this is intentional, since GRMT Pvt. Ltd. was formed specifically to build and maintain this tool, so the company name and the product's short form are the same acronym by design, not a naming collision)* |
| **Research & development by** | Gudsky Research Foundation — [www.gudsky.org](https://www.gudsky.org) — Section 8 non-profit, AICTE-approved, DPIIT Startup India recognized, NGO Darpan: WB/2024/0474558 |
| **Product developed & maintained by** | GRMT Pvt. Ltd. |
| **Legal-structure note** | Gudsky Research Foundation (Section 8 non-profit) and GRMT Pvt. Ltd. (for-profit private limited company) are distinct legal entities. Attribution throughout this project should read as *"Research and development by Gudsky Research Foundation; product developed and maintained by GRMT Pvt. Ltd."* rather than implying they are the same entity — this keeps IP, liability, and funding lines clean if the two ever need to be treated separately (grant reporting, non-profit compliance, etc.). **[ASSUMPTION]** — confirm with GRF/GRMT's actual legal counsel/MoU before this attribution language goes on anything public-facing (site footer, published paper, investor materials); it is a reasonable default for internal engineering docs, not a substitute for a real IP/licensing agreement between the two entities. |
| **Brand assets** | `assets/branding/gudsky/` (§2.1) — logo, favicon, and color palette pulled from the official site. See that folder's own `README.md` for the exact file list expected. |

**Status:** Binding for all contributors on this project. **Companion to:** `GRMT_Final_Technical_Build_Document.docx` (product spec, architecture, schema, API, roadmap) — now rebranded to match this document. This file does not repeat that document — it defines *how we build*, not *what we build*. Where the two conflict, the master build document is the source of truth for product/architecture decisions; this file is the source of truth for process, tooling, security, and operational rules.

**Compute platform decision (updated):** the project standardizes on **Lightning AI** (Studios) for all GPU workloads, replacing the RunPod recommendation in the master document's §7.7. Rationale in §1 below.

---

## Table of contents

1. [Compute platform: Lightning AI](#1-compute-platform-lightning-ai)
2. [Repository & pipeline structure](#2-repository--pipeline-structure)
3. [Logging standard — `log.txt`](#3-logging-standard--logtxt)
4. [`setup.sh` — one-shot environment bootstrap](#4-setupsh--one-shot-environment-bootstrap)
5. [Testing standard — pytest, 100-test target](#5-testing-standard--pytest-100-test-target)
6. [Security & encryption requirements](#6-security--encryption-requirements)
7. [Admin panel requirements](#7-admin-panel-requirements)
8. [In-browser PDF viewer & reviewer annotation tools](#8-in-browser-pdf-viewer--reviewer-annotation-tools)
9. [Definition of done](#9-definition-of-done)
10. [Open assumptions](#10-open-assumptions)

---

## 1. Compute platform: Lightning AI

### 1.1 Why Lightning AI, and what tier

Lightning AI Studios are persistent, browser-accessible GPU workspaces that keep files and environment state across stop/start cycles — this matters for us because it avoids the "re-download 15GB of models every session" problem that plain Colab/Kaggle have. Confirmed current plan structure:

| Plan | Cost | Relevant limits |
|---|---|---|
| Free | $0 | 15 monthly Lightning credits, 1 active Studio (auto-restarts every 4 hrs), single-GPU Studios only, 100GB persistent storage, ~80 free GPU hours/month |
| Pro | ~$50/mo (annual) | 40 credits/month, 1 Studio runs 24/7, multi-GPU Studios, 2TB persistent storage, ~80% savings via preemptible instances |
| Teams | ~$119/user/mo (annual) | A100/H100/H200 access, multi-node, SSO, 99.9% uptime SLA |

**Rule:** develop on the **Free plan** through Phase 1–3 of the build (per the master roadmap §7). **Upgrade to Pro no later than the day GPU services need to stay up for integration testing without the 4-hour auto-restart interrupting work** — the free tier's 4-hour Studio restart is fine for iterative dev but not for a stable demo environment. Downgrade back to Free after the demo if the project pauses.

**GPU tier for this project:** an **L4** Studio is the target — confirmed adequate in the master doc for Binoculars + a Q4 7–8B LLM run sequentially (§3.6, §7.6 of the master doc). Do not provision A100/H100 for this workload; it's unnecessary cost.

### 1.2 Studio layout for this project

One Studio per logical service group, not one giant Studio running everything — this keeps GPU-bound and CPU-bound work independently restartable and keeps the free-tier single-active-Studio limit from becoming a bottleneck once we're on Pro (multi-GPU Studios):

- **`grmt-gpu-inference`** — Binoculars + Fast-DetectGPT service, Ollama (Qwen2.5-7B-Instruct). GPU Studio (L4).
- **`grmt-embeddings`** — BGE-M3 + FAISS service. CPU Studio by default; only attach a GPU here if corpus embedding throughput becomes a bottleneck.
- **`grmt-backend-dev`** — FastAPI backend + Postgres client for local iteration (CPU Studio). Production backend still targets Render/Railway per the master doc §2.6; this Studio is for development and for running the GPU-service integration tests against a live GPU Studio.

### 1.3 Exposing GPU services from a Studio

Use Lightning's **public port / API builder** pattern to expose each GPU service as a stable HTTP endpoint the backend can call, rather than tunneling or hardcoding a Studio's ephemeral internal address:

```python
# grmt-gpu-inference/serve_binoculars.py — served via LitServe, exposed on a public port
import litserve as ls
from binoculars import Binoculars

class BinocularsAPI(ls.LitAPI):
    def setup(self, device):
        self.model = Binoculars()

    def decode_request(self, request):
        return request["text"]

    def predict(self, text):
        return {"binoculars_score": self.model.predict(text)}

    def encode_response(self, output):
        return output

if __name__ == "__main__":
    server = ls.LitServer(BinocularsAPI(), accelerator="gpu")
    server.run(port=8002)
```

**Rule:** enable **auto-sleep** on every exposed Studio API — the Studio powers down when idle and wakes on the next request. This is the mechanism that keeps free/Pro-tier GPU-hour spend under control; do not disable it "to avoid cold starts" without a documented reason, since cold-start latency (a few seconds to a couple of minutes depending on model size) is an acceptable trade-off at prototype scale and is explicitly budgeted for in the orchestration timeout (master doc §2.3).

### 1.4 Cost & session management rules

- Record every Studio's GPU-hour usage in `log.txt` (§3) at the end of each work session — one line, timestamped, with the Studio name and approximate hours consumed, so credit burn is traceable without logging into the Lightning dashboard every time.
- Never leave a GPU Studio running unattended overnight without auto-sleep enabled.
- The admin panel (§7) surfaces current model-serving status; use it to confirm a Studio actually went to sleep after a work session, not just that you closed the tab.

---

## 2. Repository & pipeline structure

### 2.1 Repo layout

```
grmt/
├── backend/            # FastAPI app, Gate Rule Engine, orchestration
│   ├── app/
│   ├── tests/          # pytest suite lives here (§5)
│   └── alembic/        # DB migrations
├── frontend/            # Next.js app
├── ai-services/
│   ├── gpu-inference/   # Binoculars + Fast-DetectGPT + Ollama client, deployed to grmt-gpu-inference Studio
│   └── embeddings/      # BGE-M3 + FAISS service, deployed to grmt-embeddings Studio
├── corpus-builder/      # one-off scripts for §3.4 of the master doc — S2AG/arXiv/CORE pull + index build
├── assets/
│   └── branding/
│       └── gudsky/      # logo, favicon, color palette — see that folder's own README.md
├── setup.sh             # §4 — one-shot bootstrap
├── log.txt              # §3 — running dev/debug log (gitignored per-machine, see §3.1)
├── development_rule.md  # this file
└── docker-compose.dev.yml
```

### 2.1.1 Brand assets folder — `assets/branding/gudsky/`

This folder holds the visual identity pulled from the official site ([www.gudsky.org](https://www.gudsky.org)) and is consumed by three places in the product: the frontend favicon/header logo, the letterhead on any generated report/PDF export, and this repo's own documentation. Its `README.md` (create alongside this folder, contents below) tells whoever has file access exactly what to drop in:

```markdown
# Gudsky brand assets

Source: official Gudsky Research Foundation assets, www.gudsky.org — do not
substitute placeholder/unofficial artwork; request current files from GRF
if anything here is missing or looks outdated.

Expected files:
- logo-full-color.svg       — primary logo, full color, for light backgrounds
- logo-white.svg             — reversed/white logo, for dark backgrounds and footers
- logo-mark-only.svg         — icon/mark only, no wordmark — used as favicon source
- favicon.ico                 — generated from logo-mark-only.svg
- color-palette.md            — hex values for primary/secondary/accent colors, pulled
                                 from the official site's stylesheet, so the frontend
                                 theme (§ frontend-design tokens) matches gudsky.org
                                 rather than an approximated color
- letterhead-template.docx    — if GRF has an existing letterhead, for any generated
                                 PDF/Word exports (e.g. analytics reports, master doc
                                 §6.4.5) that should carry official branding

Do not commit low-resolution screenshots or watermarked social-media exports
as the working logo files — request vector/source files from GRF directly.
```

**[ASSUMPTION]** No official color palette or vector logo files were available to embed automatically as part of this update — the site's fetched content confirmed a logo exists at gudsky.org (`/assets/images/logos/GudskyLOGO.jpg`) but the folder above needs someone with direct file access (or a request to GRF) to actually populate it. Until then, the frontend should use a neutral placeholder theme rather than guessing at brand colors.



### 2.2 Branching & PR rules

- `main` is always deployable. Feature branches: `feat/<short-name>`, fixes: `fix/<short-name>`.
- **No PR merges without the pytest suite passing** (§5) — enforced by CI, not by discipline alone.
- Every PR description must include: what changed, which `check_type`(s) or endpoints it touches (per master doc §4/§5), and whether it adds new tests toward the 100-test target.

### 2.3 The bug-fixing acceleration pipeline

The specific ask here is a *small* pipeline that shortens the loop from "something broke" to "I know exactly why." Three pieces, all mandatory:

1. **Structured `log.txt` output** (§3) from every service — the single most important piece, because it means a bug report is "paste these 20 lines" instead of "it doesn't work."
2. **A request ID that threads through every layer.** Generate a UUID at the FastAPI request boundary, pass it into every downstream call (LanguageTool, GROBID, embeddings, Binoculars, Ollama), and log it at every step. This turns "the plagiarism check failed for some submission" into "grep `req-id 7e2a...` in `log.txt` and see the exact call chain."
3. **A `/admin/health` endpoint** (feeds the admin panel, §7) that pings every AI service and reports up/down + last-response-time in one call — so "is it my code or is a service down" is answered in one glance, not five separate `curl` commands.

---

## 3. Logging standard — `log.txt`

### 3.1 Location and format

Every service (backend, each AI service, frontend build/runtime errors) writes to a single append-only `log.txt` at its own service root during local/Studio development. **Rule: plain text, one event per line, copy-paste friendly — no multi-line stack-trace blocks without a clear `---BEGIN TRACE---` / `---END TRACE---` fence**, so a whole error can be selected and pasted cleanly.

Line format:

```
[YYYY-MM-DD HH:MM:SS UTC] [LEVEL] [service] [req-id] message
```

Example:

```
[2026-08-14 09:12:03 UTC] [INFO] [backend] [req-7e2a1c] submission created id=s_9f1 conference=c_44
[2026-08-14 09:12:04 UTC] [INFO] [backend] [req-7e2a1c] dispatching AI checks: grammar,citation,plagiarism,ai_text,table_figure
[2026-08-14 09:12:06 UTC] [INFO] [grmt-gpu-inference] [req-7e2a1c] binoculars predict start text_len=8213
[2026-08-14 09:12:09 UTC] [ERROR] [grmt-gpu-inference] [req-7e2a1c] CUDA out of memory
---BEGIN TRACE---
Traceback (most recent call last):
  File "serve_binoculars.py", line 41, in predict
    ...
torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.10 GiB
---END TRACE---
[2026-08-14 09:12:09 UTC] [WARN] [backend] [req-7e2a1c] ai_text check marked status=timed_out
```

### 3.2 What must be logged, at minimum

- Every AI check invocation: start, end, duration, `model_version` (per master doc `ai_reports.model_version`), and pass/fail/flag outcome.
- Every gate-decision evaluation: which rules fired, hard vs. soft, final decision.
- Every auth failure (`401`/`403`) — without logging credentials or tokens themselves.
- Every Lightning Studio wake/sleep event for the GPU services (§1.4).
- Every admin-panel action (§7.3), especially server-down/test-run/server-up transitions — these are exactly the events someone will need to reconstruct after the fact.

### 3.3 What must never be logged

Passwords, raw JWTs, full PDF content, full API keys (log a masked suffix like `sk-...ab12` if you must confirm which key was used). This is a security rule (§6), not just a hygiene one.

### 3.4 Rotation

Keep it simple for the prototype: rotate `log.txt` to `log.txt.1` when it exceeds 20MB, no more than 3 rotated files kept. A full log-aggregation stack (ELK, Datadog, etc.) is explicitly out of scope for the prototype — `log.txt` plus `grep`/`ripgrep` is the intended workflow given the project's timeline.

---

## 4. `setup.sh` — one-shot environment bootstrap

**Rule:** one script, run from a clean checkout, brings up every dependency needed for local development — system packages, Python/Node environments, Docker images (LanguageTool, GROBID), model downloads, database migrations, and a `.env` template. It must be **idempotent** (safe to re-run) and must **end by printing a clear PASS/FAIL summary**, appended to `log.txt`.

```bash
#!/usr/bin/env bash
# setup.sh — one-shot bootstrap for Gudsky Research Management Tool (GRMT)
# Usage: ./setup.sh [--skip-models] [--skip-docker]
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
command -v node >/dev/null || { log "FATAL: node not found"; exit 1; }
command -v docker >/dev/null || log "WARNING: docker not found — --skip-docker implied"
log "system checks OK: python=$(python3 --version), node=$(node --version)"

# 2. Backend Python environment
log "setting up backend venv..."
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install --upgrade pip --quiet
pip install -r backend/requirements.txt --break-system-packages --quiet
log "backend deps installed"

# 3. Frontend deps
log "installing frontend deps..."
(cd frontend && npm install --silent)
log "frontend deps installed"

# 4. Docker-based CPU services (LanguageTool, GROBID)
if [ "$SKIP_DOCKER" = false ]; then
  log "pulling and starting LanguageTool..."
  docker run -d --name languagetool -p 8010:8010 -e Java_Xmx=2g erikvl87/languagetool:latest || log "languagetool container already running"
  log "pulling and starting GROBID (CRF)..."
  docker run -d --name grobid --init --ulimit core=0 -p 8070:8070 --memory=4g grobid/grobid:0.9.0-crf || log "grobid container already running"
else
  log "skipping Docker services (--skip-docker)"
fi

# 5. AI model downloads (large — skip with --skip-models for a quick backend-only setup)
if [ "$SKIP_MODELS" = false ]; then
  log "installing embedding + FAISS deps..."
  pip install sentence-transformers faiss-cpu --break-system-packages --quiet
  python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')" \
    && log "BGE-M3 downloaded" || log "WARNING: BGE-M3 download failed"

  log "cloning + installing Binoculars..."
  [ -d Binoculars ] || git clone --quiet https://github.com/ahans30/Binoculars
  pip install -e Binoculars --break-system-packages --quiet
  log "Binoculars installed (models download on first predict() call — see grmt-gpu-inference Studio)"

  log "installing Ollama + pulling Qwen2.5-7B-Instruct (Q4_K_M)..."
  command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh
  ollama pull qwen2.5:7b-instruct-q4_K_M && log "Qwen2.5-7B-Instruct pulled" || log "WARNING: ollama pull failed"
else
  log "skipping model downloads (--skip-models)"
fi

# 6. Database
log "running Alembic migrations..."
(cd backend && alembic upgrade head) && log "migrations OK" || log "FATAL: migrations failed"

# 7. .env template
if [ ! -f .env ]; then
  cat > .env << 'EOF'
DATABASE_URL=postgresql://user:pass@localhost:5432/grmt
JWT_PRIVATE_KEY_PATH=./secrets/jwt_private.pem
JWT_PUBLIC_KEY_PATH=./secrets/jwt_public.pem
S2AG_API_KEY=
CORE_API_KEY=
GROQ_API_KEY=
LIGHTNING_GPU_INFERENCE_URL=
STORAGE_ENCRYPTION_KEY=
EOF
  log ".env template created — fill in secrets before running the app"
else
  log ".env already exists, not overwritten"
fi

# 8. Verification
log "running smoke checks..."
curl -sf http://localhost:8010/v2/languages >/dev/null && log "LanguageTool: OK" || log "LanguageTool: NOT REACHABLE"
curl -sf http://localhost:8070/api/isalive >/dev/null && log "GROBID: OK" || log "GROBID: NOT REACHABLE"

log "=== setup.sh finished: PASS ==="
echo ""
echo "Setup complete. Summary appended to $LOG — copy/paste it if reporting an issue."
```

**Rule:** any new dependency introduced by a feature branch (a new Python package, a new Docker image, a new model) must be added to `setup.sh` in the same PR that introduces the dependency — `setup.sh` drifting out of sync with `requirements.txt`/`package.json` is treated as a bug.

---

## 5. Testing standard — pytest, 100-test target

### 5.1 Why 100, and how it's allocated

100 is a floor, not a ceiling, and it's tied to the master roadmap's phases (master doc §7) so the count grows in step with features rather than being bolted on at the end:

| Area | Target test count | Roadmap phase it lands in |
|---|---|---|
| Auth (signup/login/JWT/RBAC) | 12 | Phase 1 |
| Database models/migrations | 8 | Phase 1 |
| Submission upload + versioning | 10 | Phase 2 |
| Grammar/citation check integration (mocked service calls) | 10 | Phase 2 |
| Plagiarism/similarity (embedding + MinHash, mocked corpus) | 10 | Phase 2–3 |
| AI-text detection + gate logic (hard/soft evaluation, incl. the `ai_content_pct`-cannot-be-hard-gate constraint) | 14 | Phase 3 |
| Reviewer assignment + review submission | 8 | Phase 4 |
| Organizer decision flow + notifications | 8 | Phase 4–5 |
| Cross-conference summary + fuzzy matching | 6 | Phase 5 |
| Admin panel endpoints (§7) | 8 | Ongoing |
| PDF viewer access-control + annotation API (§8) | 8 | Ongoing |
| Security (auth bypass attempts, encryption sanity checks, rate limiting) | 8 | Ongoing |
| **Total** | **110** | — |

**Rule:** every new feature PR includes at least one new test. If a PR touches an endpoint listed in the master doc §5 and adds zero tests, CI should still pass technically but the PR is not mergeable per team review policy — call this out explicitly in review, since CI cannot enforce "did you test the thing you built," only "do the tests that exist pass."

### 5.2 CI gate rules

- Every PR runs the full suite via GitHub Actions (or equivalent) before merge is allowed.
- GPU-dependent tests (Binoculars, Ollama) run against **mocked responses** in CI — CI does not have GPU access. Real-GPU integration tests run manually against the `grmt-gpu-inference` Studio and are tracked separately (a `tests/integration_gpu/` folder, run on demand, not on every CI push).
- Target: CI suite completes in under 3 minutes. If it creeps past that as the suite grows toward 100+ tests, parallelize with `pytest-xdist` rather than cutting tests.

### 5.3 Example test structure

```python
# backend/tests/test_gate_engine.py
import pytest
from app.gate_engine import evaluate_gate_rules

def test_ai_content_pct_cannot_be_hard_gate():
    """Master doc §4.3 / §5.2 constraint — must be enforced at the API layer."""
    with pytest.raises(ValueError, match="cannot be a hard gate"):
        evaluate_gate_rules(rules=[
            {"rule_type": "ai_content_pct", "is_hard_gate": True, "threshold_hard": 20}
        ], report={})

def test_hard_fail_blocks_before_soft_flags_considered():
    rules = [
        {"rule_type": "format_compliance", "is_hard_gate": True, "threshold_hard": 1},
        {"rule_type": "plagiarism_pct", "is_hard_gate": False, "threshold_soft": 5},
    ]
    report = {"format_compliance": {"pass_fail": False}, "plagiarism_pct": {"score": 3}}
    result = evaluate_gate_rules(rules, report)
    assert result["hard_fail"] is True
```

---

## 6. Security & encryption requirements

### 6.1 Transport

- **TLS 1.2+ everywhere**, no exceptions, including Studio-to-backend calls for the GPU services once past local dev (Lightning's public-port URLs are HTTPS by default — do not downgrade to plain HTTP even for "internal" calls).
- HSTS enabled on the frontend domain.

### 6.2 At rest

- **Uploaded PDFs and submission files: AES-256 encryption at rest.** If using Supabase Storage/Cloudflare R2's built-in server-side encryption, that satisfies this by default — confirm it's enabled, don't assume. If any custom storage path is used, encrypt with AES-256-GCM before write, key managed per §6.3.
- **Database:** enable encryption at rest at the provider level (Supabase/Neon both support this) — this is a checkbox to confirm, not custom code to write.
- **Reference corpus and FAISS index files:** same at-rest encryption standard, even though the corpus is built from public data — the index files are still part of the system's data footprint.

### 6.3 Auth & secrets

- **Password hashing: Argon2id** (preferred over bcrypt for new systems; bcrypt acceptable if the auth provider — Supabase/Firebase Auth — handles it natively and Argon2id isn't an option there).
- **JWT signing: RS256 (asymmetric), not HS256.** This lets the AI services and any future microservice verify tokens with only the public key, without holding a shared secret that would need to be distributed to every service.
- **Secrets never committed to the repo.** `.env` is gitignored; `setup.sh` only ever writes a *template* `.env` with empty values (§4). Real secrets live in the deployment platform's secret manager (Render/Railway env vars, Lightning Studio environment variables) — document this in the PR, don't paste real keys into Slack/chat either.
- **Key rotation:** JWT signing keys and the storage encryption key should be rotatable without a full redeploy — store the active key ID alongside the key material so rotation is a config change, not a migration.

### 6.4 PDF-specific security (ties directly into §8)

- PDFs are **never served as a direct downloadable file URL.** Every PDF view goes through a short-lived (≤5 minute), single-use signed URL generated per view request, streamed into the in-browser viewer (§8) — this is the mechanism that makes "no download" actually enforceable rather than just a UI restriction that a savvy user bypasses by finding the raw URL.
- Rate-limit PDF view-request generation per user to prevent bulk scripted extraction (e.g., max 30 view requests/hour per user — **[ASSUMPTION]**, tune based on real usage patterns).

### 6.5 Application-layer hardening

- Input validation on every endpoint (Pydantic models already do most of this in FastAPI — the rule is: no endpoint accepts a raw untyped dict).
- Rate limiting on auth endpoints specifically (`/auth/login`, `/auth/forgot-password`) to blunt credential-stuffing/brute-force attempts — a simple in-memory or Redis-backed limiter is sufficient at prototype scale.
- Standard security headers (CSP, X-Frame-Options, X-Content-Type-Options) on every frontend response.
- **Dependency scanning:** run `pip-audit` (backend) and `npm audit` (frontend) as part of CI, not just ad hoc — flag (don't necessarily block on) high-severity findings, given the 25-day timeline means an instant hard block on every transitive-dependency CVE would stall the build; use judgment, log the finding, and fix before demo day at the latest.
- The `audit_log` table specified in the master doc §4.3 (originally scoped as post-prototype) is **pulled forward into the prototype scope** given the admin panel's need to show who did what (§7.3's server-down/test-run actions specifically need an audit trail) — this is a schema-scope change from the master document, noted here rather than silently diverging from it.

---

## 7. Admin panel requirements

This is a new page not enumerated in the master document's §6 frontend spec — it's organizer/platform-admin-only (a new `platform_admin` role, distinct from `conference organizer`, since this panel spans all conferences and all models, not one conference's data — **[ASSUMPTION]**: the master doc's role matrix didn't anticipate a platform-wide admin role, since it was scoped per-conference; add `platform_admin` as a fourth role value in `users.role`).

### 7.1 Model usage & performance dashboard

**Purpose:** answer "how many models are in use, and how are they performing" at a glance.

**Components:**
- A card per AI service (LanguageTool, GROBID, embeddings, Binoculars, Fast-DetectGPT, Ollama LLM) showing: current status (up/down/sleeping — reading Lightning Studio state where applicable, §1.3), `model_version` currently active, request count (last 24h / 7d), average latency, error rate.
- A per-`check_type` performance table pulling from `ai_reports` (master doc §4.3): count of checks run, count flagged, count hard-failed, average score.

**New schema needed (additive to master doc §4):**

```sql
CREATE TABLE model_usage_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  service_name text NOT NULL,         -- 'languagetool' | 'grobid' | 'embeddings' | 'binoculars' | 'fastdetectgpt' | 'ollama_llm'
  model_version text NOT NULL,
  request_count integer NOT NULL DEFAULT 0,
  avg_latency_ms numeric,
  error_count integer NOT NULL DEFAULT 0,
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL
);
```
Populated by a periodic aggregation job (hourly rollup from `ai_reports` + service-level request logs) rather than computed live on every dashboard load, to keep the admin panel fast.

### 7.2 False-positive tracking

**This requires a feedback loop, since "false positive" can't be computed from the AI output alone — it needs a human-confirmed ground truth.** Design:

- When a reviewer or organizer reviews a flagged check (plagiarism or AI-text, per the master doc's soft-gate design, §1.7 of the master doc), give them an explicit **"Flag was correct" / "Flag was incorrect"** control alongside the existing review UI — this is a one-click addition to the Paper Review Detail page (master doc §6.5.2), not a new page.
- Store this as structured feedback:

```sql
CREATE TABLE flag_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ai_report_id uuid NOT NULL REFERENCES ai_reports(id) ON DELETE CASCADE,
  reviewer_id uuid NOT NULL REFERENCES users(id),
  was_correct boolean NOT NULL,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);
```
- Admin panel computes **false-positive rate = incorrect flags / total flags with feedback**, per `check_type`, per `model_version` — this last dimension matters: if you swap Binoculars' threshold or upgrade the embedding model, you want the false-positive trend to be attributable to the specific model version, not lumped together.
- **[ASSUMPTION]** Feedback coverage will be partial (not every flag gets a reviewer verdict) — the dashboard should show the feedback *sample size* next to the false-positive rate, not just the rate alone, so a 2-out-of-3 sample isn't presented with the same confidence as a 200-out-of-500 sample.

### 7.3 "Take server down → run 100 tests → bring server back up" workflow

This is a deliberately heavyweight, admin-gated action — treat it as a maintenance operation, not a casual button.

**Flow:**

1. Admin clicks **"Run Full Test Suite"** on the admin panel.
2. Confirmation modal: *"This will put the platform into maintenance mode, stop accepting new submissions, and run the full test suite (currently ~110 tests). Estimated downtime: X minutes. Continue?"*
3. On confirm: backend sets a `maintenance_mode` flag (a simple key in a `system_settings` table or a feature-flag service); all non-admin API calls return `503` with a clear maintenance message while this flag is set; the frontend shows a maintenance banner to any logged-in user.
4. Backend triggers the pytest suite as a subprocess, streaming results back to the admin panel in real time (Server-Sent Events or simple polling of a `test_run` status record — **[ASSUMPTION]**: SSE is the cleaner choice given tests can take a couple of minutes, but polling every 2–3 seconds is an acceptable fallback given the 25-day timeline).
5. Results shown live: pass/fail count, and on failure, the specific test names and a copy-pasteable error block (same `---BEGIN TRACE---` convention as `log.txt`, §3.1) rendered directly in the admin UI.
6. Admin reviews results, then clicks **"Bring Server Back Up"** — this clears `maintenance_mode`. **Rule: bringing the server back up is always a separate, explicit action, never automatic** — even if all 100+ tests pass, an admin should consciously decide to go live again, since a green test suite doesn't guarantee the specific bug that triggered the check was actually fixed correctly rather than just not-covered-by-a-test.
7. The full sequence (who triggered it, start/end time, pass/fail summary, who brought it back up) is written to `audit_log` (§6.5) and to `log.txt`.

**New schema needed:**

```sql
CREATE TABLE test_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  triggered_by uuid NOT NULL REFERENCES users(id),
  status text NOT NULL,          -- 'running' | 'passed' | 'failed'
  total_tests integer,
  passed_count integer,
  failed_count integer,
  failure_detail jsonb,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  server_restored_at timestamptz,
  restored_by uuid REFERENCES users(id)
);
```

**New endpoints (additive to master doc §5):**

| Method & Path | Purpose | Auth |
|---|---|---|
| `POST /admin/maintenance/start` | Enter maintenance mode | `platform_admin` |
| `POST /admin/test-run` | Trigger the pytest suite | `platform_admin` |
| `GET /admin/test-run/{id}/stream` | Live results (SSE or polled) | `platform_admin` |
| `POST /admin/maintenance/end` | Exit maintenance mode | `platform_admin` |
| `GET /admin/models/usage` | Model usage dashboard data (§7.1) | `platform_admin` |
| `GET /admin/models/false-positive-rate` | False-positive dashboard data (§7.2) | `platform_admin` |

---

## 8. In-browser PDF viewer & reviewer annotation tools

### 8.1 Core constraint: view-only, no download, no share

Papers are **never** downloadable or shareable through the product UI — this is a stricter rule than the master document's general privacy commitments (§1.12 of the master doc) and is specific to how PDFs are rendered:

- Render PDFs with **PDF.js** inside a custom viewer component embedded in the Paper Review Detail page (master doc §6.5.2) and, for researchers viewing their own submission, the relevant researcher-facing pages — served via the short-lived signed-URL streaming pattern from §6.4, never a direct file link.
- **Disable the browser's native PDF toolbar** (which normally offers print/download/save) — PDF.js supports this via viewer configuration; do not rely on hiding the toolbar with CSS alone, since that doesn't disable the underlying capability, only the button.
- Disable right-click context menu on the viewer surface, and block common save shortcuts (`Ctrl+S`/`Cmd+S`) from triggering a browser save dialog while focus is inside the viewer.
- **Watermark rendering:** overlay a faint, tiled watermark (viewer's name + timestamp) on the rendered PDF canvas — this doesn't stop a determined screenshot, but it deters casual redistribution and, more importantly, makes any leaked copy traceable to who viewed it and when.
- **[ASSUMPTION]** Text selection/copy is left enabled *within* the viewer, since reviewers need to be able to select text to anchor highlights and comments (§8.2) — fully disabling text selection would break the annotation feature. If stricter exfiltration resistance is needed later, revisit this trade-off; for the prototype, the signed-URL + no-toolbar + watermark combination is the intended bar, not text-selection blocking.

### 8.2 Reviewer annotation toolkit

Reviewers (not researchers, not organizers by default — **[ASSUMPTION]**: extend to organizers only if a specific need arises) get an annotation toolbar over the PDF viewer:

- **Five highlighter colors**, each mapped to a category so highlights are meaningful at a glance rather than arbitrary — recommended default mapping, tunable by the organizer:
  1. Yellow — general note-worthy passage
  2. Red — concern / potential issue
  3. Green — particularly strong point
  4. Blue — links to an AI pre-review flag (grammar/citation/plagiarism/AI-text) for cross-reference
  5. Purple — question for the author (visible to the researcher only if the organizer chooses to release it, consistent with the master doc's reviewer-comment-release rule, §1.2 item 9 / §5.5)
- **Sticky-note comments** anchored to a specific highlight or page location.
- **Strikethrough/underline** as lighter-weight markup options alongside highlighting.

**Annotations are stored as structured data, never burned into a modified copy of the PDF** — this is what keeps "no download" enforceable; there is never a downloadable annotated file to leak.

```sql
CREATE TABLE pdf_annotations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_version_id uuid NOT NULL REFERENCES submission_versions(id) ON DELETE CASCADE,
  reviewer_id uuid NOT NULL REFERENCES users(id),
  annotation_type text NOT NULL,   -- 'highlight' | 'comment' | 'strikethrough' | 'underline'
  color text,                       -- one of the five highlighter colors, nullable for non-highlight types
  page_number integer NOT NULL,
  position_data jsonb NOT NULL,     -- PDF.js text-layer coordinates/range needed to re-render the annotation
  comment_text text,
  visible_to_researcher boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

**New endpoints (additive to master doc §5):**

| Method & Path | Purpose | Auth |
|---|---|---|
| `GET /submissions/{id}/pdf-view-url` | Issue a short-lived signed streaming URL (§6.4) | Submitting researcher (own), assigned reviewer, organizer of that conference |
| `GET /submissions/{id}/annotations` | Fetch annotations for the current viewer | Reviewer (own), organizer, researcher (only where `visible_to_researcher = true`) |
| `POST /submissions/{id}/annotations` | Create an annotation | Reviewer only |
| `PATCH/DELETE /annotations/{id}` | Edit/remove own annotation | The authoring reviewer only |

### 8.3 What this explicitly does not do

No export of annotations to a shareable format, no "download my annotated copy," no organizer bulk-export of all annotations across a conference in the prototype scope — all of these are plausible future asks but are out of scope here specifically because any export path reopens the exfiltration risk this section exists to close. If a future requirement needs export, it should go through a deliberate, audited, rate-limited path — not be added as a quick convenience feature.

---

## 9. Definition of done

A feature is not done until:

- [ ] It's covered by at least one pytest test, counted toward the §5 target.
- [ ] It logs its key events per the §3 `log.txt` convention, including a request ID.
- [ ] Any new dependency it introduces is added to `setup.sh` (§4).
- [ ] Any new endpoint is added to the API surface table (master doc §5.11 or this file's additive tables) and has an explicit auth/role rule — no endpoint ships without a stated answer to "who can call this."
- [ ] Any new PDF-adjacent or model-serving feature is checked against §6 (encryption, signed URLs, no direct file exposure) before merge, not after.
- [ ] If it touches admin-visible metrics (§7), the admin panel reflects it — a feature whose data the admin panel can't see is effectively invisible to the people operating the platform.

## 10. Open assumptions

Everything tagged **[ASSUMPTION]** above, collected here for visibility:

1. §1.1 — Free-tier Lightning AI Studio through Phase 1–3, Pro tier from the point GPU services need to stay up reliably (exact day to be pinned to the master roadmap's Day 10–14 window once GPU integration actually starts).
2. §6.4 — PDF view-request rate limit of 30/hour/user is a starting default, not a validated number.
3. §7 — A new `platform_admin` role is introduced, distinct from the master doc's `organizer` role, since the admin panel spans all conferences.
4. §7.3 — SSE preferred for live test-run streaming; polling is an acceptable fallback given the timeline.
5. §8.1 — Text selection stays enabled inside the PDF viewer to support annotation; this is a deliberate trade-off against stricter copy-prevention, open to revisiting post-prototype.
6. §8.2 — Annotation permissions default to reviewers only; whether organizers also need annotation rights is unresolved and should be confirmed against real reviewer workflow feedback once the prototype is in use.
7. §6.5 — `audit_log` (originally post-prototype in the master doc) is pulled into prototype scope specifically to support §7.3's admin actions; this is a scope change from the master document, flagged here explicitly rather than silently diverging.
8. **Branding** — "Gudsky Research Management Tool" (GRMT) is taken as final per this update; the attribution split between Gudsky Research Foundation (R&D) and GRMT Pvt. Ltd. (product) is a reasonable default, not a substitute for an actual IP/licensing agreement between the two entities — confirm before it appears anywhere public-facing.
9. **Branding assets** — `assets/branding/gudsky/` is created with a README specifying expected files, but is currently empty; no official logo vector, favicon, or color palette was available to embed automatically. The frontend should use a neutral placeholder theme until real assets are supplied.
