import Image from 'next/image';
import Link from 'next/link';

const NAV_LINKS = [
  { href: '#audience', label: "Who It's For" },
  { href: '#engine', label: 'The AI Layer' },
  { href: '#trust', label: 'Trust & Policy' },
];

export default function MarketingNav() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-[var(--color-line)] bg-white/90 backdrop-blur">
      <nav className="mx-auto flex max-w-[1360px] items-center justify-between px-8 py-3.5">
        <div className="flex items-center gap-2.5">
          <Image
            src="/images/logo.jpg"
            alt="Gudsky Research Foundation"
            width={36}
            height={36}
            className="rounded-full"
          />
          <span className="font-display-bold text-xl">GRMT</span>
        </div>

        <div className="hidden gap-8 text-sm font-semibold md:flex">
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href} className="transition hover:text-[var(--color-accent)]">
              {link.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm font-bold transition hover:text-[var(--color-accent)]">
            Log in
          </Link>
          <Link href="/signup">
            <button
              className="bg-[var(--color-accent)] px-5 py-2.5 text-xs font-extrabold uppercase tracking-wide text-white transition hover:bg-[var(--color-accent-dark)]"
              style={{ clipPath: 'polygon(6% 0, 100% 0, 94% 100%, 0 100%)' }}
            >
              Get Started
            </button>
          </Link>
        </div>
      </nav>
    </header>
  );
}
