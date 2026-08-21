'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';
import StatusBadge from '@/components/StatusBadge';

export default function SubmissionQueuePage() {
  const { id } = useParams<{ id: string }>();
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [submissions, setSubmissions] = useState<api.Submission[]>([]);
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
              <Link
                key={s.id}
                href={`/submissions/${s.id}`}
                className="flex items-center justify-between px-6 py-4 transition hover:bg-[var(--color-accent-soft)]"
              >
                <span className="font-medium">{s.title}</span>
                <StatusBadge status={s.status} />
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
