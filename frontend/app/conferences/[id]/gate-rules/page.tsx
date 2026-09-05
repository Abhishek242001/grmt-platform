'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';

const CHECK_TYPES: { value: string; label: string; lockedSoft: boolean }[] = [
  { value: 'grammar', label: 'Grammar', lockedSoft: false },
  { value: 'citation', label: 'Citation Completeness', lockedSoft: false },
  { value: 'format', label: 'Publisher Format Compliance', lockedSoft: false },
  { value: 'plagiarism', label: 'Plagiarism / Similarity', lockedSoft: true },
  { value: 'ai_text', label: 'AI-Generated Text Detection', lockedSoft: true },
  { value: 'table_figure', label: 'Table / Figure Consistency', lockedSoft: false },
  { value: 'logical_consistency', label: 'Logical Consistency', lockedSoft: false },
];

interface RuleState {
  is_hard_gate: boolean;
  threshold: string;
}

export default function GateRulesPage() {
  const { id } = useParams<{ id: string }>();
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [rules, setRules] = useState<Record<string, RuleState>>(
    Object.fromEntries(CHECK_TYPES.map((c) => [c.value, { is_hard_gate: false, threshold: '' }]))
  );
  const [loadingRules, setLoadingRules] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!user || !id) return;
    api
      .getGateRules(id)
      .then((existing) => {
        setRules((prev) => {
          const next = { ...prev };
          for (const r of existing) {
            next[r.check_type] = {
              is_hard_gate: r.is_hard_gate,
              threshold: r.threshold != null ? String(r.threshold) : '',
            };
          }
          return next;
        });
      })
      .catch((e) => setError(e instanceof api.ApiError ? e.detail : 'Failed to load gate rules'))
      .finally(() => setLoadingRules(false));
  }, [user, id]);

  function updateRule(checkType: string, patch: Partial<RuleState>) {
    setRules((prev) => ({ ...prev, [checkType]: { ...prev[checkType], ...patch } }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const payload = CHECK_TYPES.map((c) => ({
        check_type: c.value,
        is_hard_gate: rules[c.value].is_hard_gate,
        threshold: rules[c.value].threshold === '' ? null : Number(rules[c.value].threshold),
      }));
      await api.updateGateRules(id, payload);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Failed to save gate rules');
    } finally {
      setSaving(false);
    }
  }

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[900px] px-8 py-12">
        <h1 className="font-display-bold text-4xl">Gate Rule Configuration</h1>
        <p className="mt-2 text-[var(--color-ink)]/55">
          Decide which checks auto-reject a submission (hard gate) versus flag it for human review (soft gate).
          Plagiarism and AI-text detection can never be a hard gate — this is enforced by the platform, not just this form.
        </p>

        {error && <div role="alert" className="mt-6 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        {success && <div className="mt-6 border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">Gate rules saved.</div>}

        {loadingRules ? (
          <p className="mt-8 text-sm text-[var(--color-ink)]/50">Loading…</p>
        ) : (
          <div className="mt-8 divide-y divide-[var(--color-line)] border border-[var(--color-line)] bg-white">
            {CHECK_TYPES.map((c) => {
              const state = rules[c.value];
              return (
                <div key={c.value} className="flex items-center justify-between gap-6 px-6 py-5">
                  <div>
                    <p className="font-bold">{c.label}</p>
                    {c.lockedSoft && (
                      <p className="mt-0.5 text-xs text-[var(--color-ink)]/45">Soft flag only — cannot be a hard gate</p>
                    )}
                  </div>

                  <div className="flex items-center gap-4">
                    <input
                      type="number" placeholder="Threshold" value={state.threshold}
                      onChange={(e) => updateRule(c.value, { threshold: e.target.value })}
                      className="w-28 border border-[var(--color-line)] bg-white px-3 py-2 text-sm"
                    />
                    <label className="flex items-center gap-2 text-sm font-semibold">
                      <input
                        type="checkbox"
                        checked={state.is_hard_gate}
                        disabled={c.lockedSoft}
                        onChange={(e) => updateRule(c.value, { is_hard_gate: e.target.checked })}
                        className="h-4 w-4"
                      />
                      Hard gate
                    </label>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <button
          onClick={handleSave} disabled={saving || loadingRules}
          className="mt-6 bg-[var(--color-accent)] px-8 py-3 text-sm font-extrabold uppercase tracking-wide text-white transition hover:bg-[var(--color-accent-dark)] disabled:opacity-50"
          style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
        >
          {saving ? 'Saving…' : 'Save Gate Rules'}
        </button>
      </main>
    </div>
  );
}
