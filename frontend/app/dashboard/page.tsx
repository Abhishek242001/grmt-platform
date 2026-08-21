'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import AppHeader from '@/components/AppHeader';
import ComingSoon from '@/components/ComingSoon';

interface LinkCard {
  title: string;
  description: string;
  href: string;
}
interface StubCard {
  title: string;
  description: string;
}

const RESEARCHER_LINKS: LinkCard[] = [
  { title: 'Browse Conferences', description: 'Find and submit to open conferences matching your field.', href: '/conferences' },
  { title: 'Submission History', description: 'Track every paper you have submitted, across all conferences.', href: '/submissions' },
];
const RESEARCHER_CARDS: StubCard[] = [
  { title: 'Profile & Settings', description: 'Update your name, email preferences, and account details.' },
];

const ORGANIZER_CARDS: StubCard[] = [
  { title: 'Submission Queue', description: 'A live view of every paper submitted to your conference.' },
  { title: 'Reviewer Management', description: 'Invite, assign, and manage your reviewer pool.' },
  { title: 'Analytics Dashboard', description: 'Gate pass/fail rates and check performance across your conference.' },
];

const REVIEWER_LINKS: LinkCard[] = [
  { title: 'Assigned Papers', description: 'Papers waiting on your review, sorted by deadline.', href: '/submissions' },
];
const REVIEWER_CARDS: StubCard[] = [
  { title: 'Review History', description: 'Decisions you have already submitted.' },
];

const ADMIN_CARDS: StubCard[] = [
  { title: 'Model Usage Dashboard', description: 'Live performance and usage stats across all 6 AI models.' },
  { title: 'False-Positive Tracking', description: 'Monitor and tune AI check accuracy over time.' },
];

const LINKS_BY_ROLE: Record<string, LinkCard[]> = {
  researcher: RESEARCHER_LINKS,
  reviewer: REVIEWER_LINKS,
};
const CARDS_BY_ROLE: Record<string, StubCard[]> = {
  researcher: RESEARCHER_CARDS,
  organizer: ORGANIZER_CARDS,
  reviewer: REVIEWER_CARDS,
  platform_admin: ADMIN_CARDS,
};

function LinkCardTile({ card }: { card: LinkCard }) {
  return (
    <Link
      href={card.href}
      className="block border border-[var(--color-line)] bg-white px-6 py-8 text-center transition hover:bg-[var(--color-accent-soft)]"
    >
      <span className="inline-block bg-[var(--color-accent-soft)] px-2.5 py-1 text-[0.68rem] font-extrabold uppercase tracking-wide text-[var(--color-accent)]">
        Open
      </span>
      <h3 className="mt-3 text-lg font-extrabold">{card.title}</h3>
      <p className="mx-auto mt-1.5 max-w-[32ch] text-sm text-[var(--color-ink)]/55">{card.description}</p>
    </Link>
  );
}

export default function DashboardPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">
        Loading…
      </div>
    );
  }

  const links = LINKS_BY_ROLE[user.role] ?? [];
  const stubs = CARDS_BY_ROLE[user.role] ?? [];

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />

      <main className="mx-auto max-w-[1360px] px-8 py-12">
        <h1 className="font-display-bold text-4xl">
          Welcome back, {user.full_name.split(' ')[0]}.
        </h1>
        <p className="mt-2 text-[var(--color-ink)]/55">
          Phase 1 has your account, conferences, submissions, and reviews fully working —
          the panels marked &quot;Coming Soon&quot; light up as the rest ships.
        </p>

        <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
          {links.map((card) => (
            <LinkCardTile key={card.title} card={card} />
          ))}
          {stubs.map((card) => (
            <ComingSoon key={card.title} title={card.title} description={card.description} />
          ))}
        </div>
      </main>
    </div>
  );
}
