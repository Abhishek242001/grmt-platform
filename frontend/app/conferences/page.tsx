'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';

export default function BrowseConferencesPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const [conferences, setConferences] = useState<api.Conference[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!user) return;
    api
      .listConferences()
      .then(setConferences)
      .catch((e) => setError(e instanceof api.ApiError ? e.detail : 'Failed to load conferences'))
      .finally(() => setLoadingList(false));
  }, [user]);

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  const canCreate = user.role === 'organizer' || user.role === 'platform_admin';

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[1360px] px-8 py-12">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display-bold text-4xl">Browse Conferences</h1>
            <p className="mt-2 text-[var(--color-ink)]/55">Find a conference matching your field and submit your paper.</p>
          </div>
          {canCreate && (
            <Link href="/conferences/new">
              <button
                className="bg-[var(--color-accent)] px-6 py-3 text-sm font-extrabold uppercase tracking-wide text-white transition hover:bg-[var(--color-accent-dark)]"
                style={{ clipPath: 'polygon(4% 0, 100% 0, 96% 100%, 0 100%)' }}
              >
                Create Conference
              </button>
            </Link>
          )}
        </div>

        {error && <div className="mt-6 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        {loadingList ? (
          <p className="mt-8 text-sm text-[var(--color-ink)]/50">Loading conferences…</p>
        ) : conferences.length === 0 ? (
          <p className="mt-8 text-sm text-[var(--color-ink)]/50">
            No conferences yet.{canCreate ? ' Create the first one.' : ' Check back soon.'}
          </p>
        ) : (
          <div className="mt-8 grid grid-cols-1 gap-px bg-[var(--color-line)] md:grid-cols-3">
            {conferences.map((c) => {
              const isOwner = c.organizer_id === user.id;
              return (
                <div key={c.id} className="bg-white px-6 py-7 transition hover:bg-[var(--color-accent-soft)]">
                  <Link href={`/conferences/${c.id}`} className="block">
                    <span className="inline-block border border-[var(--color-line)] bg-[var(--color-paper)] px-2.5 py-1 text-[0.68rem] font-extrabold uppercase tracking-wide">
                      {c.publisher_format}
                    </span>
                    <h3 className="mt-3 text-xl font-extrabold">{c.name}</h3>
                    {c.description && (
                      <p className="mt-1.5 text-sm text-[var(--color-ink)]/55 line-clamp-2">{c.description}</p>
                    )}
                  </Link>
                  {isOwner && (
                    <Link
                      href={`/conferences/${c.id}/queue`}
                      className="mt-3 inline-block text-xs font-bold uppercase tracking-wide text-[var(--color-accent)] hover:underline"
                    >
                      Manage →
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
