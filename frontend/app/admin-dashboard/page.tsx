'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { useAdminAuth } from '@/lib/admin-auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';

const METRICS_HISTORY_LENGTH = 60; // 60 ticks at 2s/tick = 2 minutes of live history on screen

interface MetricPoint {
  t: string; // formatted HH:MM:SS for chart x-axis labels
  cpu: number;
  mem: number;
  gpu: number | null;
  netSent: number;
  netRecv: number;
}

function StatTile({ label, value, unit }: { label: string; value: string | number; unit?: string }) {
  return (
    <div className="border border-[var(--color-line)] bg-white px-4 py-3.5">
      <div className="text-[0.68rem] font-semibold uppercase tracking-wide text-[var(--color-ink)]/50">{label}</div>
      <div className="mt-1 font-display-bold text-2xl">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-[var(--color-ink)]/50">{unit}</span>}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const { user, accessToken, isLoading, logout } = useAdminAuth();
  const router = useRouter();

  const [metrics, setMetrics] = useState<api.SystemMetrics | null>(null);
  const [history, setHistory] = useState<MetricPoint[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  const [providers, setProviders] = useState<api.ApiProviderStatus[]>([]);
  const [usage, setUsage] = useState<api.ApiUsageSummary | null>(null);
  const [gptzeroKeyInput, setGptzeroKeyInput] = useState('');
  const [winstonKeyInput, setWinstonKeyInput] = useState('');
  const [savingProvider, setSavingProvider] = useState<string | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);

  // Access gate — redirects to /admin (the dedicated admin login, not the
  // shared /login) since a platform_admin account isn't meant to be
  // reachable through the regular researcher/organizer/reviewer login flow.
  useEffect(() => {
    if (isLoading) return;
    if (!user || user.role !== 'platform_admin') {
      router.push('/admin');
    }
  }, [user, isLoading, router]);

  function reloadProvidersAndUsage() {
    if (!accessToken) return;
    api.getApiProviders(accessToken).then(setProviders).catch(() => {});
    api.getApiUsage(accessToken).then(setUsage).catch(() => {});
  }

  useEffect(() => {
    if (!user || user.role !== 'platform_admin') return;
    reloadProvidersAndUsage();
    // Usage stats aren't pushed live over WS (unlike hardware metrics) —
    // a real request could land between polls, so refresh on a plain
    // interval rather than requiring a manual page reload to see updated
    // counts.
    const interval = setInterval(reloadProvidersAndUsage, 15000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, accessToken]);

  // Real-time hardware metrics via the admin:system-metrics WS channel —
  // same subscribe pattern already used on the submission detail page
  // (api.getWsTicket() -> ticket-authenticated WS -> subscribe to a
  // specific channel), just pointed at a different channel.
  const historyRef = useRef<MetricPoint[]>([]);
  useEffect(() => {
    if (!user || user.role !== 'platform_admin' || !accessToken) return;

    let socket: WebSocket | null = null;
    let cancelled = false;

    api.getWsTicket(accessToken).then(({ ticket }) => {
      if (cancelled) return;
      const wsBase = process.env.NEXT_PUBLIC_WS_BASE_URL || '/api/ws';
      socket = new WebSocket(`${wsBase}?ticket=${ticket}`);

      socket.onopen = () => {
        socket?.send(JSON.stringify({ action: 'subscribe', channel: 'admin:system-metrics' }));
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'subscribed') {
            setWsConnected(true);
            return;
          }
          if (msg.type === 'system_metrics') {
            const data: api.SystemMetrics = msg.data;
            setMetrics(data);
            const point: MetricPoint = {
              t: new Date(data.timestamp * 1000).toLocaleTimeString(),
              cpu: data.cpu_utilization_pct,
              mem: data.memory_used_pct,
              gpu: data.gpu_utilization_pct,
              netSent: data.network_sent_mb_s,
              netRecv: data.network_recv_mb_s,
            };
            const next = [...historyRef.current, point].slice(-METRICS_HISTORY_LENGTH);
            historyRef.current = next;
            setHistory(next);
          }
        } catch {
          // malformed frame — ignore rather than crash the dashboard over a bad push
        }
      };

      socket.onclose = () => setWsConnected(false);
      socket.onerror = () => setWsConnected(false);
    }).catch(() => setWsConnected(false));

    return () => {
      cancelled = true;
      socket?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, accessToken]);

  async function handleSetKey(provider: 'gptzero' | 'winston', e: FormEvent) {
    e.preventDefault();
    const key = provider === 'gptzero' ? gptzeroKeyInput : winstonKeyInput;
    if (!key.trim() || !accessToken) return;
    setSavingProvider(provider);
    setProviderError(null);
    try {
      await api.setApiKey(provider, key.trim(), accessToken);
      if (provider === 'gptzero') setGptzeroKeyInput('');
      else setWinstonKeyInput('');
      reloadProvidersAndUsage();
    } catch (err) {
      setProviderError(err instanceof api.ApiError ? err.detail : 'Could not save the key. Try again.');
    } finally {
      setSavingProvider(null);
    }
  }

  async function handleActivate(provider: 'gptzero' | 'winston') {
    if (!accessToken) return;
    setSavingProvider(provider);
    setProviderError(null);
    try {
      const updated = await api.activateApiProvider(provider, accessToken);
      setProviders(updated);
    } catch (err) {
      setProviderError(err instanceof api.ApiError ? err.detail : 'Could not activate this provider.');
    } finally {
      setSavingProvider(null);
    }
  }

  if (isLoading || !user || user.role !== 'platform_admin') {
    return null; // redirect is already in flight via the effect above
  }

  const gptzero = providers.find((p) => p.provider === 'gptzero');
  const winston = providers.find((p) => p.provider === 'winston');

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader user={user} onLogout={logout} />

      <main className="mx-auto max-w-[1360px] px-8 py-10">
        <div className="flex items-center justify-between">
          <h1 className="font-display-bold text-3xl">Admin Panel</h1>
          <span
            className={`inline-flex items-center gap-1.5 border px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-wide ${
              wsConnected
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-[var(--color-line)] bg-[var(--color-accent-soft)] text-[var(--color-ink)]/50'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${wsConnected ? 'bg-emerald-500' : 'bg-[var(--color-ink)]/30'}`} />
            {wsConnected ? 'Live' : 'Connecting…'}
          </span>
        </div>

        {/* ── Real-time hardware resource monitoring ── */}
        <section className="mt-8">
          <h2 className="font-display-bold text-xl">System Resources</h2>
          <p className="mt-1 text-sm text-[var(--color-ink)]/55">
            Live readings from this Studio instance, refreshed every 2 seconds.
          </p>

          {!metrics ? (
            <p className="mt-4 text-sm text-[var(--color-ink)]/50">Waiting for the first reading…</p>
          ) : (
            <>
              <div className="mt-4 grid grid-cols-2 gap-px bg-[var(--color-line)] sm:grid-cols-3 lg:grid-cols-5">
                <StatTile label="CPU" value={metrics.cpu_utilization_pct.toFixed(1)} unit="%" />
                <StatTile label="CPU Cores" value={metrics.cpu_core_count} />
                <StatTile label="Memory" value={metrics.memory_used_pct.toFixed(1)} unit="%" />
                <StatTile label="Memory Used" value={`${metrics.memory_used_gb} / ${metrics.memory_total_gb}`} unit="GB" />
                <StatTile label="Swap" value={metrics.swap_used_pct.toFixed(1)} unit="%" />
                <StatTile label="Disk Used" value={metrics.disk_used_pct.toFixed(1)} unit="%" />
                <StatTile label="Disk I/O Read" value={metrics.disk_read_mb_s} unit="MB/s" />
                <StatTile label="Disk I/O Write" value={metrics.disk_write_mb_s} unit="MB/s" />
                <StatTile label="Network Sent" value={metrics.network_sent_mb_s} unit="MB/s" />
                <StatTile label="Network Recv" value={metrics.network_recv_mb_s} unit="MB/s" />
                <StatTile label="Load Avg (1m)" value={metrics.load_average_1m} />
                <StatTile label="Load Avg (5m)" value={metrics.load_average_5m} />
                <StatTile label="Processes" value={metrics.process_count} />
                <StatTile label="Uptime" value={Math.floor(metrics.uptime_seconds / 3600)} unit="h" />
                <StatTile
                  label="GPU Utilization"
                  value={metrics.gpu_utilization_pct !== null ? metrics.gpu_utilization_pct.toFixed(1) : 'No GPU'}
                  unit={metrics.gpu_utilization_pct !== null ? '%' : undefined}
                />
                {metrics.gpu_memory_used_mb !== null && (
                  <StatTile
                    label="GPU Memory"
                    value={`${Math.round(metrics.gpu_memory_used_mb)} / ${Math.round(metrics.gpu_memory_total_mb ?? 0)}`}
                    unit="MB"
                  />
                )}
                {metrics.gpu_temperature_c !== null && (
                  <StatTile label="GPU Temp" value={metrics.gpu_temperature_c} unit="°C" />
                )}
              </div>

              <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div className="border border-[var(--color-line)] bg-white p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink)]/50">
                    CPU / Memory / GPU — last 2 minutes
                  </div>
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={history}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                      <XAxis dataKey="t" tick={{ fontSize: 10 }} minTickGap={30} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} unit="%" />
                      <Tooltip />
                      <Line type="monotone" dataKey="cpu" name="CPU %" stroke="var(--color-accent)" dot={false} strokeWidth={2} />
                      <Line type="monotone" dataKey="mem" name="Memory %" stroke="#5c8dff" dot={false} strokeWidth={2} />
                      <Line type="monotone" dataKey="gpu" name="GPU %" stroke="#0d2f86" dot={false} strokeWidth={2} connectNulls={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="border border-[var(--color-line)] bg-white p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink)]/50">
                    Network throughput — last 2 minutes
                  </div>
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={history}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                      <XAxis dataKey="t" tick={{ fontSize: 10 }} minTickGap={30} />
                      <YAxis tick={{ fontSize: 10 }} unit=" MB/s" />
                      <Tooltip />
                      <Line type="monotone" dataKey="netSent" name="Sent" stroke="var(--color-accent)" dot={false} strokeWidth={2} />
                      <Line type="monotone" dataKey="netRecv" name="Received" stroke="#5c8dff" dot={false} strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </>
          )}
        </section>

        {/* ── Plagiarism-provider API keys ── */}
        <section className="mt-12">
          <h2 className="font-display-bold text-xl">Plagiarism Detection Providers</h2>
          <p className="mt-1 text-sm text-[var(--color-ink)]/55">
            Only one provider is used at a time. Activating a provider automatically deactivates the other.
          </p>

          {providerError && (
            <div role="alert" className="mt-4 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {providerError}
            </div>
          )}

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* GPTZero */}
            <div className="border border-[var(--color-line)] bg-white p-5">
              <div className="flex items-center justify-between">
                <h3 className="font-display-bold text-lg">GPTZero</h3>
                {gptzero?.is_active && (
                  <span className="border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-emerald-700">
                    Active
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-[var(--color-ink)]/50">
                Free tier now (10,000 words/month) — upgradeable to a paid plan later.
              </p>
              <div className="mt-3 text-sm">
                Status:{' '}
                {gptzero?.is_configured ? (
                  <span className="text-[var(--color-ink)]/70">key configured{gptzero.masked_key ? ` (${gptzero.masked_key})` : ''}</span>
                ) : (
                  <span className="text-[var(--color-ink)]/50">no key set</span>
                )}
              </div>
              <form onSubmit={(e) => handleSetKey('gptzero', e)} className="mt-3 flex gap-2">
                <input
                  type="password"
                  placeholder="GPTZero API key"
                  value={gptzeroKeyInput}
                  onChange={(e) => setGptzeroKeyInput(e.target.value)}
                  className="min-w-0 flex-1 border border-[var(--color-line)] px-3 py-2 text-sm"
                />
                <button
                  type="submit"
                  disabled={savingProvider === 'gptzero'}
                  className="border border-[var(--color-ink)] px-3 py-2 text-sm font-medium disabled:opacity-50"
                >
                  Save
                </button>
              </form>
              <button
                onClick={() => handleActivate('gptzero')}
                disabled={!gptzero?.is_configured || gptzero?.is_active || savingProvider === 'gptzero'}
                className="mt-3 w-full bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {gptzero?.is_active ? 'Currently Active' : 'Activate GPTZero'}
              </button>
            </div>

            {/* Winston AI */}
            <div className="border border-[var(--color-line)] bg-white p-5">
              <div className="flex items-center justify-between">
                <h3 className="font-display-bold text-lg">Winston AI</h3>
                {winston?.is_active && (
                  <span className="border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-emerald-700">
                    Active
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-[var(--color-ink)]/50">
                2,500 free credits. Used only for plagiarism detection (2 credits/word) — never its AI-text or image-detection endpoints.
              </p>
              <div className="mt-3 text-sm">
                Status:{' '}
                {winston?.is_configured ? (
                  <span className="text-[var(--color-ink)]/70">key configured{winston.masked_key ? ` (${winston.masked_key})` : ''}</span>
                ) : (
                  <span className="text-[var(--color-ink)]/50">no key set</span>
                )}
              </div>
              <form onSubmit={(e) => handleSetKey('winston', e)} className="mt-3 flex gap-2">
                <input
                  type="password"
                  placeholder="Winston AI API key"
                  value={winstonKeyInput}
                  onChange={(e) => setWinstonKeyInput(e.target.value)}
                  className="min-w-0 flex-1 border border-[var(--color-line)] px-3 py-2 text-sm"
                />
                <button
                  type="submit"
                  disabled={savingProvider === 'winston'}
                  className="border border-[var(--color-ink)] px-3 py-2 text-sm font-medium disabled:opacity-50"
                >
                  Save
                </button>
              </form>
              <button
                onClick={() => handleActivate('winston')}
                disabled={!winston?.is_configured || winston?.is_active || savingProvider === 'winston'}
                className="mt-3 w-full bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {winston?.is_active ? 'Currently Active' : 'Activate Winston AI'}
              </button>
            </div>
          </div>
        </section>

        {/* ── Usage stats ── */}
        <section className="mt-12 mb-10">
          <h2 className="font-display-bold text-xl">API Request Usage</h2>
          <p className="mt-1 text-sm text-[var(--color-ink)]/55">Refreshes every 15 seconds.</p>

          {usage && (
            <>
              <div className="mt-4 grid grid-cols-1 gap-px bg-[var(--color-line)] sm:grid-cols-2">
                {(['gptzero', 'winston'] as const).map((provider) => {
                  const t = usage.totals_by_provider[provider] || { total_requests: 0, successful_requests: 0 };
                  return (
                    <div key={provider} className="bg-white px-4 py-3.5">
                      <div className="text-[0.68rem] font-semibold uppercase tracking-wide text-[var(--color-ink)]/50">
                        {provider === 'gptzero' ? 'GPTZero' : 'Winston AI'} — total requests
                      </div>
                      <div className="mt-1 font-display-bold text-2xl">{t.total_requests}</div>
                      <div className="mt-0.5 text-xs text-[var(--color-ink)]/50">{t.successful_requests} succeeded</div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-4 border border-[var(--color-line)] bg-white p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink)]/50">
                  Requests per hour, last 24 hours
                </div>
                {usage.hourly_breakdown.length === 0 ? (
                  <p className="mt-3 text-sm text-[var(--color-ink)]/50">No requests logged yet.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={usage.hourly_breakdown}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                      <XAxis dataKey="hour" tick={{ fontSize: 10 }} minTickGap={30} />
                      <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                      <Tooltip />
                      <Line type="monotone" dataKey="gptzero" name="GPTZero" stroke="var(--color-accent)" dot={false} strokeWidth={2} />
                      <Line type="monotone" dataKey="winston" name="Winston AI" stroke="#5c8dff" dot={false} strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
