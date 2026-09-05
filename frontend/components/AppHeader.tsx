'use client';

import Image from 'next/image';
import { useAuth } from '@/lib/auth-context';
import type { User } from '@/lib/api';

const ROLE_LABEL: Record<string, string> = {
  researcher: 'Researcher',
  organizer: 'Organizer',
  reviewer: 'Reviewer',
  platform_admin: 'Platform Admin',
};

interface AppHeaderProps {
  // update51 — optional override so the admin dashboard (a separate,
  // sessionStorage-based identity — see admin-auth-context.tsx) can supply
  // its OWN user/logout instead of this component silently falling back to
  // the shared researcher/organizer/reviewer session, which would show the
  // wrong identity entirely (or nothing) on that page, and whose logout
  // button would act on the wrong session.
  user?: User | null;
  onLogout?: () => void;
}

export default function AppHeader({ user: userOverride, onLogout }: AppHeaderProps = {}) {
  const shared = useAuth();
  const user = userOverride !== undefined ? userOverride : shared.user;
  const logout = onLogout ?? shared.logout;

  return (
    <header className="border-b border-[var(--color-line)] bg-white">
      <div className="mx-auto flex max-w-[1360px] items-center justify-between px-8 py-3.5">
        <div className="flex items-center gap-2.5">
          <Image src="/images/logo.jpg" alt="GRMT" width={32} height={32} className="rounded-full" />
          <span className="font-display-bold text-lg">GRMT</span>
        </div>

        {user && (
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-sm font-bold leading-tight">{user.full_name}</div>
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-accent)]">
                {ROLE_LABEL[user.role] ?? user.role}
              </div>
            </div>
            <button
              onClick={logout}
              className="border border-[var(--color-line)] px-4 py-2 text-xs font-bold uppercase tracking-wide transition hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
            >
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
