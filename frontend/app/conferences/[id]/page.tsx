'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';

const MANAGE_LINKS = [
  { href: 'queue', label: 'Submission Queue' },
  { href: 'gate-rules', label: 'Gate Rules' },
  { href: 'manage', label: 'Reviewers & Co-Admins' },
  { href: 'analytics', label: 'Analytics' },
];

export default function ConferenceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [conference, setConference] = useState<api.Conference | null>(null);
  const [title, setTitle] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!user || !id) return;
    api.getConference(id).then(setConference).catch(() => setError('Conference not found'));
  }, [user, id]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError('Please select a .docx file');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await api.createSubmission({
        conference_id: id,
        title,
        original_filename: file.name,
        original_file_url: `placeholder://uploads/${file.name}`,
      });
      setSuccess(true);
      setTimeout(() => router.push('/submissions'), 1200);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  const isOwner = conference && conference.organizer_id === user.id;

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[900px] px-8 py-12">
        {conference && (
          <>
            <span className="inline-block border border-[var(--color-line)] bg-white px-2.5 py-1 text-[0.68rem] font-extrabold uppercase tracking-wide">
              {conference.publisher_format}
            </span>
            <h1 className="font-display-bold mt-3 text-4xl">{conference.name}</h1>
            {conference.description && (
              <p className="mt-2 text-[var(--color-ink)]/55">{conference.description}</p>
            )}
          </>
        )}

        {isOwner && (
          <div className="mt-8 border border-[var(--color-accent)] bg-[var(--color-accent-soft)] p-6">
            <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-accent)]">
              You organize this conference
            </h2>
            <div className="mt-3 flex flex-wrap gap-3">
              {MANAGE_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={`/conferences/${id}/${link.href}`}
                  className="border border-[var(--color-accent)] bg-white px-4 py-2 text-xs font-bold uppercase tracking-wide text-[var(--color-accent)] transition hover:bg-[var(--color-accent)] hover:text-white"
                >
                  {link.label}
                </Link>
              ))}
            </div>
          </div>
        )}

        {user.role === 'researcher' && conference && (
          <div className="mt-10 border border-[var(--color-line)] bg-white p-8">
            <h2 className="text-xl font-extrabold">Submit Your Paper</h2>
            <p className="mt-1 text-sm text-[var(--color-ink)]/55">Word (.docx) only — PDF is not accepted.</p>

            <form onSubmit={handleSubmit} className="mt-6 space-y-5" noValidate>
              {error && <div role="alert" className="border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
              {success && <div className="border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">Submitted! Redirecting…</div>}

              <div>
                <label htmlFor="title" className="mb-1.5 block text-sm font-medium">Paper title</label>
                <input
                  id="title" type="text" required value={title} onChange={(e) => setTitle(e.target.value)}
                  className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm focus-visible:border-[var(--color-accent)]"
                />
              </div>

              <div>
                <label htmlFor="file" className="mb-1.5 block text-sm font-medium">Manuscript file</label>
                <input
                  id="file" type="file" accept=".docx" required
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                />
              </div>

              <button
                type="submit" disabled={submitting}
                className="bg-[var(--color-accent)] px-8 py-3 text-sm font-extrabold uppercase tracking-wide text-white transition hover:bg-[var(--color-accent-dark)] disabled:opacity-50"
                style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
              >
                {submitting ? 'Submitting…' : 'Submit Paper'}
              </button>
            </form>
          </div>
        )}
      </main>
    </div>
  );
}
