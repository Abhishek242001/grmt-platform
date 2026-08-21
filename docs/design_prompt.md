# GRMT Design System — Restart Prompt

**How to use this file:** upload this to Claude at the start of a new session and say
"follow this design system for GRMT" (or similar). It captures the visual language,
structural patterns, and content rules already implemented in the live app, so new work
stays consistent instead of drifting to generic defaults.

---

## 1. Brand identity

- **Product name:** GRMT (Gudsky Research Management Tool)
- **Logo:** a formal seal — laurel wreath, eagle-and-cloud mark, "GUDSKY RESEARCH
  FOUNDATION" circular text, three stars. Deep royal blue on white/transparent.
  File lives at `frontend/public/images/logo.jpg`.
- **Organization:** Gudsky Research Foundation (Section 8 non-profit, AICTE-approved,
  DPIIT Startup India recognized) — R&D. GRMT Pvt. Ltd. — product ownership/maintenance.
  Always credit both correctly; never conflate them.

## 2. Color tokens (CSS variables, defined in `app/globals.css`)

--color-ink: #0f172a;          primary text, near-navy-black
--color-paper: #ffffff;         primary background
--color-hero: #0a0e1a;          the ONE dark section, hero only
--color-accent: #1341b1;        GRMT blue, pulled directly from the real logo
--color-accent-dark: #0d2f86;   hover/pressed states
--color-accent-light: #5c8dff;  text/accents ON DARK backgrounds only
--color-accent-soft: #eaeffb;   light tint for badges, hover backgrounds
--color-line: #e2e5ec;          hairline borders throughout

Rule: the entire site is white/light. Exactly one section is allowed to be dark —
the homepage hero. Don't add a second dark section without deciding that deliberately.

## 3. Typography

- Display/bold headlines: Anton (Google Fonts), .font-display-bold utility class.
  Big headline moments only, not body text.
- Body/UI text: Inter, used everywhere else.
- Source Serif 4 (.font-display) exists on the auth pages only (manuscript feel).
  Anton is preferred for new marketing work. Don't silently migrate auth pages.

## 4. Structural motifs (reuse, don't reinvent)

- Marquee ticker band: components/MarqueeBand.tsx, items: string[] prop.
- Dense info cards in a hairline grid: grid gap-px + bg-[var(--color-line)] container.
- Diagonal clip-path buttons: clipPath polygon(5% 0, 100% 0, 95% 100%, 0 100%)
  for primary CTAs only.
- Stats band: 4-column grid, big Anton numerals, hairline top/bottom borders.
- Manuscript-annotation motif: AuthBrandPanel.tsx only, don't reuse elsewhere.

## 5. Content rules (non-negotiable)

- Never fabricate testimonials/user quotes for GRMT — it's a real product. Use real
  documented policy content instead (see the homepage Trust & Policy section for the
  pattern).
- Three non-negotiable product rules, if referenced: (1) AI-content/plagiarism checks
  are soft-flag only, never hard gate, enforced at the API layer; (2) reviewers always
  see confidence scores + highlighted spans, never a bare yes/no; (3) cross-conference
  history is reviewer/organizer-only, summary-only, never full comments.
- Accurate current numbers if quoted: 7 automated checks, 6 AI models, 2 publisher
  formats (IEEE, Springer). Update this file if the count changes.

## 6. What NOT to default to

Avoid generic AI-design tells: warm cream + terracotta, near-black + acid-green,
dense broadsheet-serif layouts. The white/blue + bold condensed type direction was a
deliberate choice against those defaults.

## 7. Where things live

- frontend/app/globals.css — color tokens, font setup
- frontend/tailwind.config.js — brand color scale
- frontend/components/MarketingNav.tsx — public site nav
- frontend/components/MarqueeBand.tsx — reusable ticker
- frontend/components/AuthBrandPanel.tsx — auth-page panel (Source Serif variant)
- frontend/app/page.tsx — homepage built from this system
- frontend/public/images/logo.jpg — real logo file

## 8. Full project context

This covers visual/brand consistency only. For architecture, build phases, decisions
log, and known issues, the companion file is GRMT_Planning_Log.md — upload both
together for general project work, or just this file for purely visual tasks.

UPDATE: auth pages (login/signup) have now been migrated to the shared Anton/
font-display-bold system and diagonal clip-path buttons, matching the landing page
and dashboard. Source Serif 4 (.font-display) is deprecated — don't use it on new
pages.
