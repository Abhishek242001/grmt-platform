'use client';

import dynamic from 'next/dynamic';
import { FormEvent, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';
import StatusBadge from '@/components/StatusBadge';

// react-pdf touches browser-only APIs (Canvas, DOMMatrix) that don't exist
// during Next.js's server render — ssr: false is required, not optional,
// or the build itself fails.
const PdfAnnotationViewer = dynamic(() => import('@/components/PdfAnnotationViewer'), {
  ssr: false,
  loading: () => <p className="mt-3 text-sm text-[var(--color-ink)]/45">Loading viewer…</p>,
});

function GrammarReportCard({ report }: { report: api.AIReport }) {
  let result: api.GrammarCheckResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-red-600">
        Grammar check failed: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Grammar</span>
        <span className="font-display-bold text-2xl text-[var(--color-accent)]">{result.score}</span>
        <span className="text-xs text-[var(--color-ink)]/50">
          {result.error_count} flagged issue{result.error_count === 1 ? '' : 's'}
        </span>
      </div>

      {result.chunks_total !== undefined && (
        <p className="mt-1.5 text-xs text-[var(--color-ink)]/40">
          Full document checked
          {result.word_count ? ` — ${result.word_count.toLocaleString()} words` : ''}
          {result.chunks_total > 1 ? ` across ${result.chunks_total} sections` : ''}
          {result.chunks_checked !== undefined && result.chunks_checked < result.chunks_total
            ? ` (${result.chunks_total - result.chunks_checked} section(s) failed to check — results may be incomplete)`
            : ''}
        </p>
      )}

      {result.matches.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.matches.map((m, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="font-bold">{m.category || m.rule_id}</span>
                {m.page != null && (
                  <span className="whitespace-nowrap text-xs font-bold uppercase tracking-wide text-[var(--color-accent)]">
                    Page {m.page}
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-[var(--color-ink)]/60">{m.message}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FormatReportCard({ report }: { report: api.AIReport }) {
  let result: api.FormatCheckResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-red-600">
        Format check failed: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Format ({(result.publisher_format || 'ieee').toUpperCase()})</span>
        <span className="font-display-bold text-2xl text-[var(--color-accent)]">{result.score}</span>
        <span className="text-xs text-[var(--color-ink)]/50">
          {result.checks_passed}/{result.checks_total} checks passed
        </span>
      </div>

      {result.issues.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.issues.map((issue, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm text-[var(--color-ink)]/70">
              {issue}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TableFigureReportCard({ report }: { report: api.AIReport }) {
  let result: api.TableFigureCheckResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-red-600">
        Table/figure check failed: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  const nothingToCheck = !result.figures_found && !result.tables_found;

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Tables &amp; Figures</span>
        {result.score !== null ? (
          <span className="font-display-bold text-2xl text-[var(--color-accent)]">{result.score}</span>
        ) : (
          <span className="text-xs text-[var(--color-ink)]/50">No tables or figures detected</span>
        )}
        {result.score !== null && (
          <span className="text-xs text-[var(--color-ink)]/50">
            {result.checks_passed}/{result.checks_total} checks passed
          </span>
        )}
      </div>

      {!nothingToCheck && result.issues.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.issues.map((issue, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm text-[var(--color-ink)]/70">
              {issue}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SubmissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [submission, setSubmission] = useState<api.Submission | null>(null);
  const [history, setHistory] = useState<api.SubmissionVersion[]>([]);
  const [decision, setDecision] = useState<api.Decision | null>(null);
  const [reviews, setReviews] = useState<api.Review[]>([]);
  const [aiReports, setAiReports] = useState<api.AIReport[]>([]);
  const [error, setError] = useState<string | null>(null);

  // resubmit form state
  const [file, setFile] = useState<File | null>(null);
  const [resubmitting, setResubmitting] = useState(false);

  // reviewer form state
  const [recommendation, setRecommendation] = useState('accept');
  const [comments, setComments] = useState('');
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewSuccess, setReviewSuccess] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  function reload() {
    if (!id) return;
    api.getSubmission(id).then(setSubmission).catch(() => setError('Submission not found'));
    api.getSubmissionHistory(id).then(setHistory).catch(() => {});
    api.getDecision(id).then(setDecision).catch(() => {});
    api.listReviews(id).then(setReviews).catch(() => {});
    api.getAiReports(id).then(setAiReports).catch(() => {});
  }

  useEffect(() => {
    if (!user) return;
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, id]);

  // Grammar check runs in the background after upload — poll briefly while
  // we're waiting on it, rather than require a manual refresh. A live WS
  // push here (ai_report.check_completed, already emitted server-side) is
  // the natural next upgrade over polling.
  useEffect(() => {
    if (!submission || submission.status !== 'processing' || aiReports.length > 0) return;
    const interval = setInterval(reload, 4000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submission, aiReports]);

  async function handleResubmit(e: FormEvent) {
    e.preventDefault();
    if (!file || !id) return;
    setResubmitting(true);
    try {
      await api.resubmit(id, { original_filename: file.name, original_file_url: `placeholder://uploads/${file.name}` });
      reload();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Resubmit failed');
    } finally {
      setResubmitting(false);
    }
  }

  async function handleReviewSubmit(e: FormEvent) {
    e.preventDefault();
    if (!id) return;
    setReviewSubmitting(true);
    try {
      await api.submitReview(id, { recommendation, comments });
      setReviewSuccess(true);
      reload();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Review submission failed');
    } finally {
      setReviewSubmitting(false);
    }
  }

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  const myExistingReview = reviews.find((r) => r.reviewer_id === user.id);

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[900px] px-8 py-12">
        {error && <div role="alert" className="mb-6 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        {submission && (
          <>
            <div className="flex items-center gap-3">
              <h1 className="font-display-bold text-3xl">{submission.title}</h1>
              <StatusBadge status={submission.status} />
            </div>

            {decision && (
              <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Final Decision</h2>
                <p className="mt-2 font-extrabold capitalize">{decision.decision.replace('_', ' ')}</p>
                {decision.notes && <p className="mt-1 text-sm text-[var(--color-ink)]/60">{decision.notes}</p>}
              </div>
            )}

            <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
              <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Version History</h2>
              <ul className="mt-3 space-y-2">
                {history.map((v) => (
                  <li key={v.id} className="flex justify-between text-sm">
                    <span>v{v.version_number} — {v.original_filename}</span>
                  </li>
                ))}
              </ul>
            </div>

            {history.length > 0 && (
              <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Paper</h2>
                <PdfAnnotationViewer
                  versionId={history[history.length - 1].id}
                  canAnnotate={user.role === 'reviewer'}
                  currentUserId={user.id}
                />
              </div>
            )}

            <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
              <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">AI Feedback</h2>

              {submission.status === 'processing' && aiReports.length === 0 && (
                <p className="mt-3 text-sm text-[var(--color-ink)]/50">Checks are running…</p>
              )}

              {aiReports.length === 0 && submission.status !== 'processing' && (
                <p className="mt-3 text-sm text-[var(--color-ink)]/45">No checks have run yet.</p>
              )}

              {aiReports.map((report) => {
                if (report.check_type === 'grammar') {
                  return <GrammarReportCard key={report.id} report={report} />;
                }
                if (report.check_type === 'format') {
                  return <FormatReportCard key={report.id} report={report} />;
                }
                if (report.check_type === 'table_figure') {
                  return <TableFigureReportCard key={report.id} report={report} />;
                }
                return (
                  <div key={report.id} className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm">
                    <span className="font-bold capitalize">{report.check_type.replace('_', ' ')}</span> — {report.status}
                  </div>
                );
              })}
            </div>

            {user.role === 'researcher' && submission.status === 'revise_resubmit' && (
              <form onSubmit={handleResubmit} className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Resubmit</h2>
                <input
                  type="file" accept=".docx,.pdf" required
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="mt-3 w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                />
                <button
                  type="submit" disabled={resubmitting}
                  className="mt-4 bg-[var(--color-accent)] px-6 py-2.5 text-sm font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
                  style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
                >
                  {resubmitting ? 'Resubmitting…' : 'Resubmit'}
                </button>
              </form>
            )}

            {user.role === 'reviewer' && (
              <form onSubmit={handleReviewSubmit} className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">
                  {myExistingReview ? 'Update Your Review' : 'Submit Your Review'}
                </h2>
                {reviewSuccess && <div className="mt-3 border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">Review saved.</div>}
                <div className="mt-4">
                  <label className="mb-1.5 block text-sm font-medium">Recommendation</label>
                  <select
                    value={recommendation} onChange={(e) => setRecommendation(e.target.value)}
                    className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                  >
                    <option value="accept">Accept</option>
                    <option value="minor_revision">Minor Revision</option>
                    <option value="major_revision">Major Revision</option>
                    <option value="reject">Reject</option>
                  </select>
                </div>
                <div className="mt-4">
                  <label className="mb-1.5 block text-sm font-medium">Comments</label>
                  <textarea
                    value={comments} onChange={(e) => setComments(e.target.value)} rows={4}
                    className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                  />
                </div>
                <button
                  type="submit" disabled={reviewSubmitting}
                  className="mt-4 bg-[var(--color-accent)] px-6 py-2.5 text-sm font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
                  style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
                >
                  {reviewSubmitting ? 'Saving…' : 'Submit Review'}
                </button>
              </form>
            )}

            {(user.role === 'organizer' || user.role === 'platform_admin') && (
              <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">
                  Reviews ({reviews.length})
                </h2>
                <ul className="mt-3 space-y-3">
                  {reviews.map((r) => (
                    <li key={r.id} className="border-t border-[var(--color-line)] pt-3 text-sm">
                      <span className="font-bold capitalize">{r.recommendation.replace('_', ' ')}</span>
                      {r.comments && <p className="mt-1 text-[var(--color-ink)]/60">{r.comments}</p>}
                    </li>
                  ))}
                </ul>
                <DecisionForm submissionId={id} onDecided={reload} />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function DecisionForm({ submissionId, onDecided }: { submissionId: string; onDecided: () => void }) {
  const [decision, setDecision] = useState('accept');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.makeDecision(submissionId, { decision, notes });
      onDecided();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-5 border-t border-[var(--color-line)] pt-5">
      <h3 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Make Final Decision</h3>
      <select
        value={decision} onChange={(e) => setDecision(e.target.value)}
        className="mt-3 w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
      >
        <option value="accept">Accept</option>
        <option value="revise_resubmit">Revise & Resubmit</option>
        <option value="reject">Reject</option>
      </select>
      <textarea
        value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Notes for the researcher"
        className="mt-3 w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
      />
      <button
        type="submit" disabled={submitting}
        className="mt-3 bg-[var(--color-ink)] px-6 py-2.5 text-sm font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
        style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
      >
        {submitting ? 'Saving…' : 'Submit Decision'}
      </button>
    </form>
  );
}
