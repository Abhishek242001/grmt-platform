'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { ApiError } from '@/lib/api';
import AuthBrandPanel from '@/components/AuthBrandPanel';

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login({ email, password });
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
          <h2 className="font-display-bold text-3xl">Log In</h2>
          <p className="mt-2 text-sm text-black/55">
            New here?{' '}
            <Link href="/signup" className="text-[var(--color-accent)] font-medium">
              Create an account
            </Link>
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5" noValidate>
            {error && (
              <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

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
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="password" className="block text-sm font-medium">
                  Password
                </label>
                <Link href="/forgot-password" className="text-xs text-[var(--color-accent)]">
                  Forgot password?
                </Link>
              </div>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm focus-visible:border-[var(--color-accent)]"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-[var(--color-accent)] py-3 text-sm font-extrabold uppercase tracking-wide text-white transition hover:bg-[var(--color-accent-dark)] disabled:opacity-50" style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
            >
              {isSubmitting ? 'Logging in…' : 'Log in'}
            </button>

            <button
              type="button"
              disabled
              title="Coming soon"
              className="w-full rounded-md border border-[var(--color-line)] py-2.5 text-sm font-medium text-black/40 cursor-not-allowed"
            >
              Continue with Google — Coming soon
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
