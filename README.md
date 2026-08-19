# Gudsky Research Management Tool (GRMT)

**AI-powered conference & paper management system** — an AI pre-review layer between researchers and human reviewers, with organizer-configurable hard/soft gates.

| | |
|---|---|
| **Research & development by** | [Gudsky Research Foundation](https://www.gudsky.org) |
| **Product developed & maintained by** | GRMT Pvt. Ltd. |
| **License** | Proprietary — All Rights Reserved, GRMT Pvt. Ltd. *(**[ASSUMPTION]** — confirm before public release)* |

Full documentation: **`GRMT_Final_Technical_Build_Document.docx`** (product spec, architecture, DB schema, API spec, frontend specs, roadmap) and **`development_rule.md`** (engineering standards — Lightning AI, logging, testing, security, admin panel, PDF viewer). This README covers *running the actual code*.

## What's real in this codebase right now

This is a working starter implementation, not just scaffolding — everything below has been built and tested:

- **Backend (FastAPI)** — boots, all 21 database tables create correctly via a real Alembic migration, auth (signup/login/refresh) works end-to-end with Argon2id hashing + RS256 JWTs, and the Gate Rule Engine enforces the core product constraint (AI-content/plagiarism checks can never be a hard gate) at three layers: DB constraint, API validation (422 on violation), and evaluation-time defense-in-depth.
- **44 passing pytest tests** covering auth, the gate engine, conferences/gate-rules API, submissions, the admin panel, and security (password hashing, JWT algorithm, a static-analysis tripwire against ever logging a raw password).
- **`log.txt` logging** in the exact copy-paste format from `development_rule.md` §3, with request-ID threading.
- **Frontend (Next.js)** — landing, login, signup, and a role-aware dashboard shell all build and type-check cleanly (`npm run build` passes).
- **AI service skeletons** — embeddings (BGE-M3 + FAISS) and GPU inference (Binoculars + Fast-DetectGPT stub + Ollama LLM client) are real, runnable FastAPI services with lazy-loaded heavy dependencies, confirmed to boot and serve `/health` without the heavy ML libraries installed.
- **Docker Compose** for local Postgres + LanguageTool + GROBID, validated as well-formed.
- **`setup.sh`**, RSA key generation, and a demo-data seed script — all tested to actually run.

## What's still a placeholder / not yet built

Be direct with yourself about this before a demo:

- **AI orchestration is not wired up.** Submitting a paper creates a `processing` submission but does **not** yet dispatch calls to LanguageTool/GROBID/embeddings/Binoculars/Ollama — `backend/app/routers/submissions.py` has a docstring marking exactly where this goes. The AI services themselves work in isolation; the backend doesn't call them yet.
- **File storage is a placeholder.** Uploaded files are hashed but stored as a fake `placeholder://` URL, not actually uploaded anywhere. Wire real Supabase Storage/Cloudflare R2 + the signed-URL pattern from `development_rule.md` §6.4 before this handles real files.
- **Fast-DetectGPT is stubbed** in `ai-services/gpu-inference/serve_binoculars.py` (returns a fixed low score) — Binoculars itself is wired for real, Fast-DetectGPT needs its scoring model added.
- **Most frontend pages don't exist yet.** Only landing/login/signup/dashboard-shell are built. Every page in the master doc §6 (conference browse, submission upload, AI feedback report, gate config UI, reviewer review detail, admin panel UI, PDF viewer) still needs building — the dashboard shell's sidebar lists them as placeholders.
- **PDF viewer, annotations, and the admin panel's frontend** are unbuilt — the backend admin API (maintenance mode, test-run trigger, model usage) works and is tested; there's no UI for it yet.
- **Only 44 of the 100+ target tests exist** — a strong, real starting installment (see `development_rule.md` §5.1's phase-by-phase allocation for what's still needed).
- **Reviewer role has no self-serve signup** (by design, invite-only) but there's also no invite-flow UI or endpoint yet to actually invite one.

## Repository structure

```
grmt/
├── backend/                          # FastAPI — see backend/README below
│   ├── app/
│   │   ├── core/                     # config, database, security, gate_engine, logging, deps
│   │   ├── models/                   # SQLAlchemy models — every table in master doc §4
│   │   ├── schemas/                  # Pydantic request/response schemas
│   │   └── routers/                  # auth, conferences, submissions, admin
│   ├── alembic/                      # real migrations — `alembic upgrade head` to set up the DB
│   ├── scripts/                      # generate_keys.py, seed_demo_data.py
│   ├── tests/                        # 44 passing pytest tests
│   └── requirements.txt
├── frontend/                         # Next.js — landing, login, signup, dashboard shell
├── ai-services/
│   ├── embeddings/                   # BGE-M3 + FAISS service (own requirements.txt — heavy deps isolated)
│   └── gpu-inference/                # Binoculars + Fast-DetectGPT + Ollama client
├── corpus-builder/                   # S2AG bulk-search corpus puller
├── assets/branding/gudsky/           # brand asset folder — README lists what's expected, currently empty
├── docker-compose.yml                # local Postgres + LanguageTool + GROBID
├── setup.sh                          # one-shot bootstrap
├── GRMT_Final_Technical_Build_Document.docx
└── development_rule.md
```

## Getting started

```bash
git clone <repo-url> grmt   # or just unzip this delivery
cd grmt
./setup.sh
```

`setup.sh` creates the backend venv, installs dependencies, generates RS256 JWT keys, installs frontend dependencies (if `node` is available), starts Postgres/LanguageTool/GROBID via Docker Compose (if `docker` is available), runs the Alembic migration, and creates `backend/.env` from the example. It defaults to local SQLite if Docker isn't available, so it works with zero external services for a first look.

Then:

```bash
# Seed demo data (admin/organizer/researchers + a demo conference with valid gate rules)
cd backend && source .venv/bin/activate
python scripts/seed_demo_data.py

# Run the backend
uvicorn app.main:app --reload
# → http://localhost:8000/api/health

# Run the frontend (separate terminal)
cd frontend && npm run dev
# → http://localhost:3000
```

Demo login after seeding: `researcher1@grmt.demo` / `DemoResearcher123!` (see `scripts/seed_demo_data.py` for the full list, including the `platform_admin` account).

## Running the tests

```bash
cd backend && source .venv/bin/activate
pytest -v
```

Should show `44 passed`. Every new feature PR should add at least one test — see `development_rule.md` §5 for the phase-by-phase target breakdown toward 100+.

## AI services

These are separate from the backend's own dependencies on purpose (master doc §3, `development_rule.md` §1) — they carry heavy ML libraries (torch, sentence-transformers, faiss) that shouldn't bloat the main API process, and they're meant to run on a **Lightning AI Studio** with real GPU access, not necessarily on your dev machine.

```bash
cd ai-services/embeddings
pip install -r requirements.txt   # downloads BGE-M3, ~2.2GB on first run
python main.py                     # serves :8001

cd ai-services/gpu-inference
pip install -r requirements.txt
git clone https://github.com/ahans30/Binoculars && pip install -e Binoculars
python serve_binoculars.py         # serves :8002 — needs a real GPU, ~15-16GB VRAM
```

Point `backend/.env`'s `EMBEDDINGS_SERVICE_URL` / `GPU_INFERENCE_SERVICE_URL` at wherever these actually run.

## Database setup

Real Alembic migrations, not just `create_all()`:

```bash
cd backend
# Local SQLite (default, zero setup):
alembic upgrade head

# Postgres (after `docker compose up -d postgres`, or against Supabase/Neon):
DATABASE_URL="postgresql://grmt:grmt_dev_password@localhost:5432/grmt" alembic upgrade head
```

Creates all 21 tables from master doc §4 plus the admin/PDF-annotation additions from `development_rule.md` §7-§8. To add a new table or column: edit `backend/app/models/`, then `alembic revision --autogenerate -m "description"`, review the generated file, then `alembic upgrade head`.

## Security notes for anyone extending this

- JWT keys live in `backend/secrets/` (gitignored) — generate with `python scripts/generate_keys.py`. If they're missing, the app falls back to an ephemeral in-memory keypair with a loud warning — fine for a single test run, **not** fine for anything that needs to survive a restart.
- `STORAGE_ENCRYPTION_KEY` in `.env` is a placeholder — real file encryption isn't wired up yet (see "What's still a placeholder" above).
- The frontend's token storage (`localStorage`) is a documented, deliberate scope cut — see the comment at the top of `frontend/lib/api.ts` for the httpOnly-cookie alternative to implement before production.

Full security requirements: `development_rule.md` §6.
