import Link from 'next/link';
import MarketingNav from '@/components/MarketingNav';
import MarqueeBand from '@/components/MarqueeBand';

const AUDIENCE_CARDS = [
  {
    tag: 'Role 01',
    kicker: '/ Submit',
    title: 'Researcher',
    rows: [
      ['Get', 'Instant AI feedback'],
      ['See', 'Confidence + highlights'],
      ['Track', 'Cross-conference history'],
      ['Format', 'Word (.docx) upload'],
    ],
  },
  {
    tag: 'Role 02',
    kicker: '/ Configure',
    title: 'Organizer',
    rows: [
      ['Set', 'Hard & soft gate rules'],
      ['Choose', 'IEEE, Springer format'],
      ['Monitor', 'Submission queue, live'],
      ['Control', 'Per-check thresholds'],
    ],
    highlight: true,
  },
  {
    tag: 'Role 03',
    kicker: '/ Review',
    title: 'Reviewer',
    rows: [
      ['Read', 'AI flags with evidence'],
      ['Never', 'A bare yes/no verdict'],
      ['View', 'Watermarked, secure PDF'],
      ['Decide', 'The science, not the format'],
    ],
  },
];

const ENGINE_CARDS = [
  {
    role: 'Grammar',
    name: 'LanguageTool',
    desc: 'Self-hosted grammar and style checking, run against the full manuscript text.',
  },
  {
    role: 'Citation & Structure',
    name: 'GROBID 0.9.0',
    desc: 'Parses title, abstract, section order, and reference completeness from the document.',
  },
  {
    role: 'Originality',
    name: 'BGE-M3 + FAISS',
    desc: 'Semantic similarity search against a reference corpus, plus exact-match hashing.',
  },
  {
    role: 'Reasoning',
    name: 'Qwen2.5-7B-Instruct',
    desc: 'Checks logical consistency between abstract and conclusion; writes resubmission summaries.',
  },
  {
    role: 'AI-Text Detection',
    name: 'Binoculars',
    desc: 'Perplexity-based detection, one of two detectors that must agree before a flag is raised.',
  },
  {
    role: 'AI-Text Detection',
    name: 'Fast-DetectGPT',
    desc: 'The second detector in the dual-agreement pair, reducing false positives on real writing.',
  },
];

const TRUST_CARDS = [
  {
    n: '01',
    title: 'Never a hard gate on originality',
    body:
      'AI-content and plagiarism/similarity checks can only ever be a soft flag requiring human ' +
      'confirmation, never an auto-reject. Enforced at the API layer because of documented ' +
      'false-positive rates against non-native-English writing.',
  },
  {
    n: '02',
    title: 'Confidence, not verdicts',
    body:
      'Reviewers see AI flags with confidence scores and highlighted spans, never a bare yes/no. ' +
      'The reasoning is always visible, never hidden behind a single score.',
  },
  {
    n: '03',
    title: 'History without exposure',
    body:
      'Cross-conference submission history is visible to reviewers and organizers only, never to ' +
      'researchers, and never as full comments from another conference, only a short AI-generated summary.',
  },
];

const STATS = [
  ['7', 'Automated Checks'],
  ['6', 'AI Models'],
  ['2', 'Publisher Formats'],
  ['0', 'Bare Yes/No Verdicts'],
];

const CRED_BADGES = ['Section 8 Non-Profit', 'AICTE-Approved', 'DPIIT Startup India Recognized'];

export default function LandingPage() {
  return (
    <div className="bg-white text-[var(--color-ink)]">
      <MarketingNav />

      <section
        className="relative flex min-h-[92vh] flex-col justify-center overflow-hidden pt-24"
        style={{ backgroundColor: 'var(--color-hero)' }}
      >
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background: 'radial-gradient(ellipse at 75% 30%, rgba(19,65,177,0.35) 0%, transparent 55%)',
          }}
        />
        <div className="relative z-10 mx-auto w-full max-w-[1360px] px-8 pb-16">
          <span className="text-xs font-bold uppercase tracking-[0.22em] text-[var(--color-accent-light)]">
            Gudsky Research Management Tool
          </span>

          <h1 className="font-display-bold mt-4 max-w-[17ch] text-white text-[clamp(2.8rem,7.5vw,6.4rem)]">
            Every Submission,
            <br />
            <span className="text-[var(--color-accent-light)]">Pre-Reviewed</span>
            <br />
            Before A Human
            <br />
            Opens It.
          </h1>

          <p className="mt-5 max-w-[46ch] text-[1.1rem] font-medium text-white/70">
            Grammar, citations, structure, and originality, checked instantly against your
            conference&apos;s own publisher format, so reviewers spend their time on scientific
            judgment, not mechanical checks.
          </p>

          <div className="mt-8 mb-11 flex flex-wrap items-center gap-4">
            <Link href="/signup">
              <button
                className="bg-[var(--color-accent)] px-8 py-4 text-sm font-extrabold uppercase tracking-wide text-white transition hover:-translate-y-0.5 hover:bg-[var(--color-accent-light)]"
                style={{ clipPath: 'polygon(5% 0, 100% 0, 95% 100%, 0 100%)' }}
              >
                Create Free Account
              </button>
            </Link>

            <a
              href="#engine"
              className="border border-white/20 px-7 py-4 text-sm font-bold uppercase tracking-wide text-white transition hover:border-[var(--color-accent-light)] hover:text-[var(--color-accent-light)]"
            >
              See How It Works
            </a>
          </div>

          <div className="flex flex-wrap gap-3">
            {CRED_BADGES.map((badge) => (
              <span
                key={badge}
                className="border border-white/15 px-3.5 py-1.5 text-xs font-bold uppercase tracking-wide text-white/70"
              >
                {badge}
              </span>
            ))}
          </div>
        </div>
      </section>

      <MarqueeBand items={['GRAMMAR', 'CITATIONS', 'STRUCTURE', 'ORIGINALITY', 'FORMAT', 'CONSISTENCY']} />

      <section className="bg-[var(--color-paper)] py-22" id="audience">
        <div className="mx-auto max-w-[1360px] px-8">
          <div className="mb-12 flex flex-wrap items-end justify-between gap-5">
            <h2 className="font-display-bold text-[clamp(2rem,4vw,3.2rem)]">
              Built For
              <br />
              Every Role.
            </h2>
            <p className="max-w-[36ch] text-[var(--color-ink)]/60">
              One AI layer, three completely different experiences, because a researcher, an
              organizer, and a reviewer need different things from it.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-px bg-[var(--color-line)] md:grid-cols-3">
          {AUDIENCE_CARDS.map((card) => (
            <div key={card.title} className="bg-white px-8 py-9 transition hover:bg-[var(--color-accent-soft)]">
              <span
                className={
                  card.highlight
                    ? 'inline-block border border-[var(--color-accent)] bg-[var(--color-accent)] px-2.5 py-1 text-[0.7rem] font-extrabold uppercase tracking-wide text-white'
                    : 'inline-block border border-[var(--color-line)] bg-[var(--color-paper)] px-2.5 py-1 text-[0.7rem] font-extrabold uppercase tracking-wide'
                }
              >
                {card.tag}
              </span>

              <div className="mt-3 font-display-bold text-sm text-[var(--color-accent)]">{card.kicker}</div>
              <h3 className="font-display-bold my-3 text-3xl">{card.title}</h3>

              <ul>
                {card.rows.map((row) => (
                  <li
                    key={row[0]}
                    className="flex justify-between border-b border-[var(--color-line)] py-2 text-sm font-semibold text-[var(--color-ink)]/55"
                  >
                    <span>{row[0]}</span>
                    <span className="text-[var(--color-ink)]">{row[1]}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="py-22" id="engine">
        <div className="mx-auto max-w-[1360px] px-8">
          <div className="mb-12 flex flex-wrap items-end justify-between gap-5">
            <h2 className="font-display-bold text-[clamp(2rem,4vw,3.2rem)]">
              Six Models.
              <br />
              One Pipeline.
            </h2>
            <p className="max-w-[36ch] text-[var(--color-ink)]/60">
              Every check is powered by a model chosen for that specific job, not one
              general-purpose model doing everything.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-px bg-[var(--color-line)] md:grid-cols-3">
          {ENGINE_CARDS.map((item) => (
            <div key={item.name} className="bg-white px-7 py-8">
              <span className="mb-3.5 inline-block border border-[var(--color-accent-soft)] bg-[var(--color-accent-soft)] px-2.5 py-1 text-[0.68rem] font-extrabold uppercase tracking-wide text-[var(--color-accent)]">
                {item.role}
              </span>
              <h3 className="mb-2 text-xl font-extrabold">{item.name}</h3>
              <p className="text-sm text-[var(--color-ink)]/55">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-2 border-y border-[var(--color-line)] md:grid-cols-4">
        {STATS.map((stat) => (
          <div key={stat[1]} className="border-r border-[var(--color-line)] px-6 py-9 text-center md:border-r">
            <div className="font-display-bold text-4xl text-[var(--color-accent)]">{stat[0]}</div>
            <div className="mt-1 text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/55">
              {stat[1]}
            </div>
          </div>
        ))}
      </div>

      <section className="bg-[var(--color-paper)] py-22" id="trust">
        <div className="mx-auto max-w-[1360px] px-8">
          <div className="mb-12 flex flex-wrap items-end justify-between gap-5">
            <h2 className="font-display-bold text-[clamp(2rem,4vw,3.2rem)]">
              Built On A
              <br />
              Non-Negotiable Rule.
            </h2>
            <p className="max-w-[36ch] text-[var(--color-ink)]/60">
              The policies behind GRMT aren&apos;t marketing, they&apos;re enforced in the code, not
              just the UI.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            {TRUST_CARDS.map((item) => (
              <div key={item.n} className="border border-[var(--color-line)] bg-white p-7">
                <div className="font-display-bold mb-4 flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-accent-soft)] text-sm text-[var(--color-accent)]">
                  {item.n}
                </div>
                <h3 className="mb-2.5 text-lg font-extrabold">{item.title}</h3>
                <p className="text-sm text-[var(--color-ink)]/55">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[var(--color-accent)] py-20 text-center text-white">
        <div className="mx-auto max-w-[1360px] px-8">
          <span className="text-xs font-bold uppercase tracking-[0.22em] text-white/80">Free To Start</span>
          <h2 className="font-display-bold mt-3 mb-4 text-[clamp(2.2rem,5.5vw,4.2rem)]">
            Submit Smarter.
            <br />
            Review Faster.
          </h2>
          <p className="mb-7 text-[1.05rem] font-semibold text-white/90">
            Create an account as a researcher, organizer, or reviewer, no credit card required.
          </p>
          <Link href="/signup">
            <button
              className="bg-[var(--color-ink)] px-10 py-4 text-sm font-extrabold uppercase tracking-wide text-white transition hover:-translate-y-0.5"
              style={{ clipPath: 'polygon(5% 0, 100% 0, 95% 100%, 0 100%)' }}
            >
              Create Free Account
            </button>
          </Link>
        </div>
      </section>

      <footer className="py-13">
        <div className="mx-auto max-w-[1360px] px-8">
          <div className="mb-9 flex flex-wrap justify-between gap-10">
            <div className="max-w-[280px]">
              <div className="mb-3.5 flex items-center gap-2.5">
                <img src="/images/logo.jpg" alt="Gudsky Research Foundation" className="h-8 w-8 rounded-full" />
                <span className="font-display-bold text-lg">GRMT</span>
              </div>
              <p className="text-sm text-[var(--color-ink)]/55">
                An AI pre-review layer for academic conference and paper management.
              </p>
            </div>

            <div>
              <h4 className="mb-3.5 text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/40">
                Platform
              </h4>
              <a href="#audience" className="mb-1.5 block text-sm text-[var(--color-ink)]/55 hover:text-[var(--color-accent)]">
                Who It&apos;s For
              </a>
              <a href="#engine" className="mb-1.5 block text-sm text-[var(--color-ink)]/55 hover:text-[var(--color-accent)]">
                The AI Layer
              </a>
              <a href="#trust" className="mb-1.5 block text-sm text-[var(--color-ink)]/55 hover:text-[var(--color-accent)]">
                Trust &amp; Policy
              </a>
            </div>

            <div>
              <h4 className="mb-3.5 text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/40">
                Account
              </h4>
              <Link href="/login" className="mb-1.5 block text-sm text-[var(--color-ink)]/55 hover:text-[var(--color-accent)]">
                Log In
              </Link>
              <Link href="/signup" className="mb-1.5 block text-sm text-[var(--color-ink)]/55 hover:text-[var(--color-accent)]">
                Create Account
              </Link>
            </div>

            <div>
              <h4 className="mb-3.5 text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/40">
                Organization
              </h4>
              <p className="mb-1.5 text-sm text-[var(--color-ink)]/55">Gudsky Research Foundation</p>
              <p className="mb-1.5 text-sm text-[var(--color-ink)]/55">Section 8 Non-Profit</p>
              <a href="https://www.gudsky.org" className="text-sm text-[var(--color-ink)]/55 hover:text-[var(--color-accent)]">
                gudsky.org
              </a>
            </div>
          </div>

          <div className="flex flex-wrap justify-between gap-3 border-t border-[var(--color-line)] pt-5 text-xs text-[var(--color-ink)]/40">
            <span>© 2026 GRMT Pvt. Ltd. Product developed &amp; maintained by GRMT Pvt. Ltd.</span>
            <span>R&amp;D by Gudsky Research Foundation</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
