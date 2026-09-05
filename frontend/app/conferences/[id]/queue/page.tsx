'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';
import StatusBadge from '@/components/StatusBadge';

// update51 — per-submission reviewer assignment. Each row shows who's
// currently assigned and lets the organizer assign anyone from this
// conference's reviewer pool, or unassign them. A reviewer must be in the
// pool AND specifically assigned here before they can see or review a
// paper at all (see backend/app/routers/reviews.py's _require_assigned_reviewer).
function AssignmentControl({
  submissionId,
  pool,
}: {
  submissionId: string;
  pool: api.MemberRow[];
}) {
  const [assigned, setAssigned] = useState<api.ReviewerAssignment[]>([]);
  const [selectedReviewerId, setSelectedReviewerId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    api.listAssignedReviewers(submissionId).then(setAssigned).catch(() => {});
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submissionId]);

  const assignedIds = new Set(assigned.map((a) => a.reviewer_id));
  const available = pool.filter((p) => p.reviewer_id && !assignedIds.has(p.reviewer_id));

  async function handleAssign() {
    if (!selectedReviewerId) return;
    setBusy(true);
    setError(null);
    try {
      await api.assignReviewer(submissionId, selectedReviewerId);
      setSelectedReviewerId('');
      reload();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Could not assign reviewer');
    } finally {
      setBusy(false);
    }
  }

  async function handleUnassign(reviewerId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.unassignReviewer(submissionId, reviewerId);
      reload();
    } catch {
      setError('Could not unassign reviewer');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
      {assigned.length === 0 ? (
        <span className="text-[var(--color-ink)]/40">No reviewer assigned</span>
      ) : (
        assigned.map((a) => {
          const member = pool.find((p) => p.reviewer_id === a.reviewer_id);
          return (
            <span
              key={a.id}
              className="inline-flex items-center gap-1.5 border border-[var(--color-line)] bg-[var(--color-paper)] px-2 py-1"
            >
              {member?.full_name ?? a.reviewer_id}
              <button
                type="button"
                disabled={busy}
                onClick={(e) => { e.preventDefault(); handleUnassign(a.reviewer_id); }}
                className="text-[var(--color-ink)]/40 hover:text-red-600"
                aria-label="Unassign"
              >
                ×
              </button>
            </span>
          );
        })
      )}

      {available.length > 0 && (
        <span className="inline-flex items-center gap-1.5">
          <select
            value={selectedReviewerId}
            onClick={(e) => e.preventDefault()}
            onChange={(e) => setSelectedReviewerId(e.target.value)}
            className="border border-[var(--color-line)] bg-white px-1.5 py-1 text-xs"
          >
            <option value="">Assign reviewer…</option>
            {available.map((m) => (
              <option key={m.reviewer_id} value={m.reviewer_id}>{m.full_name}</option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !selectedReviewerId}
            onClick={(e) => { e.preventDefault(); handleAssign(); }}
            className="border border-[var(--color-line)] px-2 py-1 font-bold uppercase tracking-wide hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] disabled:opacity-40"
          >
            Assign
          </button>
        </span>
      )}

      {error && <span className="text-red-600">{error}</span>}
    </div>
  );
}

export default function SubmissionQueuePage() {
  const { id } = useParams<{ id: string }>();
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [submissions, setSubmissions] = useState<api.Submission[]>([]);
  const [reviewerPool, setReviewerPool] = useState<api.MemberRow[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  function reload() {
    api
      .conferenceQueue(id)
      .then(setSubmissions)
      .catch((e) => setError(e instanceof api.ApiError ? e.detail : 'Failed to load queue'))
      .finally(() => setLoadingList(false));
  }

  useEffect(() => {
    if (!user || !id) return;
    reload();
    if (user.role === 'organizer' || user.role === 'platform_admin') {
      api.listReviewers(id).then(setReviewerPool).catch(() => {});
    }
    // Simple polling refresh every 15s — a real live-push version of this page
    // is a natural next step, wiring in the WebSocket queue channel that's
    // already built and tested on the backend (conference:{id}:queue).
    const interval = setInterval(reload, 15000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, id]);

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  const canAssign = user.role === 'organizer' || user.role === 'platform_admin';

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[1360px] px-8 py-12">
        <h1 className="font-display-bold text-4xl">Submission Queue</h1>
        <p className="mt-2 text-[var(--color-ink)]/55">Refreshes automatically every 15 seconds.</p>

        {error && <div role="alert" className="mt-6 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        {loadingList ? (
          <p className="mt-8 text-sm text-[var(--color-ink)]/50">Loading…</p>
        ) : submissions.length === 0 ? (
          <p className="mt-8 text-sm text-[var(--color-ink)]/50">No submissions yet.</p>
        ) : (
          <div className="mt-8 divide-y divide-[var(--color-line)] border border-[var(--color-line)] bg-white">
            {submissions.map((s) => (
              <div key={s.id} className="px-6 py-4">
                <Link
                  href={`/submissions/${s.id}`}
                  className="flex items-center justify-between transition hover:text-[var(--color-accent)]"
                >
                  <span className="font-medium">{s.title}</span>
                  <StatusBadge status={s.status} />
                </Link>
                {canAssign && s.status !== 'ai_review_passed' && s.status !== 'processing' && s.status !== 'submitted' && (
                  <AssignmentControl submissionId={s.id} pool={reviewerPool} />
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
