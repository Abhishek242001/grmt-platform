# GRMT Platform — Project Handoff & Continuation Guide

**Read this first in any new chat.** This is a complete, current-as-of-now snapshot of the project — what's built, what's tested, what's broken, what's left, and exactly how to get the dev environment running again. It supersedes the older `GRMT_Planning_Log.md` (which stops partway through Phase 2 and is missing everything from the grammar-check chunking work onward).

---

## 1. Project Overview

**GRMT (Gudsky Research Management Tool)** — an AI-powered academic conference/paper management platform. Researchers submit papers, AI checks pre-review them for grammar/format/citation/plagiarism/etc., organizers configure gate rules (hard-reject vs soft-flag thresholds per check), reviewers give human judgment, and it never lets AI checks hard-gate on plagiarism or AI-text-detection (a locked-in non-negotiable product principle).

**Stack:** FastAPI (Python) backend · Next.js 16 (React 19) frontend · SQLite dev DB · Lightning AI Studio (T4 GPU) · GitHub repo `https://github.com/Abhishek242001/grmt-platform.git`, branch `dev`.

**Master spec document:** `GRF_Conference_System_Final_Technical_Build_Document.docx` (uploaded early in the original session) — this is the authoritative source for product requirements, though **some of its numeric values (IEEE margins) turned out to be wrong when checked against real IEEE templates — see §5.2 below.** Don't trust every number in it blindly; verify against real source documents when possible, the way we now do.

---

## 2. Current Overall Status

- **Phase 1 (Foundation, Auth, Backend, Frontend): COMPLETE.**
- **Phase 2 (AI Models): 3 of 8 checks built and tested.** 5 remain.

Backend test suite: **118/118 passing** as of the last verified state (105 from before + 13 new for table/figure consistency).

---

## 3. Phase 1 — What's Built (Complete)

### Backend (`~/grmt-platform/backend/`)
- Auth: signup/login, Argon2id password hashing, RS256 JWT (access + refresh)
- Conferences: full CRUD, gate rules, reviewer/co-admin management, submission queue
- Submissions: create, real file upload (multipart, `.docx`/`.pdf`), version history, resubmit (see gap in §6)
- Reviews & Decisions: reviewer submission, organizer decision-making, status transitions
- Analytics: submission counts, review/decision stats
- Files: HMAC-signed PDF view URLs, PDF annotations CRUD
- WebSocket layer: connection manager, ticket-based auth (WS can't carry Authorization headers), per-channel authorization, live push on submission create/resubmit/AI-check-complete

**Non-negotiable rules enforced in code (not just UI):**
- `gate_rules` DB CHECK constraint + Pydantic validator + evaluation-time downgrade: plagiarism/AI-text checks can never be `is_hard_gate=true` (3-layer defense)
- 404 (not 403) for all unauthorized resource access, to avoid leaking existence
- Ownership checks centralized in shared helper functions so sibling endpoints can't drift apart

### Frontend (`~/grmt-platform/frontend/`)
Next.js 16.3.1, React 19.0.0, zero known vulnerabilities.

- Landing page, login/signup, dashboard (role-aware)
- Researcher: Browse Conferences, Submission Detail (with real AI Feedback display), My Submissions
- Organizer: Create Conference, Gate Rule Configuration, Submission Queue, Reviewer/Co-Admin Management, Analytics
- Reviewer: Assigned Papers, review form (built early, **not re-verified with the same rigor as later work — worth a fresh look**)

### Key infrastructure fixes made along the way
- Next.js 14 → 16 upgrade (14 was past EOL with unpatched CVEs)
- `allowedDevOrigins` + `rewrites()` config for Lightning's proxy domain (both needed together — losing either one breaks things differently: dropping `allowedDevOrigins` blocks HMR/asset loading with 403s, dropping `rewrites()` breaks all `/api/*` calls with 404s)

---

## 4. Phase 2 — AI Models: Detailed Status

### 4.1 What's DONE (3 of 8 checks)

#### Grammar check (`backend/app/ai/grammar_check.py`) — DONE
Uses self-hosted **LanguageTool** (Docker container, `erikvl87/languagetool`, port 8010).

- **Full-document coverage** — chunks the document into <=15,000-char pieces (paragraph-boundary-aware splitting) and calls LanguageTool per chunk, so nothing is silently truncated. (Originally had a hard 20,000-char truncation bug — fixed.)
- **Page numbers** on every flagged issue (PDF only — tracked via a `page_map` built during PDF extraction, re-anchored correctly after text trimming)
- **Byline/References exclusion** — trims checked text to Abstract-to-References range, so author names and the citation list (hundreds of surnames/abbreviations) never get flagged as "typos." Uses a lookbehind-based regex (`(?:^|(?<=\n\n))ABSTRACT\b`, case-insensitive) that matches both a published article's ALL-CAPS standalone heading AND a real manuscript's title-case run-in heading (`"Abstract - text starts here"`) — these are genuinely different conventions and both needed to be detected.
- **Acronym false-positive filtering** — spelling-rule flags on tokens with 2+ internal capital letters (AIoT, IoT, PdM, etc.) are dropped, since that shape is essentially never a real typo
- **PDF text extraction is column-aware** (`backend/app/ai/pdf_text_extraction.py`) — buckets text blocks by left/right half of page, sorts top-to-bottom per column, then emits left column before right. Includes dehyphenation (`"com-\nputing"` -> `"computing"`) and line-wrap-to-space conversion, both needed to avoid spurious "malformed word" and "sentence doesn't start with uppercase" flags.
- Runs on both `.docx` and `.pdf` uploads

#### Format compliance check (`backend/app/ai/format_compliance_check.py`) — DONE
Pure local computation — **no external service**, no GPU, no API calls. Checks:
- Page size detection (Letter vs A4)
- Column count (**PDF only** — not yet measured for `.docx`, would need raw `<w:cols>` XML digging)
- Margins (top/bottom/left/right) — **page-size-aware**, see §5.2, exact from `.docx` metadata / approximate (bounding-box-inferred) for PDF
- Body font size — including **style-inherited** sizing (see §5.3), not just per-run
- Page limit (8 pages, IEEE's actual stated hard max — **PDF only**, `.docx` page count isn't knowable without rendering)
- Structure presence: Abstract, References, Roman-numeral section headings

#### Gate evaluation engine (`backend/app/core/gate_engine.py`) — DONE
Deterministic rule evaluation — NOT an AI model itself. Reads completed `AIReport` rows, compares against the conference's configured `GateRule` thresholds, decides `ai_review_hard_failed` vs `in_human_review`. **Deliberately never returns `ai_review_passed`** — with only 3 of 8 checks built, claiming "passed" would falsely imply the full pipeline ran clean.

`CHECK_EVALUATORS` registry design: adding a new check's gate-evaluation logic is a ~6-line addition (a new evaluator function + one registry line), not a rewrite. Proven — this is exactly what happened when format-compliance was added.

Both checks run together in one background task (`_run_ai_checks_and_store` in `backend/app/routers/submissions.py`), triggered on `POST /submissions/{id}/upload`.

#### Table/figure consistency check (`backend/app/ai/table_figure_check.py`) — DONE
Pure text analysis — **no external service, no GPU, no page-geometry needed** — so unlike format-compliance, this one runs on **both `.docx` and `.pdf`** via the same `extract_text()` dispatcher `grammar_check.py` already uses (PDF gets page numbers on issues via the same `page_map`; `.docx` doesn't, matching the existing nullable-`page` pattern from grammar matches).

- **Caption vs. in-text-reference distinction** — a caption is recognized by its punctuation ("Fig. 3.", "TABLE II.") immediately after the number, at the start of a line/paragraph; a broader pattern catches in-text mentions anywhere ("as shown in Fig. 3," / "Table II shows..."). A number only counts as "truly referenced" if its reference count exceeds its caption count (the caption line itself always also matches the broader pattern).
- **Two-way consistency**: flags a caption with no in-text reference, AND an in-text reference with no matching caption — checked independently for figures and tables.
- **Numbering gaps and duplicates** — sequential-numbering check across captioned figures/tables; duplicate caption numbers flagged separately.
- **Roman numeral support for tables** (IEEE convention: tables use Roman numerals, figures use Arabic) — `_numeral_to_int()` handles both, so a table numbered I/II/III and a figure numbered 1/2/3 are both checked correctly. Some non-IEEE templates use Arabic for tables too; the regex accepts either for tables, so this isn't a blocker.
- **Calibrated against a real published IEEE-style paper** (fetched via web search, not committed to the repo — copyright), not just synthetic fixtures, per §5.1's lesson. The real paper had exactly the kind of defect this check is meant to catch: a figure caption ("Fig1. Steps in document clustering") with no matching in-text reference anywhere in the body — confirmed the caption/reference regex distinction works correctly against real inconsistent-real-world formatting (mixed "Fig1." vs "Fig 2." spacing/punctuation within the same document), not just clean synthetic text.
- Zero tables/figures in a document is **not** treated as an error — `status: "complete"`, `score: null`, `checks_total: 0` (nothing to check, not a failure).
- Registered in `CHECK_EVALUATORS` as `"table_figure"` (already reserved in `CHECK_TYPES`/`app/models/conferences.py` — no migration needed) — same `score >= threshold` shape as grammar/format, ~6-line addition as promised.

**Deferred** (out of scope for this pass, would need more infrastructure): actually verifying a table's claimed column count or that a figure's referenced image data exists/isn't corrupt — that needs Camelot (table structure) or real image-object inspection, not just text matching. This check verifies referencing/numbering consistency, not content correctness.

### 4.2 What's NOT built (5 of 8 checks remain)

| Check | Model/Tool needed | Blocker |
|---|---|---|
| **Citation completeness** | GROBID | Needs GROBID Docker service stood up (not done), needs PDF input specifically |
| **Plagiarism/similarity** | BGE-M3 + FAISS | Needs a reference corpus of papers to compare against — doesn't exist yet, real prerequisite, not a shortcut-able gap |
| **AI-generated-text detection** | Binoculars + Fast-DetectGPT | Needs the GPU Studio; two ~7B models loaded — tight on the T4's 16GB VRAM budget, unverified whether both fit simultaneously |
| **Logical consistency** | Qwen2.5-7B-Instruct via Ollama | Needs Ollama + model download on the GPU Studio; single model so more tractable than AI-text detection, but still new GPU infra |

---

## 5. Critical Lessons Learned (read before touching AI checks again)

### 5.1 Always verify against real source documents, not just synthetic tests
Synthetic test files can be subtly unrealistic in ways that hide real bugs or manufacture fake ones:
- A 2-column synthetic PDF test failed to detect 2 columns because text was written **interleaved** (left-line, right-line, left-line...) instead of **all-of-column-1-then-all-of-column-2** — PyMuPDF's block-grouping merges interleaved same-line text into one block, which doesn't match how real 2-column documents are actually laid out.
- Margin measurement accuracy depends on how much the synthetic text actually fills the column width — short test lines read an inflated "margin" versus real justified prose, which naturally reaches the column edge.

**When something looks wrong, get the real document and read/parse it directly** before changing code. This caught several real bugs (see below) that synthetic tests alone would have missed, and also *prevented* changing code to "fix" things that were actually just unrealistic test construction.

### 5.2 IEEE does not have one universal format — it's page-size-dependent, and even that's a simplification
Two genuine official/semi-official IEEE templates were checked directly:
1. **`Full-Paper-template.docx`** (genuine official IEEE conference template) — **US Letter**, margins top=1.0in, bottom=1.125in, left/right=0.8125in (derived from the template's own stated print-area width). This was cross-verified by reading the template's own explanatory instructional text (e.g., "the bottom margin should be 1-1/8 inches (2.86 cm)").
2. **`IEEE-paper-format-template.docx`** — turned out to be a **third-party Scribbr recreation**, not IEEE-authored (confirmed by finding Scribbr's own website links directly to this exact filename). Targets **A4**, margins top=0.75in, bottom=1.0in, left/right=0.62in.

The master build doc's original §3.7 numbers (0.75/1.0/0.625in) matched neither cleanly — they were closest to the A4 numbers, suggesting a transcription mix-up in the original spec-writing pass. **Current code applies different margin specs depending on detected page size** (`IEEE_RULES["margins_in"]["letter"]` vs `["a4"]`) — this was itself a missing feature, not just wrong numbers, and matches an `[ASSUMPTION]` the master doc had flagged from the very start but which was never actually implemented that way until now.

**The A4 numbers are lower-confidence** (third-party source) than the Letter numbers (genuine IEEE template) — flagged as such directly in the code comments. Worth finding a genuine IEEE-authored A4 template to cross-verify if this matters later.

Real IEEE abstract convention (confirmed by both a real template AND Scribbr independently): **`"Abstract - text starts right here"`**, italicized, bold, run-in heading — NOT a standalone `"ABSTRACT"` all-caps line. That standalone-caps style is what a **published/typeset** article shows (compiler-added), not what a **manuscript submission** should look like.

### 5.3 Real .docx files often define font size via named paragraph styles, not per-run
Many real templates set font size on a style (e.g., a style literally named `"Abstract"` or `"Body Text Indent"`) that itself inherits from a base style (`"Normal"`), rather than setting `run.font.size` explicitly on every run. Checking only `run.font.size` — the original, naive implementation — misses this entirely; it's not a rare edge case, it's normal Word template construction. Fixed by walking the style inheritance chain (`style.base_style`) until a size is found.

### 5.4 Some real .docx files use a non-standard OOXML namespace and python-docx can't open them
Files generated by certain non-Word tools (confirmed against the real Scribbr-generated template above) use `http://purl.oclc.org/ooxml/...` instead of the canonical `http://schemas.openxmlformats.org/...` namespace. `python-docx`'s `Document()` constructor raises `KeyError` on these — a hard crash, not a quality issue. Fixed with `backend/app/ai/docx_utils.py`'s `open_docx()`, which tries the normal path first and only falls back to in-memory namespace normalization (regex substitution across every XML part in the zip) if that fails — no extra cost for the common case (genuine Word files).

### 5.5 Multi-section .docx documents: don't trust sections[0]
Real templates often have multiple `sectPr` sections (e.g., a title-page-specific section with different margins, followed by the main body's section). Reading `doc.sections[0]` can silently read the *wrong* section's margins. Fixed by using `doc.sections[-1]` (last section) — the same "page 1 is atypical" reasoning already applied to PDF page selection (which measures from page index 1, not 0, for the same reason).

### 5.6 Terminal / environment gotchas hit repeatedly this session
- **zsh history expansion (`!`) breaks inline `python3 -c "..."` strings** containing `!r` (e.g., `repr()`-style f-strings) or other `!`-prefixed content. Fix: write the script to a real `.py` file via heredoc (`cat > script.py << 'EOF' ... EOF`) and run that, instead of inlining complex Python via `-c`.
- **Running a script from `/tmp` breaks `from app...` imports** — Python puts the *script's own directory* on `sys.path[0]`, not the current working directory. Always place diagnostic scripts inside `backend/` itself (or explicitly set `PYTHONPATH`), not `/tmp`.
- **`node_modules` gets wiped on Lightning Studio instance restarts/idle cycles** — always run `npm install` after any restart before `npm run dev`, don't assume it survived.
- **`npm`/`node` occasionally report "command not found" via `nohup` right after a fresh shell session**, even though they work fine when invoked directly moments later — likely a PATH-initialization timing quirk on fresh shells. If `nohup npm run dev` fails this way, just retry the same commands — it resolved on retry every time this happened.
- **The LanguageTool Docker container does not survive Studio restarts** — always check `docker ps -a | grep languagetool` and `docker start languagetool` (or re-`docker run` if the container's gone entirely) after any restart, *before* testing grammar checks. A "LanguageTool request failed for all chunks" error usually means this.
- **Extracting an `update*.zip` from inside the target directory double-nests the path.** The zip's internal paths are relative to the repo root (e.g., `backend/app/...`), so always `cd ~/grmt-platform` (repo root) before extracting — never `cd` into `backend/` or `frontend/` first.

---

## 6. Known, Documented Gaps (not silently dropped — explicitly flagged as follow-ups)

- **`POST /submissions/{id}/resubmit` doesn't accept real file uploads yet** — still takes JSON metadata + a placeholder URL, the same shape `/submissions` originally had before real upload support was added. Needs the same real-multipart-upload treatment `/upload` got. Until fixed, resubmission doesn't actually re-run AI checks (status correctly stays `"submitted"`, not `"processing"`, to avoid the stuck-forever bug this would otherwise cause).
- **Word-to-PDF conversion pipeline doesn't exist.** Needed for: reviewers' PDF viewer, and GROBID (which needs PDF input) for the citation-completeness check. Standard approach flagged in the master doc: LibreOffice headless (`soffice --headless --convert-to pdf`), not `docx2pdf` (Windows/COM-only, not viable server-side).
- **WebSocket live-push isn't wired into the AI-report UI** — the submission detail page still polls every 4 seconds. The WS channel and event (`ai_report.check_completed`) already exist and are tested; this is a frontend wiring task, not new backend work.
- **`.docx` column count isn't measured** — returns `None`, documented limitation, would need raw `<w:cols>` XML digging (not yet attempted).
- **`.docx` page count isn't knowable without rendering** — same reason page-limit check is PDF-only.
- **Reviewer-facing frontend pages were built early and haven't been re-verified** with the same real-build/real-test rigor later work received.

---

## 7. How to Continue — Environment Setup From Scratch

This assumes a Lightning AI Studio instance (same one, or a fresh one — commands work either way; skip steps that are already satisfied).

### 7.1 Get the code
```bash
cd ~
git clone https://github.com/Abhishek242001/grmt-platform.git
cd grmt-platform
git checkout dev
git pull
```
(If continuing on the *same* Studio where `~/grmt-platform` already exists, just `git pull` instead.)

### 7.2 Backend
```bash
cd ~/grmt-platform/backend
pip install -r requirements.txt --break-system-packages --quiet
ls secrets/jwt_private.pem || python3 app/scripts/generate_keys.py
```

### 7.3 LanguageTool (grammar check dependency)
```bash
docker start languagetool 2>/dev/null || docker run -d -p 8010:8010 --name languagetool erikvl87/languagetool
sleep 15
curl -s http://localhost:8010/v2/check -d "text=test&language=en-US" | head -c 100
```

### 7.4 Start backend
```bash
cd ~/grmt-platform/backend
nohup uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > ~/grmt-platform/backend.log 2>&1 &
sleep 3
curl -s http://localhost:8000/api/health
```

### 7.5 Frontend
```bash
cd ~/grmt-platform/frontend
npm install
nohup npm run dev > ~/grmt-platform/frontend.log 2>&1 &
sleep 8
tail -20 ~/grmt-platform/frontend.log
```
(If `npm run dev` fails with "command not found" via `nohup`, just retry the exact same block — see §5.6.)

### 7.6 Get your public test URL
```bash
env | grep -i litng
```
URL is `https://3000-<that-suffix>.cloudspaces.litng.ai`

### 7.7 Run the test suite to confirm everything's healthy
```bash
cd ~/grmt-platform/backend
python3 -m pytest -v 2>&1 | tail -20
```
Should show **105 passed**.

---

## 8. How Future Code Changes Get Deployed (the updateN.zip workflow)

This is the pattern used throughout Phase 2 — worth continuing, since it verifies every change (real build/test) *before* it ever reaches the Studio, rather than trusting terminal-paste transcription.

1. Claude builds and verifies changes in its own sandbox (`python3 -m pytest`, `npm run build`) — never ships unverified code
2. Claude packages only the new/changed files into a zip (e.g., `update14.zip`)
3. You run, from the **repo root** (`~/grmt-platform`, not a subdirectory):
   ```bash
   cd ~/grmt-platform
   python3 -c "
   import zipfile
   with zipfile.ZipFile('update14.zip') as zf:
       zf.extractall('.')
       print('extracted:', len(zf.namelist()), 'files')
   "
   rm update14.zip
   ```
4. Run tests to confirm: `cd backend && python3 -m pytest -v 2>&1 | tail -20`
5. Restart whichever server(s) changed (backend usually auto-reloads via `--reload`; frontend needs a manual restart — `pkill -f "next dev"`, `rm -rf .next`, `nohup npm run dev ...`)
6. Test in the browser
7. **Periodically commit and push to `dev`** so the repo stays in sync with the Studio's actual state:
   ```bash
   cd ~/grmt-platform
   git add -A
   git commit -m "Description of what changed"
   git push origin dev
   ```

---

## 9. Suggested Next Steps (pick up from here)

In rough order of "easiest to build next" given current infrastructure:

1. ~~**Table/figure consistency check**~~ — **DONE**, see §4.1.
2. **Word-to-PDF conversion pipeline** (LibreOffice headless) — unlocks both the reviewer PDF viewer and GROBID-dependent citation checking.
3. **Wire WebSocket live-push into the AI-report UI** — replaces polling with the already-built, already-tested real-time channel. Frontend-only work.
4. **Fix `/resubmit` to accept real file uploads** — closes the gap flagged in §6, makes resubmission actually re-trigger AI checks.
5. **GROBID setup + citation-completeness check** — bigger lift (new Docker service, TEI-XML parsing), best done after the PDF pipeline above exists.
6. **Reference corpus + plagiarism check** — real prerequisite work before this check can even start.
7. **Ollama + Qwen2.5-7B + logical-consistency check** — first LLM-based check, moderate GPU setup.
8. **Binoculars + Fast-DetectGPT + AI-text detection** — biggest GPU risk (two large models, tight VRAM budget), do last or verify VRAM feasibility early.

---

## 10. Reference: Full File Inventory (Phase 2 AI code)

```
backend/app/ai/
├── grammar_check.py           # LanguageTool integration, chunking, byline/refs trimming, acronym filter
├── pdf_text_extraction.py     # Column-aware PDF text extraction, dehyphenation, page_map tracking
├── format_compliance_check.py # IEEE margin/font/structure checks, page-size-aware
├── table_figure_check.py      # Caption<->reference consistency, numbering gaps/duplicates (.docx + .pdf)
└── docx_utils.py              # Shared open_docx() with legacy-namespace compatibility fallback

backend/app/core/
└── gate_engine.py             # CHECK_EVALUATORS registry (grammar, format, table_figure), evaluate_submission_gates()

backend/app/routers/
└── submissions.py             # _run_ai_checks_and_store() background task, upload endpoint

backend/tests/
├── test_grammar_check.py
├── test_pdf_text_extraction.py
├── test_format_compliance_check.py
├── test_table_figure_check.py
├── test_docx_utils.py
├── test_gate_engine.py
└── test_submissions.py        # includes integration tests for all three checks running together

frontend/app/submissions/[id]/page.tsx  # GrammarReportCard + FormatReportCard + TableFigureReportCard display components
frontend/lib/api.ts                     # GrammarCheckResult, FormatCheckResult, TableFigureCheckResult TypeScript types
```
