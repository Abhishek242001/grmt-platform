'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { ApiError } from '@/lib/api';
import AuthBrandPanel from '@/components/AuthBrandPanel';

type SelfAssignableRole = 'researcher' | 'organizer' | 'reviewer';

const ROLE_OPTIONS: { value: SelfAssignableRole; label: string; blurb: string }[] = [
  { value: 'researcher', label: 'Researcher', blurb: 'Submit papers, get instant AI feedback' },
  { value: 'organizer', label: 'Organizer', blurb: 'Run a conference, configure review gates' },
  { value: 'reviewer', label: 'Reviewer', blurb: 'Review assigned papers' },
];

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<SelfAssignableRole>('researcher');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await signup({ email, password, full_name: fullName, role });
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Something went wrong. Try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      <AuthBrandPanel />

      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-sm">
          <h2 className="font-display-bold text-3xl">Create Your Account</h2>
          <p className="mt-2 text-sm text-black/55">
            Already have one?{' '}
            <Link href="/login" className="text-[var(--color-accent)] font-medium">
              Log in
            </Link>
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5" noValidate>
            {error && (
              <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <fieldset>
              <legend className="block text-sm font-medium mb-2">I am a…</legend>
              <div className="grid grid-cols-3 gap-2">
                {ROLE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setRole(opt.value)}
                    aria-pressed={role === opt.value}
                    className={`rounded-md border px-2 py-2.5 text-left text-xs transition ${
                      role === opt.value
                        ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]'
                        : 'border-[var(--color-line)] hover:border-black/30'
                    }`}
                  >
                    <span className="block font-medium">{opt.label}</span>
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-xs text-black/45">
                {ROLE_OPTIONS.find((o) => o.value === role)?.blurb}
              </p>
            </fieldset>

            <div>
              <label htmlFor="fullName" className="block text-sm font-medium mb-1.5">
                Full name
              </label>
              <input
                id="fullName"
                type="text"
                required
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full rounded-md border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm focus-visible:border-[var(--color-accent)]"
                placeholder="Ada Lovelace"
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-sm font-medium mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm focus-visible:border-[var(--color-accent)]"
                placeholder="you@university.edu"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm focus-visible:border-[var(--color-accent)]"
                placeholder="At least 8 characters, a letter and a number"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-[var(--color-accent)] py-3 text-sm font-extrabold uppercase tracking-wide text-white transition hover:bg-[var(--color-accent-dark)] disabled:opacity-50" style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
            >
              {isSubmitting ? 'Creating account…' : 'Create account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
