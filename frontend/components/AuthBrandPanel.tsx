import Image from 'next/image';

// Signature element: manuscript-annotation marks — kept, per design_prompt.md,
// as an auth-only motif. Typography now matches the rest of the app (Anton
// for the headline), closing the earlier inconsistency with the dashboard
// and marketing pages.
export default function AuthBrandPanel() {
  return (
    <div className="hidden lg:flex lg:w-[42%] flex-col justify-between border-r border-[var(--color-line)] bg-white px-12 py-14">
      <div className="flex items-center gap-3">
        <Image
          src="/images/logo.jpg"
          alt="Gudsky Research Foundation"
          width={48}
          height={48}
          className="rounded-full"
        />
        <div>
          <span className="font-display-bold text-lg tracking-tight text-[var(--color-ink)]">
            GRMT
          </span>
          <p className="text-xs text-black/50">Gudsky Research Management Tool</p>
        </div>
      </div>

      <div className="space-y-6">
        <h1 className="font-display-bold text-4xl leading-[0.98] text-[var(--color-ink)]">
          Every Submission,
          <br />
          Pre-Reviewed Before
          <br />A Human Opens It.
        </h1>
        <p className="text-black/60 text-sm max-w-sm">
          Grammar, citations, structure, and originality — checked instantly, so reviewers spend
          their time on the science, not the mechanics.
        </p>

        <div className="space-y-3 pt-4" aria-hidden="true">
          {[
            { label: 'Citation completeness', mark: '✓' },
            { label: 'Structure vs. publisher format', mark: '✓' },
            { label: 'Originality flag — human confirms', mark: '⚑' },
          ].map((row) => (
            <div key={row.label} className="flex items-center gap-3 text-xs text-black/45">
              <span className="flex h-5 w-5 items-center justify-center rounded-sm border border-[var(--color-line)] text-[10px] text-[var(--color-accent)]">
                {row.mark}
              </span>
              <span className="border-t border-dashed border-[var(--color-line)] flex-1 pt-2">
                {row.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="text-xs text-black/45 space-y-1">
        <p className="font-medium text-black/60">Gudsky Research Foundation</p>
        <p>Section 8 Non-Profit · AICTE-Approved · DPIIT Startup India Recognized</p>
        <p className="pt-1 text-black/35">Platform developed &amp; maintained by GRMT Pvt. Ltd.</p>
      </div>
    </div>
  );
}
