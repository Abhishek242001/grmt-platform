'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';

function MemberSection({
  title,
  description,
  members,
  onAdd,
  onRemove,
  emailPlaceholder,
}: {
  title: string;
  description: string;
  members: api.MemberRow[];
  onAdd: (email: string) => Promise<void>;
  onRemove: (rowId: string) => Promise<void>;
  emailPlaceholder: string;
}) {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onAdd(email);
      setEmail('');
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Failed to add');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="border border-[var(--color-line)] bg-white p-6">
      <h2 className="text-xl font-extrabold">{title}</h2>
      <p className="mt-1 text-sm text-[var(--color-ink)]/55">{description}</p>

      <form onSubmit={handleSubmit} className="mt-4 flex gap-3">
        {error && <div role="alert" className="w-full border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
      </form>
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="email" required placeholder={emailPlaceholder} value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="flex-1 border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
        />
        <button
          type="submit" disabled={submitting}
          className="bg-[var(--color-accent)] px-5 py-2.5 text-xs font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
          style={{ clipPath: 'polygon(4% 0, 100% 0, 96% 100%, 0 100%)' }}
        >
          {submitting ? 'Adding…' : 'Add'}
        </button>
      </form>

      <ul className="mt-5 divide-y divide-[var(--color-line)]">
        {members.length === 0 && <li className="py-3 text-sm text-[var(--color-ink)]/45">None yet.</li>}
        {members.map((m) => (
          <li key={m.id} className="flex items-center justify-between py-3">
            <div>
              <p className="text-sm font-bold">{m.full_name}</p>
              <p className="text-xs text-[var(--color-ink)]/50">{m.email}</p>
            </div>
            <button
              onClick={() => onRemove(m.id)}
              className="text-xs font-bold uppercase tracking-wide text-red-600 hover:underline"
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ManageMembersPage() {
  const { id } = useParams<{ id: string }>();
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [reviewers, setReviewers] = useState<api.MemberRow[]>([]);
  const [coAdmins, setCoAdmins] = useState<api.MemberRow[]>([]);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  function reload() {
    api.listReviewers(id).then(setReviewers).catch(() => {});
    api.listCoAdmins(id).then(setCoAdmins).catch(() => {});
  }

  useEffect(() => {
    if (!user || !id) return;
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, id]);

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[900px] px-8 py-12 space-y-8">
        <h1 className="font-display-bold text-4xl">Manage Team</h1>

        <MemberSection
          title="Reviewers"
          description="Must already have a reviewer account on GRMT."
          members={reviewers}
          emailPlaceholder="reviewer@example.com"
          onAdd={async (email) => {
            await api.addReviewer(id, email);
            reload();
          }}
          onRemove={async (rowId) => {
            await api.removeReviewer(id, rowId);
            reload();
          }}
        />

        <MemberSection
          title="Co-Admins"
          description="Must already have an organizer account. Co-admins get full management access to this conference."
          members={coAdmins}
          emailPlaceholder="coadmin@example.com"
          onAdd={async (email) => {
            await api.addCoAdmin(id, email);
            reload();
          }}
          onRemove={async (rowId) => {
            await api.removeCoAdmin(id, rowId);
            reload();
          }}
        />
      </main>
    </div>
  );
}
