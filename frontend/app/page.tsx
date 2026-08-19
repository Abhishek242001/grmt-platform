import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 text-center">
      <h1 className="text-3xl font-bold text-brand-primary mb-3">
        Gudsky Research Management Tool
      </h1>
      <p className="max-w-xl text-gray-600 mb-8">
        An AI pre-review layer between researchers and human reviewers —
        organizer-configurable gates, instant structured feedback, and a
        reviewer experience that spends its time on scientific judgment, not
        mechanical checks.
      </p>
      <div className="flex gap-4">
        <Link
          href="/login"
          className="px-5 py-2 rounded-md bg-brand-primary text-white font-medium hover:opacity-90"
        >
          Log in
        </Link>
        <Link
          href="/signup"
          className="px-5 py-2 rounded-md border border-brand-primary text-brand-primary font-medium hover:bg-brand-primary/5"
        >
          Sign up
        </Link>
      </div>
      <p className="mt-10 text-xs text-gray-400">
        Research &amp; development by Gudsky Research Foundation ·
        Product by GRMT Pvt. Ltd.
      </p>
    </main>
  );
}
