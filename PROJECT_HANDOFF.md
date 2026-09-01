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
- **Phase 2 (AI Models): 6 of 7 checks built and wired into the live pipeline.** Only plagiarism remains — blocked on a real prerequisite (no reference corpus exists yet), not a coding gap. (Note: earlier revisions of this doc said "8 checks" — stale carryover from an early planning draft; `CHECK_TYPES` in `app/models/conferences.py` is the authoritative source and only ever defined 7.)
- **WebSocket live-push and the real `/resubmit` file upload fix are also DONE** — both were paused mid-project to focus on AI checks, then finished. Nothing from the original roadmap is still paused. See §9 for what's actually left.

Backend test suite: **261/261 passing** as of the last verified state. Frontend has a genuine working reviewer PDF viewer with annotations (§4.1), a genuine working AI-generated-content detection card with highlighted flagged paragraphs (§4.3), and citation/logical-consistency report cards (§4.4/§4.5) — all verified with real headless-browser runs against a real running instance, not just build checks.

**⚠️ The AI-generated-text detection check (§4.3) has a long, important saga — READ IT BEFORE TOUCHING THIS CHECK AGAIN.** Four different approaches were tried. Three failed with real, replicated negative results (not bugs — the actual detection signal wasn't there). The fourth (a pretrained academic-domain classifier, `followsci/bert-ai-text-detector`) is what's actually wired in now, and it is NOT highly accurate — it's a reasonable-effort starting point with known real weaknesses (misses adversarially-styled or closely-paraphrased AI text). §4.3 has the full decision record, every real number from every real test, and what a proper fix (fine-tuning on real academic-domain datasets) would need. Don't re-attempt Binoculars or Fast-DetectGPT at small model scale — that's already been tried twice and failed consistently.

**⚠️ Citation completeness (§4.4) and logical consistency (§4.5) are built and unit-tested, but GROBID and Ollama were never actually run** — no access to either service in the environment they were built in. Both need a real verification pass on an actual Studio (§7.3b/§7.3c) before being fully trusted, the same "written but unverified" category every GPU/external-service check this session started in.

**§9 is the section to read if resuming this project — it has the real, current "what's left" list, not the stale one that used to be here.**

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

### 4.1 What's DONE (6 of 7 checks — grammar, format, table_figure below; ai_text/citation/logical_consistency have their own §4.3/§4.4/§4.5 given their complexity)

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
Deterministic rule evaluation — NOT an AI model itself. Reads completed `AIReport` rows, compares against the conference's configured `GateRule` thresholds, decides `ai_review_hard_failed` vs `in_human_review`. **Deliberately never returns `ai_review_passed`** — with only 3 of 7 checks built, claiming "passed" would falsely imply the full pipeline ran clean.

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

**Real-document validation, round 2** (Aug 2026): tested against an actual real submission using the genuine (unfilled) Scribbr IEEE template. Two rounds of investigation followed:
1. First pass surfaced a genuine bug — see §5.7 (text-box content invisible to `doc.paragraphs` entirely) — fixed in `docx_utils.py`, benefits every check that reads `.docx` text, not just this one.
2. After that fix, the SAME file still flagged "Figure 1 referenced but no caption found." Full XML inspection (no `numPr`, no field codes, no text-box wrapper on the caption paragraph) confirmed this is NOT a bug: the raw template's "figure caption"-styled paragraph literally contains placeholder prose ("This is a figure caption. It appears directly underneath the figure.") — it never writes `"Fig. 1."` as text anywhere, while the body prose genuinely does reference "Fig. 1" by name. Validated by filling in the same real template with realistic content (preserving all original styles) — scored 100/0 issues — then deliberately breaking it, which the check correctly caught. **Conclusion: the check is accurate; an unfilled template genuinely has this defect**, and the template's own last line literally warns authors to remove placeholder text before submitting.

#### Word-to-PDF conversion pipeline (`backend/app/core/word_to_pdf.py`) — DONE
LibreOffice headless (`soffice --headless --convert-to pdf`), not `docx2pdf` (Windows/COM-only, not viable server-side) — matches the approach the master build doc already flagged. Not an AI check; deterministic, external-process-based infrastructure, same category as the gate-evaluation engine above.

- Populates `SubmissionVersion.converted_pdf_url` — a schema field that already existed from Phase 1 (built for the reviewer's PDF annotation viewer, `PDFAnnotation` model) but was never populated until now. No migration needed.
- Wired into the same background task as the AI checks (`_convert_to_pdf_and_store`, called from `_run_ai_checks_and_store`), but as its own step with its own error handling — a conversion failure never blocks grammar/format/table_figure checks, which don't depend on the PDF at all.
- An already-`.pdf` upload needs no conversion — `converted_pdf_url` is just set to the original file path directly, so the frontend never has to branch on original file type to find a PDF to display.
- **Concurrency safety, confirmed empirically, not assumed**: LibreOffice headless instances sharing a user-profile directory can clash when invoked concurrently — real, documented upstream behavior. Each call here gets its own throwaway profile (`-env:UserInstallation=file://...`, a fresh `tempfile.TemporaryDirectory()` per call), removed after. Tested with 3 real concurrent conversions via `ThreadPoolExecutor` — confirmed each output matched only its own input, no cross-contamination.
- **Real, confirmed limitation, not a guess**: `soffice --convert-to` does NOT reject malformed/non-`.docx` input with an error — it falls back to interpreting the raw bytes as plain text and produces a PDF containing that text verbatim (exit code 0, no stderr). Confirmed by feeding it a genuinely corrupt file and inspecting the output PDF's actual text content. This means the conversion step is **not** a validity check for the uploaded file — that's still `docx_utils.open_docx()`'s job (used by the AI checks), which DOES raise loudly on a genuinely corrupt `.docx`.
- Publishes a `submission_version.pdf_converted` WebSocket event (`{submission_id, version_id, converted, error}`) on the existing conference queue channel — not yet wired into any frontend UI (see gaps below).
- Real conversion tested throughout (not mocked) — `soffice` is genuinely installed and testable; ~2s per conversion in practice.

**Deferred / explicitly out of scope for this pass**: none — the reviewer PDF viewer/annotation UI is now DONE too. See new subsection below.

#### Reviewer PDF viewer & annotations (`frontend/components/PdfAnnotationViewer.tsx`) — DONE
Building this surfaced a real backend gap that had nothing to do with the frontend: `generate_signed_url()` signed a raw filesystem path and nothing ever actually served the bytes back — `verify_signed_url()` was defined but never called anywhere, no `FileResponse`/`StaticFiles` route existed. The existing test only checked the returned string *contained* `"signature="`, never that it was fetchable. Confirmed by tracing the code, not assumed. Fixed as part of this work, not treated as separate:

- `GET /submissions/versions/{id}/pdf-url` now signs `version_id` itself (not a raw filesystem path — avoids leaking the container's layout to the client) and returns a URL pointing at a genuinely new endpoint.
- `GET /submissions/versions/{id}/pdf-stream?expires=...&signature=...` — the endpoint that actually streams the PDF. Deliberately has **no** `get_current_user` dependency: a browser's native PDF viewer embed can't attach an `Authorization` header, so the signature itself (HMAC-verified, expiry-checked) is the auth — matches `file_signing.py`'s own documented security model. Auth for *who can obtain* a signature already happens at `pdf-url`.
- Returns 404 (not a mislabeled wrong file) when no real PDF exists yet — checks the resolved path is non-null, ends in `.pdf`, and actually exists on disk, rather than trusting `converted_pdf_url or original_file_url` blindly (a `.docx` original with a failed/pending conversion would otherwise get served back mislabeled as `application/pdf`).
- 4 new tests, all against real behavior: genuinely fetchable + serves real bytes (fetched **without** an Authorization header, matching how a browser PDF embed actually works), tampered signature rejected, expired signature rejected, missing-PDF case 404s cleanly.

Frontend (`react-pdf`, wraps pdf.js): page navigation, click-to-annotate (reviewers only — gated on `user.role === 'reviewer'`), annotation pins positioned as **percentage of rendered page width/height** (not raw pixels — a deliberate choice for scale-independence, since `position_json`'s format wasn't otherwise pinned down anywhere in the existing schema/tests). Pin click opens the comment; delete is restricted to the annotation's own author, matching the backend's existing `reviewer_id != user.id -> 404` rule.

**Verified with a real, actually-running instance of the app, not just a build check**: started the real backend + frontend dev servers in-sandbox, ran a genuine `.docx` through the real upload → LibreOffice conversion → streaming pipeline, then drove an actual headless browser (Playwright) through the real login flow to:
- Confirm the PDF canvas has real non-blank rendered pixel content (checked via `getImageData`, not just "a canvas element exists" — a canvas can exist and render nothing)
- Click on the rendered page, type a comment, save it, and confirm the pin appears at the right position
- **Reload the page and confirm the annotation persisted** (not just held in React state)
- Log in as a *different* user (the paper's own researcher, not the annotation's reviewer-author) and confirm: the pin and comment are visible, the "click to annotate" affordance is correctly hidden (not a reviewer), and the Delete button is correctly hidden (not the annotation's author)
- Confirmed the only console errors present were pre-existing and unrelated (`/images/logo.jpg` missing asset, `/decision` 404 for a submission with no decision yet — both predate this work)

### 4.2 What's NOT built (1 of 7 checks remains)

| Check | Model/Tool needed | Blocker |
|---|---|---|
| **Plagiarism/similarity** | BGE-M3 + FAISS | Needs a reference corpus of papers to compare against — doesn't exist yet, real prerequisite, not a shortcut-able gap |

### 4.3 AI-generated-text detection — DONE, but read the full saga before touching this again

**Status: wired into the live pipeline and working, but with real, known accuracy limitations.** This took four full attempts across one long session. Three failed with genuine, replicated negative results — not bugs, not bad luck, real evidence the underlying approach doesn't work at the scale/setup available. Documented in full because the failures are exactly as informative as the eventual success, and re-attempting an already-rejected approach would waste real time.

#### Attempt 1: Binoculars, Falcon-7B pair (the original plan) — rejected before writing any code

Falcon-7B alone needs ~15GB in FP16; Binoculars needs **two** loaded simultaneously (~30GB combined) — roughly double the T4's 16GB budget. A published benchmark needed an L40S (48GB) just to run Binoculars and Fast-DetectGPT together, confirming this wasn't an overly cautious read of the constraint.

#### Attempt 2: Binoculars, Qwen2.5-0.5B pair — built, tested on real T4, FAILED

Swapped to a much smaller same-family base/instruct pair (`Qwen/Qwen2.5-0.5B` + `Qwen/Qwen2.5-0.5B-Instruct` — chosen over Phi-1.5 because Qwen has an *official* matched instruct release, unlike Phi-1.5's community-only instruct fine-tune). Real calibration on real T4:
- Single pair: human sample scored `1.1111` (likely_human, correct), AI sample scored `1.2090` (likely_human, **wrong** — and *higher*, the wrong direction, not just wrong side of a threshold)
- 4-per-class calibration set: human mean ≈1.154, AI mean ≈1.232 — **AI scored higher than human on average**, fully interleaved when sorted, no separation at all
- Ruled out sample length as the cause (retested with ~230-word passages, same backward result)
- **Root cause (found via real research, not guessed)**: zero-shot detection relies on the proxy model being well-aligned with whatever model generated the text. A 0.5B Qwen proxy has no reason to find Claude's (the AI actually writing the test samples) writing patterns statistically unusual — the observer/generator mismatch collapses the signal the method needs.

#### Attempt 3: Fast-DetectGPT, single Qwen2.5-3B model — built, tested on real T4, FAILED

Different method (conditional probability curvature, not perplexity-ratio), one larger model instead of two smaller ones (freed VRAM from not needing a pair). Same 8 calibration samples for direct comparison: human curvature mean ≈0.333, AI mean ≈0.007 — again **backward**, again fully interleaved (`-0.71(H), -0.30(AI), -0.07(H), -0.01(AI), 0.04(AI), 0.30(AI), 0.30(H), 1.81(H)`). Confirms the problem wasn't specific to Binoculars or to the 0.5B scale — it's proxy-model/generator mismatch and domain unfamiliarity, a documented, real limitation of zero-shot detection methods generally (current research explicitly frames this as an arms race: "detectors are increasingly precise, while LLMs keep improving alignment with human styles, rendering detectors potentially obsolete tomorrow").

**Both pure-math scoring formulas (Binoculars' perplexity/cross-perplexity ratio, Fast-DetectGPT's curvature statistic) are independently verified correct** — 27 hand-calculated unit tests between them (`binoculars_scoring.py`, `fast_detect_gpt_scoring.py`) — so the negative results are real findings about the detection approach, not implementation bugs. These two modules and their model-inference counterparts (`ai_text_detection_check.py`, `fast_detect_gpt_check.py`) are still in the codebase, unused, kept for the historical record and in case future research changes the calculus (e.g. much larger GPU access).

#### Attempt 4: RADAR (TrustSafeAI/RADAR-Vicuna-7B) — a trained classifier, not zero-shot — built, tested, real signal but real bias

Different category of approach entirely: a *trained* adversarial classifier (despite the name, actually a RoBERTa-large model, ~355M params — "Vicuna-7B" refers to what it was trained against, not its own size). Real calibration: caught all 4 AI samples confidently (0.95-0.999), but flagged 3 of 4 human samples as AI too — specifically the **formal, structured** ones, not randomly. This is a real, serious, documented failure mode for our use case (academic writing is inherently formal), not just imprecision — deploying this would systematically false-accuse real researchers, especially non-native English speakers (a well-documented bias pattern for detectors trained on general web text, later independently confirmed while researching ZeroGPT — see below). Non-commercial license was also a real constraint (inherited from Vicuna-7B-v1.1).

#### ZeroGPT — researched, explicitly rejected, never built

User asked about this commercial tool directly. Real findings from independent sources (not vendor marketing): self-reported ~98% accuracy, independent benchmarks show 67-85%; false-positive rate 15-26%, with **independently confirmed higher false-positive rates specifically on "academic writing, formal business writing, and content from non-native English speakers"** — the same bias pattern RADAR showed, now confirmed by a second, independent source. Also: no published technical documentation, no independent academic benchmark participation (opaque "DeepAnalyse™" black box), sends full paper text to a third-party server (real confidentiality concern for peer review), and degrades on newer models. **Naming trap worth remembering**: GPTZero (different company) is a meaningfully stronger product if an external API is ever reconsidered — real academic benchmark validation (99.3% recall, Chicago Booth 2026), much lower reported false-positive rate (1-2%), real LMS integrations. Still carries the same "send private papers to a third party" and recurring-cost concerns any external API has. Not pursued either way — self-hosting was already working better.

#### Attempt 5 (the one that's actually wired in): `followsci/bert-ai-text-detector`

BERT-base, fine-tuned specifically on **1.86M academic paragraphs from arXiv** — MIT licensed (no RADAR-style restriction). Self-reported 99.57% accuracy treated with real skepticism (same as every other self-reported number this session) — the only number that mattered was our own calibration.

**Real result on the same 8 samples**: 5/8 correct, but — critically — **no bias against formal academic writing** (RADAR's specific failure mode doesn't show up here; 3 of 4 human samples correctly identified, including formal/technical ones). The two AI misses were both adversarially-constructed on purpose (a deliberately casual-register AI sample, and a close paraphrase of a human sample) — a real, expected limitation (adversarial/mimicking text is a known hard case for any detector), not a random failure. The model is also **overconfident when wrong** (0.0000/1.0000, not hedged) — worth keeping in mind when interpreting results; a wrong answer stated with 100% confidence is more dangerous than one that hedges.

**This is the model actually wired into the live pipeline now** (`app/ai/followsci_check.py`) — not because it's highly accurate, but because it was the only one of five approaches that avoided the specific bias that would actively harm real users, and its real-world weaknesses (adversarial/paraphrased text) are a more defensible, expected kind of failure than "flags formal writing as AI."

#### The pipeline architecture (matches the organizer's actual policy model)

Built after the project owner specified the real requirement: get text → chunk into buckets → score each bucket → **word-weighted percentage** (not a simple average) → compare against an **organizer-configured maximum** (e.g. "must be under 15%") → highlight flagged buckets.

- **`text_chunking.py`** — splits text into word-count buckets (default 300 words, fits BERT's 512-token limit with headroom), preserving exact character offsets into the original text. 9 tests.
- **`ai_content_pipeline.py`** — `aggregate_chunk_results()`: **word-weighted**, not a flat average — `percentage = (words in AI-flagged chunks) / (total words) × 100`. This was a real design correction: a flat average of probabilities treats every chunk as equally significant regardless of size, which doesn't correspond to "X% of the content" as a policy statement at all. **Accept requires strictly below the threshold** (exactly at the threshold fails — "must have less than 15%" was taken literally). The scorer is dependency-injected (defaults to `followsci_check`), so swapping to a future fine-tuned model is a one-line change, not a rewrite. 17 tests, including a hand-verified boundary case (exactly 15.0% → reject) and a direct comparison showing the identical document accepts at a looser 25% policy but rejects at a strict 15% one.
- Verified end-to-end on real T4 with the real model on a document that's genuinely half real human text, half genuinely Claude-written: correctly computed **31.82% AI-generated (140/440 words)** and correctly pointed the highlighted flagged chunk at the actual AI-written half, not a random or scattered match.

#### Wiring into the live pipeline

- `gate_engine.py`: `_ai_text_passes` — comparison direction is **inverted** from every other evaluator (`percentage < threshold` passes, not `score >= threshold`) — documented heavily in-code since copying the wrong pattern would silently accept everything except 100%-AI-generated submissions.
- **Real discovery while wiring this in**: `app/models/conferences.py` already has `NEVER_HARD_GATE = {"plagiarism", "ai_text"}`, a DB-enforced constraint (`ck_gate_rule_never_hard_gate`) from an earlier phase that a GateRule for this check_type can never be configured as a hard gate — only ever a soft flag for human review. Given everything found in attempts 1-4 about real false-positive risk, this is exactly the right call, already baked in before this session even started. A submission can never be auto-rejected purely on an AI-detection score.
- `submissions.py`: added to `checks_to_run`, gracefully degrades to a normal `status: "error"` result (not a crash) if torch/transformers/GPU aren't available on whatever machine runs the background task.
- Frontend: `AiTextDetectionReportCard` in `page.tsx` — shows the percentage (red if over the organizer's max), and each flagged chunk in its own highlighted paragraph block with its actual text, word count, and confidence — verified rendering correctly via a real Playwright screenshot against a real running instance.
- **Explicitly NOT built**: true highlighting drawn directly on the rendered PDF (boxes at exact page coordinates) — that needs mapping flagged text back to PDF bounding boxes (PyMuPDF's `search_for()` could do this, but it's new, real work). What exists is a dedicated highlighted-paragraph list in the AI Feedback panel — achieves "see exactly what was flagged and read it," just not as a canvas overlay.

#### Real path forward if `followsci`'s accuracy proves insufficient with more testing

Fine-tuning is no longer blocked on data collection the way it originally seemed — two real, purpose-built academic-domain datasets were found: `AITextDetect/AI_Polish_clean` (built specifically for generalization research in academic writing) and a 469K-real-arXiv-paragraph dataset from a 2026 paper (paired with 100K GPT-3.5 + 100K Gemini-generated paragraphs). That same paper's own properly-trained model got **81% balanced accuracy** (100% on GPT-3.5, 93% on Gemini, 76% human recall) — a realistic target to calibrate expectations against, not the near-100% numbers self-reported models keep claiming and not delivering.

**Future GPU scope, if ever revisited:**

| Setup | What it gets you | GPU needed |
|---|---|---|
| **Current (followsci, CPU-cheap BERT-base)** | Working now, real known weaknesses | T4 16GB (what we have) |
| **Fine-tune our own on real academic datasets above** | Best long-term fit, full control, no third-party dependency | T4 16GB is plenty for BERT/DeBERTa-base fine-tuning |
| **Zero-shot with the original Falcon-7B pair** (if ever revisited despite attempts 1-2's failure at smaller scale) | The specific, most-validated Binoculars configuration | A100 40GB or L40S 48GB |
| **Multi-method ensemble** (several approaches cross-validating) | Meaningfully more robust, closer to current research | A100 80GB |

### 4.4 Citation completeness — DONE, deterministic, no GPU risk

Built and fully unit-tested (18 tests: 10 pure XML-parsing, 8 mocked orchestration) in one pass, unlike ai_text's four-attempt saga — this check is deterministic extraction/comparison, the same category as table_figure_check.py, not an AI judgment call.

- **`backend/app/ai/citation_extraction.py`** — parses GROBID's TEI XML (confirmed against GROBID's own documentation, not assumed): in-text citations are `<ref type="bibr" target="#bN">`, bibliography entries are `<biblStruct xml:id="bN">` inside `<listBibl>`. Pure set comparison finds `broken_citations` (cited but no matching bibliography entry — a real defect) and `uncited_references` (in the bibliography but never cited — a *softer* signal, could be a legitimate "further reading" entry, deliberately doesn't affect the score).
- **`backend/app/ai/citation_check.py`** — the GROBID HTTP client (`POST /api/processFulltextDocument`, PDF as multipart field `input`). PDF-only, same reasoning as format-compliance — a `.docx` submission uses the already-converted PDF from the Word→PDF pipeline (§4.1), passed in by `submissions.py` rather than looked up independently.
- Score reflects `broken_citations` only, not `uncited_references` — a deliberate design correction made while building this (see the module docstring): weighting both the same would penalize a stylistic choice (an intentional further-reading entry) as if it were the same kind of problem as a genuinely broken reference.
- **Can be configured as a hard gate** (confirmed with a test) — unlike ai_text/logical_consistency, this is deterministic, not an AI judgment call, so it doesn't carry the same false-positive risk that justifies excluding those two.
- **Genuinely unverified beyond mocked tests**: GROBID itself was never actually run (no Docker/GROBID access in the environment this was built in) — see §7.3b for setup and what still needs a real run to confirm.
- Real robustness fix made while wiring this in: broadened the exception handling around the GROBID HTTP call to catch any unexpected failure shape (not just the two specific `httpx` exception subclasses), not just for its own sake — this also fixed 7 pre-existing tests that broke because their shared `fake_post` mock (used across several unrelated upload-integration tests) didn't expect the `files=` keyword argument GROBID's multipart upload uses, since `httpx.post` is a shared module-level function and monkeypatching it affects every caller, not just the one test intended to target.

### 4.5 Logical consistency — DONE and verified end-to-end (update35)

The first check that's a real LLM **judgment call** (Ollama + Qwen2.5-7B-Instruct reasoning about text), not deterministic extraction — same category of real risk as ai_text's whole saga (§4.3), approached the same way: build it carefully, test everything that can be tested without the real model, and be explicit about what still needs a real run.

**Scope, chosen deliberately narrow**: compares the paper's ABSTRACT against its CONCLUSION specifically — not an open-ended "check the whole paper for any inconsistency," which would be too vague a claim for an LLM to judge reliably and impossible to write a meaningful test against. Real, checkable cases this catches: a claimed accuracy/result number that differs between the two sections, an unconditional claim in the abstract that the conclusion hedges or contradicts, a claimed contribution the conclusion doesn't actually support.

- **`backend/app/ai/logical_consistency_scoring.py`** — pure logic, 20 tests: `extract_abstract_and_conclusion()` (regex-based section extraction, hand-verified against several real edge cases — missing sections, no trailing section after CONCLUSION, plural "CONCLUSIONS" heading) and `parse_llm_response()` (defensive JSON validation — strips markdown fences models sometimes wrap responses in despite instructions not to, validates required fields, and catches a real self-contradiction case: the model claiming `"consistent": true` while still listing findings, or `false` with an empty findings list).
- **`backend/app/ai/logical_consistency_check.py`** — the Ollama HTTP client. Uses Ollama's real **JSON-schema-constrained** structured output (the `format` parameter as a full JSON Schema object, a genuine grammar-level constraint during generation — not just `"format": "json"` or a hopeful prompt instruction), `temperature: 0` for determinism. 8 tests confirm the orchestration (including one that specifically checks only the abstract/conclusion text reaches the model, not the whole document).
- **Added to `NEVER_HARD_GATE`** alongside `ai_text`/`plagiarism` (see `app/models/conferences.py`) — an unverified LLM judgment must not be able to auto-reject a submission any more than ai_text's real, confirmed bias risk (§4.3) was allowed to. Confirmed the existing Pydantic-level enforcement (`GateRuleIn.validate_never_hard_gate`) picks up the new set member automatically — no separate code change needed there.
- **Verified end-to-end for real (Sept 2026, update35)**: Ollama + `qwen2.5:7b-instruct` (Q4_K_M, 4.68GB, pulled and served locally on a Lightning T4 Studio — confirmed running via `/api/tags`) was actually run against `run_logical_consistency_check()`, not mocked. Two real runs, not one:
  1. **Positive case** (§7.3c's deliberately obvious 95%-vs-80% abstract/conclusion mismatch): returned `consistent: False, score: 0.0`, with a correct finding pairing the two conflicting sentences and a coherent explanation of the discrepancy.
  2. **Negative control** (abstract and conclusion both stating 91% accuracy, explicitly consistent): returned `consistent: True, score: 100.0, findings: []` — added specifically to rule out a check that just rubber-stamps "inconsistent" regardless of input. Confirms the check genuinely discriminates, not just that it runs without erroring.
  
  Both runs used the real JSON-schema-constrained structured output at `temperature: 0`, matching the orchestration §4.5 already describes. T4's 15.3GB VRAM comfortably covers the ~5.5GB Qwen2.5-7B-Instruct needs at Q4_K_M — no OOM risk observed or expected in normal operation.

**A correction made while building this, worth remembering**: initially believed `NEVER_HARD_GATE`'s API-layer enforcement was missing (a comment claimed it existed but the router body didn't have it) and added a redundant check — turned out the enforcement already existed via a Pydantic `field_validator` on `GateRuleIn` in `schemas/conferences.py`, which the added router-level check could never actually reach (Pydantic validation happens before the endpoint body runs). Removed the dead code and corrected the comment rather than leave two enforcement paths, one of them unreachable — worth the reminder that "I can't find X" should mean "keep looking" before it means "X is missing."

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
- **LibreOffice (`soffice`) is not preinstalled on a fresh Lightning Studio** — confirmed directly (Aug 2026): a fresh instance's `pytest` run failed 5 tests with the wrong error signature until traced back to a missing binary, not a code bug. See §7.2b for the install command. Was deliberately caught by tests hitting the real binary rather than mocking it — same reasoning as §5.1: mocking `soffice` out would have hidden this deployment gap AND the permissive-garbage-input behavior documented in §4.1.

### 5.7 Text-box content is invisible to `doc.paragraphs` entirely — and IEEE's own template guidance tells authors to use text boxes for figures
Discovered via the table/figure consistency check's first real-document test: a real submitted `.docx` had genuine figure and table captions, but the check reported both as "referenced in the text but no matching caption was found." The captions were real — they just weren't in `doc.paragraphs` at all.

Root cause: `paragraph.text` / `run.text` in python-docx only walk a run's **direct** `w:t` children. Content inside a text box lives nested inside a `w:txbxContent` element (wrapped in either a legacy `<v:pict><v:textbox>` or a modern DrawingML shape) — structurally *not* a direct-child paragraph of the document body, so it's invisible to the normal paragraph-iteration approach every check up to this point relied on. This isn't a rare authoring choice: IEEE's own official conference-template guidance explicitly tells authors to insert figures via a text box ("more stable than directly inserting a picture directly"), so this will recur on other real submissions, not just this one.

Fixed in `backend/app/ai/docx_utils.py`'s new `extract_textbox_paragraphs()` — walks the document XML for every `w:txbxContent` element (covers both the legacy and modern wrapper with one tag-name search) and returns its paragraph text. `grammar_check.py`'s `extract_text_from_docx()` now appends this to the normal paragraph text, so **every check that reads document text** (grammar, table/figure, and format-compliance's structure checks) benefits, not just the check that happened to surface the gap. Text-box paragraphs are appended after body text rather than interleaved at their true position — reconstructing exact reading-order placement wasn't worth the complexity, since every consumer of this text does whole-document pattern matching, not position-dependent reading.

### 5.8 A schema field existing, and an endpoint returning a signed-URL-shaped string, doesn't mean the file is actually fetchable
Discovered while building the reviewer PDF viewer — before writing any frontend code, tracing whether `GET /pdf-url`'s returned URL could actually be fetched. It couldn't: `generate_signed_url()` signed a raw filesystem path, and `verify_signed_url()` existed but was never called anywhere — no route consumed the signature or served file bytes back. The one existing test only asserted the returned string *contained* `"signature="` and `"expires="`, never that a client could do anything with it.

This is a category of gap worth watching for generally: Phase 1 built the `PDFAnnotation` model, the signing helper, and a schema field all correctly in isolation, each of which looks "done" in a file listing or a passing test — but the actual end-to-end path (client asks for a URL → client fetches that URL → gets real bytes) was never wired together, and no test exercised that path. Fixed by making `pdf-url` sign `version_id` (not a raw path — also avoids leaking the container's filesystem layout to the client) and adding a real `pdf-stream` endpoint that verifies the signature and returns `FileResponse`. New tests fetch the signed URL **without an Authorization header** (matching how a browser's native PDF embed actually works, since it can't attach custom headers) to confirm the signature alone is sufficient — not just checking the endpoint exists.

### 5.9 A backend 404 handled correctly can still surface as an unhandled frontend failure — two separate failure points, only one of which had a fallback
Found the moment the app was actually used live (not sandbox testing) — a submission whose version had no real PDF (predates the Word→PDF pipeline, or a placeholder never actually uploaded) correctly 404'd from `pdf-stream`, exactly as designed and tested (§5.8). But `PdfAnnotationViewer.tsx` only caught a failure from the `getPdfUrl()` **metadata** call — `pdf-url` itself doesn't validate a real PDF exists (matches its original contract, see §5.8), so it always succeeds and returns a syntactically valid signed URL. The actual PDF *bytes* fetch happens separately, inside react-pdf's `<Document>` component, and THAT failure had no handler — it only surfaced as react-pdf's own internal `console.error`, leaving the user looking at a stuck/blank viewer with zero explanation, while the page itself still returned 200 (nothing actually crashed).

Two independent failure points along one user-facing flow; only handling one of them isn't enough. Fixed with `<Document onLoadError={...}>`, routed to the same friendly "PDF not available" message the metadata-failure path already used. Verified against the exact real scenario (a version with no converted PDF, live in a browser via Playwright) — confirmed the friendly message now renders — and separately confirmed the working case (a version with a real PDF) still renders correctly, so the fix didn't regress the happy path.

### 5.10 A file rendering correctly can still contain a real, visible defect that has nothing to do with the platform
Spotted by the project owner in a live screenshot, not caught in sandbox testing: a test fixture (`IEEE-filled-realistic.docx`, hand-built weeks earlier to validate the table/figure check against realistic content) rendered with a doubled caption — **"Fig. 1. Fig. 1. Detection accuracy..."** — in the PDF viewer. Traced directly rather than assumed: the document's `"figure caption"` paragraph *style itself* (in `styles.xml`) carries a built-in Word auto-numbering definition (`<w:numPr><w:numId w:val="2"/></w:numPr>`), which LibreOffice correctly resolves and renders as a visual "Fig. 1." prefix. The test fixture's construction script (run months earlier, not part of the shipped codebase) *also* typed a literal "Fig. 1." into that same paragraph's text — so the rendered PDF shows both the style's auto-generated prefix and the hand-typed one, stacked.

Confirmed as cosmetic and fixture-specific, not a platform bug: `python-docx`'s `paragraph.text` never resolves style-level numbering fields at all (only literal run text), which is exactly why the table/figure check still correctly scored this file 100% (6/6) — it only ever saw one "Fig. 1.", matching what was intended. No code change was needed; this is purely a artifact of one specific test file, not the conversion pipeline, the AI checks, or the viewer. Recorded here mainly as a reminder that "it renders" and "it's correct" are different claims, and a live screenshot review can catch things sandbox testing won't — worth continuing to share screenshots/live results, not just pytest/build output.

### 5.11 Monkeypatching a shared module-level function (like `httpx.post`) affects every caller, not just the one test targeting it
Found while wiring citation completeness in: 7 pre-existing, unrelated upload-integration tests suddenly failed with `TypeError: fake_post() got an unexpected keyword argument 'files'`. Those tests patch `httpx.post` globally (`monkeypatch.setattr(grammar_check_module.httpx, "post", fake_post)`) to fake LanguageTool's response for grammar_check.py — but `httpx` is one shared module object across the whole process, so patching `post` there intercepts *every* caller during that test, including citation_check.py's brand-new GROBID call, which uses a different call shape (`files=` for multipart upload) the old `fake_post(url, data=None, timeout=None)` stub never anticipated.

Two real fixes, not a workaround: (1) broadened both new checks' (citation, logical_consistency) exception handling around their external HTTP calls to catch any unexpected failure — including a `TypeError` from a malformed call — rather than just the two specific `httpx` exception subclasses, which is a genuine robustness improvement on its own (a real GROBID/Ollama deployment could hit plenty of failure modes beyond those two), and incidentally fixed the test breakage as a side effect, confirmed by rerunning rather than assumed. (2) Did NOT touch the old tests' `fake_post` stubs — the broadened exception handling was the right fix at the right layer, not papering over it by making test mocks more permissive.

### 5.12 "I can't find it" should mean "keep looking," not "it must be missing"
While wiring logical_consistency into the gate system, found a comment in `models/conferences.py` claiming `NEVER_HARD_GATE` was "also enforced at the API layer (routers/conferences.py)" — checked that file, found nothing, concluded the comment was aspirational/stale, and added a redundant enforcement check plus a whole paragraph explaining "the real fix." It wasn't needed: the enforcement genuinely existed, just in `schemas/conferences.py`'s `GateRuleIn.validate_never_hard_gate` Pydantic field validator, which runs before the endpoint body ever executes — meaning the newly-added router-level check was unreachable dead code from the moment it was written. Caught by actually running the existing test suite (`test_never_hard_gate_on_*` tests were already passing, which shouldn't have been possible if the enforcement were genuinely absent) rather than trusting the initial investigation. Removed the dead code, corrected the file-path reference in the original comment (it just pointed at the wrong of two real files), and left this note so the correction itself isn't lost — the mistake was investigating one file, not finding what the comment described, and concluding "missing" instead of "look at the schema file too."

---

## 6. Known, Documented Gaps (not silently dropped — explicitly flagged as follow-ups)

- **`.docx` column count isn't measured** — returns `None`, documented limitation, would need raw `<w:cols>` XML digging (not yet attempted).
- **`.docx` page count isn't knowable without rendering** — same reason page-limit check is PDF-only.
- **Reviewer-facing frontend pages were built early and haven't been re-verified** with the same real-build/real-test rigor later work received.
- **GROBID (citation completeness) was never actually run** — fully built and unit-tested with mocked external calls, but genuinely unverified end-to-end. See §7.3b for setup and the manual verification steps to run before trusting this on real submissions. (Ollama/logical-consistency was verified for real in update35 — see §4.5.)
- **Plagiarism/similarity check** — the one remaining unbuild check (§4.2). Blocked on a real prerequisite (no reference corpus of papers exists yet), not a coding gap — needs that decided/provided before this can start meaningfully.

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

### 7.2b LibreOffice (Word-to-PDF conversion dependency)
Not preinstalled on a fresh Lightning Studio — confirmed the hard way (Aug 2026): a full backend test run reported `soffice` missing, not just "some tests failed." `soffice` is a real production runtime dependency (not just a test one), so this needs to actually be present, not mocked around.
```bash
sudo apt-get update && sudo apt-get install -y libreoffice-writer
# no sudo available? try without it — most cloud dev containers run as root:
# apt-get update && apt-get install -y libreoffice-writer
which soffice && soffice --version
```
`libreoffice-writer` alone is enough — it pulls in `libreoffice-core` (which actually provides the `soffice` binary) as a dependency, without the full `libreoffice` metapackage's much larger footprint (Calc, Impress, etc., none of which this pipeline needs).

### 7.2c GPU verification + AI-text-detection dependencies
Confirm the Studio actually has a GPU and CUDA-enabled PyTorch before installing anything else — catches a misconfigured Studio immediately instead of failing confusingly mid-way through a model load:
```bash
nvidia-smi
python3 -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```
`nvidia-smi` should show a T4 with ~16GB. If `torch.cuda.is_available()` is `False` on a Studio that does have a GPU, PyTorch was likely installed without CUDA support — reinstall per [pytorch.org](https://pytorch.org)'s current command for the Studio's CUDA version rather than guessing a version number here (it changes over time).

`transformers` and `accelerate` are in `requirements.txt` now (added when this check was built) — `pip install -r requirements.txt` in §7.2 already covers them, no separate install step needed.

**The model actually used in production is `followsci/bert-ai-text-detector`** (see §4.3 for the full decision record — four other approaches were tried and rejected first). Pre-download it so the first real check run isn't the first time the download happens:
```bash
python3 -c "
from transformers import BertTokenizer, BertForSequenceClassification
name = 'followsci/bert-ai-text-detector'
print(f'Downloading {name}...')
BertTokenizer.from_pretrained(name)
BertForSequenceClassification.from_pretrained(name)
print('done')
"
```

**Other models downloaded during development (not used in production, but likely still cached on this Studio from testing — harmless to leave, or safe to delete from `~/.cache/huggingface` to reclaim space if needed):** `Qwen/Qwen2.5-0.5B`, `Qwen/Qwen2.5-0.5B-Instruct` (Binoculars attempt, rejected), `Qwen/Qwen2.5-3B` (Fast-DetectGPT attempt, rejected), `TrustSafeAI/RADAR-Vicuna-7B` (RADAR attempt, rejected for bias against formal writing), `microsoft/phi-1_5` (earliest model choice, superseded before a check was ever built against it).

### 7.3 LanguageTool (grammar check dependency)
```bash
docker start languagetool 2>/dev/null || docker run -d -p 8010:8010 --name languagetool erikvl87/languagetool
sleep 15
curl -s http://localhost:8010/v2/check -d "text=test&language=en-US" | head -c 100
```

### 7.3b GROBID (citation completeness check dependency)
Same Docker pattern as LanguageTool — a self-hosted service on port 8070. Not yet run/verified on any real Studio as of this writing; the citation check's own logic is fully unit-tested (see §4.1's citation completeness section), but the actual GROBID service integration needs a real run to confirm.
```bash
docker start grobid 2>/dev/null || docker run -d -p 8070:8070 --name grobid grobid/grobid:0.8.1
sleep 30  # GROBID's own startup is slower than LanguageTool's — it loads several CRF/DL models on boot
curl -s http://localhost:8070/api/isalive
```
Should return `true`. If `GROBID_URL` needs to point somewhere other than `http://localhost:8070` (citation_check.py's default), set it as an environment variable before starting the backend: `export GROBID_URL=http://your-host:8070`.

### 7.3c Ollama + Qwen2.5-7B-Instruct (logical consistency check dependency)
The first check needing a real LLM for judgment (not just extraction). Not yet run/verified on any real Studio as of this writing — same disclosure as every GPU-dependent check built this session (see §4.3's Binoculars/Fast-DetectGPT saga for why this matters): the orchestration and prompt are structurally sound but genuinely unverified until run for real.
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
sleep 5
ollama pull qwen2.5:7b-instruct
```
The model pull is a real, substantial download (~4-5GB depending on quantization) — expect this to take a few minutes depending on connection speed. Confirm it's working:
```bash
curl -s http://localhost:11434/api/tags | grep qwen2.5
```
If `OLLAMA_URL` needs to point somewhere other than `http://localhost:11434` (logical_consistency_check.py's default), set it as an environment variable: `export OLLAMA_URL=http://your-host:11434`.

**Manual verification worth running before trusting this check on real submissions** (mirrors the `run_manual_verification()` pattern used for the AI-text-detection checks — same file location convention):
```bash
cd ~/grmt-platform/backend
python3 -c "
from app.ai.logical_consistency_check import run_logical_consistency_check
import tempfile, os
from docx import Document

doc = Document()
doc.add_paragraph('ABSTRACT')
doc.add_paragraph('Our method achieves 95% accuracy on the benchmark dataset.')
doc.add_paragraph('CONCLUSION')
doc.add_paragraph('We achieved approximately 80% accuracy in our final evaluation.')
path = os.path.join(tempfile.mkdtemp(), 'test.docx')
doc.save(path)

result = run_logical_consistency_check(path)
print(result)
"
```
This is a deliberately obvious inconsistency (95% vs 80%) — if the check reports `"consistent": True` on this, something is wrong with the prompt or the model isn't actually being reached; if it correctly reports `"consistent": False` with a finding about the accuracy discrepancy, the real pipeline is working.

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
(If `npm run dev` fails with "command not found" via `nohup`, just retry the exact same block — see §5.6.) `npm install` now also pulls in `react-pdf` (the reviewer PDF viewer's dependency) — no separate step needed, it's in `package.json`.

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
Should show whatever passed count matches your last pushed commit on `dev` — apply any not-yet-pushed `updateN.zip` packages you've received on top (check with `git log --oneline -5` and compare against what's been discussed), then re-run to confirm **261 passed** (as of `update34` — citation completeness + logical consistency, the last two checks built).

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

## 9. What's Actually Left — Read This First If Resuming

Everything from the original roadmap (§9's old ordering, kept below for archaeology) is done except one item. Current real status:

1. ~~Table/figure consistency check~~ — **DONE**
2. ~~Word-to-PDF conversion pipeline~~ — **DONE**
3. ~~Reviewer PDF viewer & annotations~~ — **DONE**
4. ~~WebSocket live-push~~ — **DONE** (§4.1 has the details — real per-submission channel, not just the organizer queue channel)
5. ~~`/resubmit` real file uploads~~ — **DONE**
6. ~~AI-generated-text detection~~ — **DONE**, see §4.3's full saga (four attempts, three failures, the one that shipped)
7. ~~Citation completeness~~ — **DONE**, see §4.4 — built and tested, but GROBID itself was never actually run (§7.3b)
8. ~~Logical consistency~~ — **DONE AND VERIFIED END-TO-END (update35)**, see §4.5 — real Ollama + qwen2.5:7b-instruct run, positive case + negative control both correct

**The only thing left to build: plagiarism/similarity detection (BGE-M3 + FAISS).** Genuinely blocked, not just unstarted — it needs a reference corpus of papers to compare submissions against, and that corpus doesn't exist. This isn't a "go build it" task the way every other check was; it's a "go decide what the corpus should be and get it" task first. Worth raising directly with whoever owns this project rather than guessing at a source.

**One real verification task left, not code**:
- Run GROBID for real (§7.3b) and confirm citation completeness catches a genuine broken citation on a real paper — Ollama/logical-consistency's equivalent task is now done (update35).

Beyond that, this project has no other open threads. Everything else — Phase 1, the PDF pipeline, WebSocket, resubmit, and 6 of 7 AI checks — is built, tested, and (as far as `git log` on `dev` reflects what's actually been pushed) deployed.

### Original ordering (superseded, kept for historical context only)

<details>
<summary>Click to expand the old roadmap — not the current plan, just a record of how priorities shifted over the session</summary>

This was the original "easiest to build next" ordering, before the project owner explicitly paused WebSocket/resubmit to focus on AI checks, then circled back to finish them once the AI-check work stabilized:

1. Table/figure consistency check
2. Word-to-PDF conversion pipeline
3. Reviewer PDF viewer & annotations
4. Wire WebSocket live-push into the AI-report UI
5. Fix `/resubmit` to accept real file uploads
6. AI-generated-text detection
7. GROBID setup + citation-completeness check
8. Ollama + Qwen2.5-7B + logical-consistency check
9. Reference corpus + plagiarism check

</details>

---

## 10. Reference: Full File Inventory (Phase 2 AI code)

```
backend/app/ai/
├── grammar_check.py           # LanguageTool integration, chunking, byline/refs trimming, acronym filter
├── pdf_text_extraction.py     # Column-aware PDF text extraction, dehyphenation, page_map tracking
├── format_compliance_check.py # IEEE margin/font/structure checks, page-size-aware
├── table_figure_check.py      # Caption<->reference consistency, numbering gaps/duplicates (.docx + .pdf)
├── docx_utils.py              # Shared open_docx() + extract_textbox_paragraphs() (text-box content)
│
│   AI-text-detection — see §4.3 for the full saga. Only followsci_check.py
│   + text_chunking.py + ai_content_pipeline.py are actually wired into the
│   live pipeline. The rest are kept for the historical record / in case
│   future GPU access changes the calculus — NOT used in production.
├── binoculars_scoring.py      # Pure perplexity/cross-perplexity math — REJECTED approach, unused, 13 hand-verified tests
├── ai_text_detection_check.py # Binoculars model inference (Qwen2.5-0.5B pair) — REJECTED approach, unused
├── fast_detect_gpt_scoring.py # Pure curvature-statistic math — REJECTED approach, unused, 14 hand-verified tests
├── fast_detect_gpt_check.py   # Fast-DetectGPT model inference (Qwen2.5-3B) — REJECTED approach, unused
├── radar_check.py             # RADAR classifier (TrustSafeAI/RADAR-Vicuna-7B) — REJECTED (bias vs. formal writing), unused
├── followsci_check.py         # ★ ACTUALLY USED — followsci/bert-ai-text-detector, academic-domain BERT classifier
├── text_chunking.py           # ★ ACTUALLY USED — word-count bucketing with original-text character offsets
├── ai_content_pipeline.py     # ★ ACTUALLY USED — chunk->score->word-weighted-percentage->threshold->highlight orchestration
│
├── citation_extraction.py     # ★ ACTUALLY USED — pure TEI-XML parsing/comparison, no GROBID dependency, 10 tests
├── citation_check.py          # ★ ACTUALLY USED — GROBID HTTP client + orchestration, 8 mocked tests, GROBID itself never actually run
│
├── logical_consistency_scoring.py # ★ ACTUALLY USED — pure JSON-response validation + abstract/conclusion section extraction, 20 tests
└── logical_consistency_check.py   # ★ ACTUALLY USED — Ollama HTTP client + orchestration, 8 mocked tests, Ollama itself never actually run

backend/app/core/
└── word_to_pdf.py             # LibreOffice headless Word->PDF conversion, per-call profile isolation

backend/app/core/gate_engine.py  # CHECK_EVALUATORS registry (grammar, format, table_figure, citation, logical_consistency — score>=threshold; ai_text — INVERTED, percentage<threshold), evaluate_submission_gates()

backend/app/models/conferences.py  # NEVER_HARD_GATE = {"plagiarism", "ai_text", "logical_consistency"} — DB-enforced (ck_gate_rule_never_hard_gate) AND API-enforced (schemas/conferences.py's GateRuleIn.validate_never_hard_gate)

backend/app/routers/
├── submissions.py             # _run_ai_checks_and_store() + _convert_to_pdf_and_store() background tasks, upload + resubmit endpoints (6 checks per upload now)
├── files.py                   # pdf-url (issues signed URL) + pdf-stream (actually serves bytes, signature-only auth) + annotation CRUD
├── ws.py                      # submission:{id}:updates channel (researcher/reviewer/organizer scoped) + conference:{id}:queue (organizer/co-admin only)
└── conferences.py             # gate-rules endpoints

backend/tests/
├── test_grammar_check.py
├── test_pdf_text_extraction.py
├── test_format_compliance_check.py
├── test_table_figure_check.py
├── test_docx_utils.py
├── test_gate_engine.py        # includes ai_text's inverted-comparison + citation/logical_consistency evaluators + NEVER_HARD_GATE tests
├── test_word_to_pdf.py        # real soffice conversion, no mocking
├── test_files.py              # real signed-URL streaming: fetchable, tamper-rejected, expiry-rejected, real annotation CRUD
├── test_ws.py                 # includes submission:{id}:updates channel authorization (owner/reviewer/organizer/denied cases) + real live-push confirmation
├── test_binoculars_scoring.py # pure math tests for the rejected Binoculars approach
├── test_fast_detect_gpt_scoring.py # pure math tests for the rejected Fast-DetectGPT approach
├── test_radar_check.py        # mocked orchestration tests for the rejected RADAR approach
├── test_followsci_check.py    # mocked orchestration tests for the check actually in use
├── test_text_chunking.py      # word-count bucketing, hand-verified
├── test_ai_content_pipeline.py # word-weighted aggregation, hand-verified boundary cases, mocked end-to-end orchestration
├── test_citation_extraction.py  # pure TEI-XML parsing, hand-built realistic GROBID-shaped fixtures
├── test_citation_check.py       # mocked GROBID orchestration
├── test_logical_consistency_scoring.py  # JSON validation + section extraction, hand-verified
├── test_logical_consistency_check.py    # mocked Ollama orchestration
├── test_conferences.py        # includes NEVER_HARD_GATE tests for all 3 excluded check_types + confirms citation CAN hard-gate
└── test_submissions.py        # includes integration tests for all 6 live checks + PDF conversion + resubmit re-running checks

frontend/app/submissions/[id]/page.tsx  # GrammarReportCard + FormatReportCard + TableFigureReportCard + AiTextDetectionReportCard + CitationReportCard + LogicalConsistencyReportCard + PdfAnnotationViewer + WebSocket live-push wiring
frontend/components/PdfAnnotationViewer.tsx  # react-pdf-based viewer, click-to-annotate (reviewer-gated), percentage-positioned pins
frontend/lib/api.ts                     # All check result types (Grammar/Format/TableFigure/AiTextDetection/Citation/LogicalConsistency) + Annotation/SignedUrl types + resubmit() now takes a real File
```

**Explicitly NOT built for ai_text**: true highlighting drawn on top of the rendered PDF (boxes at exact page coordinates) — needs new work mapping flagged text to PDF bounding boxes (PyMuPDF's `search_for()` could do this). What exists is a highlighted-paragraph list in the AI Feedback panel instead — see §4.3's wiring section for the full explanation of this scope decision.

