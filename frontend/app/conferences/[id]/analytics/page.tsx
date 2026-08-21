'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';

export default function AnalyticsPage() {
  const { id } = useParams<{ id: string }>();
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [data, setData] = useState<api.ConferenceAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!user || !id) return;
    api
      .getAnalytics(id)
      .then(setData)
      .catch((e) => setError(e instanceof api.ApiError ? e.detail : 'Failed to load analytics'));
  }, [user, id]);

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[1360px] px-8 py-12">
        <h1 className="font-display-bold text-4xl">Analytics</h1>

        {error && <div role="alert" className="mt-6 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        {data && (
          <>
            <div className="mt-8 grid grid-cols-2 gap-px border border-[var(--color-line)] bg-[var(--color-line)] md:grid-cols-4">
              {[
                ['Total Submissions', data.total_submissions],
                ['Reviews Submitted', data.total_reviews_submitted],
                ['Decisions Made', data.total_decisions_made],
                ['Avg Reviews / Submission', data.average_reviews_per_submission],
              ].map(([label, value]) => (
                <div key={label as string} className="bg-white px-6 py-8 text-center">
                  <div className="font-display-bold text-4xl text-[var(--color-accent)]">{value}</div>
                  <div className="mt-1 text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/55">{label}</div>
                </div>
              ))}
            </div>

            <div className="mt-8 border border-[var(--color-line)] bg-white p-6">
              <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Submissions by Status</h2>
              <ul className="mt-4 space-y-2">
                {Object.entries(data.submissions_by_status).map(([status, count]) => (
                  <li key={status} className="flex justify-between border-b border-[var(--color-line)] py-2 text-sm">
                    <span className="capitalize">{status.replace(/_/g, ' ')}</span>
                    <span className="font-bold">{count}</span>
                  </li>
                ))}
                {Object.keys(data.submissions_by_status).length === 0 && (
                  <li className="py-2 text-sm text-[var(--color-ink)]/45">No submissions yet.</li>
                )}
              </ul>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
