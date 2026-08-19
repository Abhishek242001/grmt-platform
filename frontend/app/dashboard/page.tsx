"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

// master doc §6.1 / Figure 5 — one nav set per role. This starter codebase
// renders the nav shell and a placeholder body; each linked page is a real
// build task per the master doc §6 page specs (upload, AI report, gate
// config, review detail, admin panel, etc.) — not yet implemented here.
const NAV_BY_ROLE: Record<string, string[]> = {
  researcher: ["Dashboard", "Browse Conferences", "Submission Upload", "Submission History", "Profile"],
  reviewer: ["Assigned Papers", "Profile"],
  organizer: ["Onboarding", "Gate Rules", "Reviewer Management", "Submission Queue", "Analytics", "Decisions"],
  platform_admin: ["Model Usage", "False-Positive Rate", "Maintenance / Test Runs"],
};

export default function DashboardPage() {
  const { isAuthenticated, role, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !isAuthenticated) router.push("/login");
  }, [loading, isAuthenticated, router]);

  if (loading || !isAuthenticated || !role) {
    return <main className="min-h-screen flex items-center justify-center text-gray-400">Loading…</main>;
  }

  const navItems = NAV_BY_ROLE[role] ?? [];

  return (
    <main className="min-h-screen flex">
      <aside className="w-64 border-r border-gray-200 p-4 flex flex-col">
        <div className="font-semibold text-brand-primary mb-6">GRMT</div>
        <nav className="flex-1 space-y-1">
          {navItems.map((item) => (
            <div key={item} className="px-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-100 cursor-default">
              {item}
            </div>
          ))}
        </nav>
        <button onClick={logout} className="text-sm text-gray-500 hover:text-gray-800 text-left">
          Log out
        </button>
      </aside>
      <section className="flex-1 p-8">
        <h1 className="text-xl font-semibold mb-2">Welcome — role: {role}</h1>
        <p className="text-gray-500 text-sm max-w-lg">
          This is a placeholder dashboard body. Build out the pages listed in
          the sidebar per the master build document §6 (Frontend Page
          Specifications) — each has its own purpose, components, states, and
          API calls already specified there.
        </p>
      </section>
    </main>
  );
}
