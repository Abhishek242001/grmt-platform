'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';
import StatusBadge from '@/components/StatusBadge';

export default function MySubmissionsPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const [submissions, setSubmissions] = useState<api.Submission[]>([]);
  const [loadingList, setLoadingList] = useState(true);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!user) return;
    const fetcher = user.role === 'reviewer' ? api.assignedSubmissions : api.mysubmissions;
    fetcher().then(setSubmissions).finally(() => setLoadingList(false));
  }, [user]);

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  const title = user.role === 'reviewer' ? 'Assigned Papers' : 'Submission History';

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[1360px] px-8 py-12">
        <h1 className="font-display-bold text-4xl">{title}</h1>

        {loadingList ? (
          <p className="mt-8 text-sm text-[var(--color-ink)]/50">Loading…</p>
        ) : submissions.length === 0 ? (
          <p className="mt-8 text-sm text-[var(--color-ink)]/50">Nothing here yet.</p>
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
