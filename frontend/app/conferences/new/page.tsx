'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';

export default function NewConferencePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [publisherFormat, setPublisherFormat] = useState('ieee');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!isLoading && user && user.role !== 'organizer' && user.role !== 'platform_admin') {
      router.push('/dashboard');
    }
  }, [isLoading, user, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const conf = await api.createConference({
        name,
        description: description || undefined,
        publisher_format: publisherFormat,
      });
      router.push(`/conferences/${conf.id}`);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Failed to create conference');
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[700px] px-8 py-12">
        <h1 className="font-display-bold text-4xl">Create a Conference</h1>
        <p className="mt-2 text-[var(--color-ink)]/55">
          You&apos;ll be able to configure gate rules, invite reviewers, and manage submissions once it&apos;s created.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5 border border-[var(--color-line)] bg-white p-8" noValidate>
          {error && <div role="alert" className="border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

          <div>
            <label htmlFor="name" className="mb-1.5 block text-sm font-medium">Conference name</label>
            <input
              id="name" type="text" required value={name} onChange={(e) => setName(e.target.value)}
              placeholder="e.g. ICSE 2027"
              className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm focus-visible:border-[var(--color-accent)]"
            />
          </div>

          <div>
            <label htmlFor="description" className="mb-1.5 block text-sm font-medium">Description (optional)</label>
            <textarea
              id="description" value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
              className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm focus-visible:border-[var(--color-accent)]"
            />
          </div>

          <div>
            <label htmlFor="format" className="mb-1.5 block text-sm font-medium">Publisher format</label>
            <select
              id="format" value={publisherFormat} onChange={(e) => setPublisherFormat(e.target.value)}
              className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
            >
              <option value="ieee">IEEE</option>
              <option value="springer">Springer</option>
            </select>
          </div>

          <button
            type="submit" disabled={submitting}
            className="bg-[var(--color-accent)] px-8 py-3 text-sm font-extrabold uppercase tracking-wide text-white transition hover:bg-[var(--color-accent-dark)] disabled:opacity-50"
            style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
          >
            {submitting ? 'Creating…' : 'Create Conference'}
          </button>
        </form>
      </main>
    </div>
  );
}
