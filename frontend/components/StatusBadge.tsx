const STATUS_STYLE: Record<string, string> = {
  submitted: 'bg-[var(--color-accent-soft)] text-[var(--color-accent)]',
  processing: 'bg-[var(--color-accent-soft)] text-[var(--color-accent)]',
  ai_review_passed: 'bg-[var(--color-accent-soft)] text-[var(--color-accent)]',
  ai_review_hard_failed: 'bg-red-50 text-red-700',
  in_human_review: 'bg-[var(--color-accent-soft)] text-[var(--color-accent)]',
  revise_resubmit: 'bg-amber-50 text-amber-700',
  accepted: 'bg-emerald-50 text-emerald-700',
  rejected: 'bg-red-50 text-red-700',
};

const STATUS_LABEL: Record<string, string> = {
  submitted: 'Submitted',
  processing: 'Processing',
  ai_review_passed: 'AI Review Passed',
  ai_review_hard_failed: 'AI Review Failed',
  in_human_review: 'In Human Review',
  revise_resubmit: 'Revise & Resubmit',
  accepted: 'Accepted',
  rejected: 'Rejected',
};

export default function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLE[status] ?? 'bg-gray-100 text-gray-600';
  const label = STATUS_LABEL[status] ?? status;
  return (
    <span className={`inline-block px-2.5 py-1 text-xs font-bold uppercase tracking-wide ${style}`}>
      {label}
    </span>
  );
}
