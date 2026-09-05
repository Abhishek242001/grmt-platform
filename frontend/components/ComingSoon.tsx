export default function ComingSoon({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="border border-dashed border-[var(--color-line)] bg-[var(--color-paper)] px-6 py-8 text-center">
      <span className="inline-block border border-[var(--color-accent-soft)] bg-[var(--color-accent-soft)] px-2.5 py-1 text-[0.68rem] font-extrabold uppercase tracking-wide text-[var(--color-accent)]">
        Coming Soon
      </span>
      <h3 className="mt-3 text-lg font-extrabold">{title}</h3>
      <p className="mx-auto mt-1.5 max-w-[32ch] text-sm text-[var(--color-ink)]/55">
        {description}
      </p>
    </div>
  );
}
