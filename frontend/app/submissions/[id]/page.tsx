'use client';

import dynamic from 'next/dynamic';
import { FormEvent, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import AppHeader from '@/components/AppHeader';
import StatusBadge from '@/components/StatusBadge';

// react-pdf touches browser-only APIs (Canvas, DOMMatrix) that don't exist
// during Next.js's server render — ssr: false is required, not optional,
// or the build itself fails.
const PdfAnnotationViewer = dynamic(() => import('@/components/PdfAnnotationViewer'), {
  ssr: false,
  loading: () => <p className="mt-3 text-sm text-[var(--color-ink)]/45">Loading viewer…</p>,
});

function GrammarReportCard({ report }: { report: api.AIReport }) {
  let result: api.GrammarCheckResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-red-600">
        Grammar check failed: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Grammar</span>
        <span className="font-display-bold text-2xl text-[var(--color-accent)]">{result.score}</span>
        <span className="text-xs text-[var(--color-ink)]/50">
          {result.error_count} flagged issue{result.error_count === 1 ? '' : 's'}
        </span>
      </div>

      {result.chunks_total !== undefined && (
        <p className="mt-1.5 text-xs text-[var(--color-ink)]/40">
          Full document checked
          {result.word_count ? ` — ${result.word_count.toLocaleString()} words` : ''}
          {result.chunks_total > 1 ? ` across ${result.chunks_total} sections` : ''}
          {result.chunks_checked !== undefined && result.chunks_checked < result.chunks_total
            ? ` (${result.chunks_total - result.chunks_checked} section(s) failed to check — results may be incomplete)`
            : ''}
        </p>
      )}

      {result.matches.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.matches.map((m, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="font-bold">{m.category || m.rule_id}</span>
                {m.page != null && (
                  <span className="whitespace-nowrap text-xs font-bold uppercase tracking-wide text-[var(--color-accent)]">
                    Page {m.page}
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-[var(--color-ink)]/60">{m.message}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FormatReportCard({ report }: { report: api.AIReport }) {
  let result: api.FormatCheckResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-red-600">
        Format check failed: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Format ({(result.publisher_format || 'ieee').toUpperCase()})</span>
        <span className="font-display-bold text-2xl text-[var(--color-accent)]">{result.score}</span>
        <span className="text-xs text-[var(--color-ink)]/50">
          {result.checks_passed}/{result.checks_total} checks passed
        </span>
      </div>

      {result.issues.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.issues.map((issue, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm text-[var(--color-ink)]/70">
              {issue}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TableFigureReportCard({ report }: { report: api.AIReport }) {
  let result: api.TableFigureCheckResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-red-600">
        Table/figure check failed: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  const nothingToCheck = !result.figures_found && !result.tables_found;

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Tables &amp; Figures</span>
        {result.score !== null ? (
          <span className="font-display-bold text-2xl text-[var(--color-accent)]">{result.score}</span>
        ) : (
          <span className="text-xs text-[var(--color-ink)]/50">No tables or figures detected</span>
        )}
        {result.score !== null && (
          <span className="text-xs text-[var(--color-ink)]/50">
            {result.checks_passed}/{result.checks_total} checks passed
          </span>
        )}
      </div>

      {!nothingToCheck && result.issues.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.issues.map((issue, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm text-[var(--color-ink)]/70">
              {issue}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Finds the ai_text report (if any, if complete) among all check reports
// and flattens every flagged chunk's highlight_boxes into one array —
// PdfAnnotationViewer just needs page-filtered boxes to draw, not the full
// per-chunk structure (text, probability, etc.) that AiTextDetectionReportCard
// itself renders separately.
function extractAiHighlights(aiReports: api.AIReport[]): api.HighlightBoxesForPage[] {
  const report = aiReports.find((r) => r.check_type === 'ai_text');
  if (!report?.result_json) return [];
  let result: api.AiTextDetectionResult | null = null;
  try {
    result = JSON.parse(report.result_json);
  } catch {
    return [];
  }
  if (!result || result.status !== 'complete' || !result.flagged_chunks) return [];
  return result.flagged_chunks.flatMap((chunk) => chunk.highlight_boxes ?? []);
}

function AiTextDetectionReportCard({ report }: { report: api.AIReport }) {
  let result: api.AiTextDetectionResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    // Deliberately gentle wording, not "failed" in red like a hard error —
    // this check needs torch/transformers/GPU on whatever machine runs
    // the background task, and a missing-GPU environment is an expected,
    // graceful outcome (see backend/app/ai/ai_content_pipeline.py), not
    // something to alarm a reviewer about.
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-[var(--color-ink)]/50">
        AI content detection unavailable: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  const pct = result.ai_generated_percentage ?? 0;
  const maxPct = result.max_ai_percentage;
  const isReject = result.overall_verdict === 'reject';

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">AI-Generated Content</span>
        <span
          className={`font-display-bold text-2xl ${isReject ? 'text-red-600' : 'text-[var(--color-accent)]'}`}
        >
          {pct.toFixed(1)}%
        </span>
        {maxPct !== undefined && (
          <span className="text-xs text-[var(--color-ink)]/50">
            organizer max: {maxPct}% — {result.ai_word_count}/{result.total_word_count} words flagged
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-[var(--color-ink)]/40">
        Score is informational for reviewers, not an automatic reject — a person always makes the final call.
      </p>

      {result.flagged_chunks && result.flagged_chunks.length > 0 && (
        <div className="mt-3 space-y-2">
          {result.flagged_chunks.map((chunk, i) => (
            <div
              key={i}
              className="border-l-4 border-yellow-400 bg-yellow-50 p-3 text-sm text-[var(--color-ink)]/80"
            >
              <div className="mb-1 flex items-center justify-between text-xs text-[var(--color-ink)]/50">
                <span>{chunk.word_count} words</span>
                <span>{(chunk.ai_probability * 100).toFixed(1)}% AI probability</span>
              </div>
              <p className="whitespace-pre-wrap">{chunk.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CitationReportCard({ report }: { report: api.AIReport }) {
  let result: api.CitationCheckResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-[var(--color-ink)]/50">
        Citation check unavailable: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Citations</span>
        {result.score !== null ? (
          <span className="font-display-bold text-2xl text-[var(--color-accent)]">{result.score}</span>
        ) : (
          <span className="text-xs text-[var(--color-ink)]/50">No citations detected</span>
        )}
        {result.total_citations !== undefined && (
          <span className="text-xs text-[var(--color-ink)]/50">
            {result.total_citations} citations, {result.total_bibliography_entries} references
          </span>
        )}
      </div>

      {result.issues.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.issues.map((issue, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm text-[var(--color-ink)]/70">
              {issue}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LogicalConsistencyReportCard({ report }: { report: api.AIReport }) {
  let result: api.LogicalConsistencyResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-[var(--color-ink)]/50">
        Logical consistency check unavailable: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Logical Consistency</span>
        <span className={`font-display-bold text-2xl ${result.consistent ? 'text-[var(--color-accent)]' : 'text-red-600'}`}>
          {result.consistent ? 'Consistent' : 'Inconsistent'}
        </span>
      </div>
      <p className="mt-1 text-xs text-[var(--color-ink)]/40">
        Compares the abstract against the conclusion only — an AI judgment call, informational for reviewers, never an automatic reject.
      </p>

      {result.findings && result.findings.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.findings.map((finding, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm text-[var(--color-ink)]/70">
              <p><span className="font-bold">Abstract:</span> {finding.abstract_claim}</p>
              <p className="mt-1"><span className="font-bold">Conclusion:</span> {finding.conclusion_statement}</p>
              <p className="mt-1 text-[var(--color-ink)]/50">{finding.explanation}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PlagiarismReportCard({ report }: { report: api.AIReport }) {
  let result: api.PlagiarismCheckResult | null = null;
  try {
    result = report.result_json ? JSON.parse(report.result_json) : null;
  } catch {
    result = null;
  }

  if (!result || result.status !== 'complete') {
    return (
      <div className="mt-3 border-t border-[var(--color-line)] pt-3 text-sm text-[var(--color-ink)]/50">
        Plagiarism check unavailable: {result?.error ?? 'unknown error'}
      </div>
    );
  }

  const external = result.external;

  return (
    <div className="mt-3 border-t border-[var(--color-line)] pt-4">
      <div className="flex items-center gap-4">
        <span className="font-bold">Plagiarism</span>
        {result.score !== null ? (
          <span className="font-display-bold text-2xl text-[var(--color-accent)]">{result.score}</span>
        ) : (
          <span className="text-xs text-[var(--color-ink)]/50">No score computed</span>
        )}
        {result.candidates_compared !== undefined && (
          <span className="text-xs text-[var(--color-ink)]/50">
            compared against {result.candidates_compared} prior submission{result.candidates_compared === 1 ? '' : 's'}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-[var(--color-ink)]/40">
        An automated similarity score is informational for reviewers, never an automatic finding of plagiarism.
      </p>

      {/* Self-submission matches — GRMT's own prior submissions */}
      {result.matches && result.matches.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/50">
            Matched against prior GRMT submissions
          </div>
          <ul className="mt-2 space-y-2">
            {result.matches.map((m, i) => (
              <li key={i} className="flex items-center justify-between border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm">
                <span className="text-[var(--color-ink)]/70">Submission {m.submission_id}</span>
                <span className="font-display-bold text-[var(--color-accent)]">{(m.similarity * 100).toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* External literature comparison (Winston AI, abstract-only — see plagiarism_check.py) */}
      <div className="mt-4">
        <div className="text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/50">
          External literature comparison
        </div>

        {external === null && (
          <p className="mt-2 text-sm text-[var(--color-ink)]/50">
            Not run — no external provider is currently active in the admin panel.
          </p>
        )}

        {external !== null && external.status !== 'complete' && (
          <p className="mt-2 text-sm text-[var(--color-ink)]/50">{external.error ?? 'Unknown error'}</p>
        )}

        {external !== null && external.status === 'complete' && (
          <>
            <div className="mt-2 flex items-center gap-4">
              <span className="font-display-bold text-2xl text-[var(--color-accent)]">
                {external.overall_similarity_pct?.toFixed(1)}%
              </span>
              <span className="text-xs text-[var(--color-ink)]/50">overall similarity (abstract only)</span>
              {external.credits_remaining !== undefined && (
                <span className="text-xs text-[var(--color-ink)]/40">{external.credits_remaining} credits remaining</span>
              )}
            </div>

            {external.matches && external.matches.length > 0 ? (
              <ul className="mt-3 space-y-2">
                {external.matches.map((m, i) => (
                  <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm">
                    <div className="flex items-center justify-between">
                      {m.source_url ? (
                        <a href={m.source_url} target="_blank" rel="noopener noreferrer" className="text-[var(--color-accent)] hover:underline">
                          {m.source_title || m.source_url}
                        </a>
                      ) : (
                        <span className="text-[var(--color-ink)]/70">{m.source_title || 'Unknown source'}</span>
                      )}
                      <span className="font-display-bold text-[var(--color-accent)]">{m.similarity_pct.toFixed(1)}%</span>
                    </div>
                    {m.can_access === false && (
                      <p className="mt-1 text-xs text-amber-700">
                        Winston found this source but couldn&apos;t fetch its full text to compare — this score reflects
                        that it couldn&apos;t be checked, not that it was checked and found dissimilar.
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-[var(--color-ink)]/50">No matching external sources found.</p>
            )}
          </>
        )}
      </div>

      {result.issues.length > 0 && (
        <ul className="mt-3 space-y-2">
          {result.issues.map((issue, i) => (
            <li key={i} className="border border-[var(--color-line)] bg-[var(--color-paper)] p-3 text-sm text-[var(--color-ink)]/70">
              {issue}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// update51 — replaces the old "all 7 checks stacked vertically" layout
// with a horizontal step-by-step wizard (per explicit request: like a job
// application form's Personal Details → Academic Details progression).
// Each step gets a green check once that check has actually finished
// (status "complete"), amber for "error", grey for still pending — and
// only the currently-selected step's full report renders below. Any step
// can be clicked directly (not strictly linear) since this same page is
// shared by researchers, reviewers, and organizers, who all have
// legitimate reasons to jump straight to one specific check's results
// rather than click through every step in order.
const CHECK_STEPS: { type: string; label: string }[] = [
  { type: 'grammar', label: 'Grammar' },
  { type: 'format', label: 'Format' },
  { type: 'table_figure', label: 'Tables & Figures' },
  { type: 'ai_text', label: 'AI-Generated Content' },
  { type: 'citation', label: 'Citations' },
  { type: 'logical_consistency', label: 'Logical Consistency' },
  { type: 'plagiarism', label: 'Plagiarism' },
];

function CheckStepper({
  reports,
  activeCheck,
  onSelect,
}: {
  reports: api.AIReport[];
  activeCheck: string;
  onSelect: (checkType: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-stretch gap-0 overflow-x-auto border border-[var(--color-line)] bg-white">
      {CHECK_STEPS.map((step, i) => {
        const report = reports.find((r) => r.check_type === step.type);
        const state: 'complete' | 'error' | 'pending' =
          report?.status === 'complete' ? 'complete' : report?.status === 'error' ? 'error' : 'pending';
        const isActive = activeCheck === step.type;

        return (
          <button
            key={step.type}
            type="button"
            onClick={() => onSelect(step.type)}
            className={`flex min-w-[130px] flex-1 items-center gap-2 border-r border-[var(--color-line)] px-3 py-3 text-left text-xs transition last:border-r-0 ${
              isActive ? 'bg-[var(--color-accent-soft)]' : 'hover:bg-[var(--color-paper)]'
            }`}
          >
            <span
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[0.65rem] font-bold ${
                state === 'complete'
                  ? 'bg-[var(--color-accent)] text-white'
                  : state === 'error'
                  ? 'bg-amber-500 text-white'
                  : 'border border-[var(--color-line)] text-[var(--color-ink)]/40'
              }`}
            >
              {state === 'complete' ? '✓' : i + 1}
            </span>
            <span className={`font-semibold ${isActive ? 'text-[var(--color-accent)]' : ''}`}>{step.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function SubmissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, isLoading } = useAuth();
  const router = useRouter();

  const [submission, setSubmission] = useState<api.Submission | null>(null);
  const [history, setHistory] = useState<api.SubmissionVersion[]>([]);
  const [decision, setDecision] = useState<api.Decision | null>(null);
  const [reviews, setReviews] = useState<api.Review[]>([]);
  const [aiReports, setAiReports] = useState<api.AIReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [activeCheck, setActiveCheck] = useState<string>('grammar');

  // resubmit form state
  const [file, setFile] = useState<File | null>(null);
  const [resubmitting, setResubmitting] = useState(false);

  // update51 — submit-for-review (the researcher's explicit review-then-
  // submit checkpoint) and camera-ready upload state
  const [submittingForReview, setSubmittingForReview] = useState(false);
  const [cameraReadyFile, setCameraReadyFile] = useState<File | null>(null);
  const [copyrightFile, setCopyrightFile] = useState<File | null>(null);
  const [cameraReadySubmitting, setCameraReadySubmitting] = useState(false);
  const [cameraReadySuccess, setCameraReadySuccess] = useState(false);

  // reviewer form state
  const [recommendation, setRecommendation] = useState('accept');
  const [comments, setComments] = useState('');
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewSuccess, setReviewSuccess] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) router.push('/login');
  }, [isLoading, user, router]);

  function reload() {
    if (!id) return;
    api.getSubmission(id).then(setSubmission).catch(() => setError('Submission not found'));
    api.getSubmissionHistory(id).then(setHistory).catch(() => {});
    api.getDecision(id).then(setDecision).catch(() => {});
    api.listReviews(id).then(setReviews).catch(() => {});
    api.getAiReports(id).then(setAiReports).catch(() => {});
  }

  useEffect(() => {
    if (!user) return;
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, id]);

  // Live push via WebSocket — subscribes to submission:{id}:updates (scoped
  // to exactly this submission; distinct from conference:{id}:queue, which
  // is organizer/co-admin only and wouldn't authorize a researcher or
  // reviewer viewing their own/assigned submission's detail page). Falls
  // back to the polling effect below if the connection never opens or
  // drops — WS is the fast path, not the only path.
  const [wsConnected, setWsConnected] = useState(false);
  useEffect(() => {
    if (!user || !id) return;

    let socket: WebSocket | null = null;
    let cancelled = false;

    api.getWsTicket().then(({ ticket }) => {
      if (cancelled) return;
      const wsBase = process.env.NEXT_PUBLIC_WS_BASE_URL || '/api/ws';
      socket = new WebSocket(`${wsBase}?ticket=${ticket}`);

      socket.onopen = () => {
        socket?.send(JSON.stringify({ action: 'subscribe', channel: `submission:${id}:updates` }));
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'subscribed') {
            setWsConnected(true);
            return;
          }
          if (
            msg.type === 'ai_report.check_completed' ||
            msg.type === 'submission_version.pdf_converted' ||
            msg.type === 'submission.status_changed' ||
            msg.type === 'submission.resubmitted'
          ) {
            reload();
          }
        } catch {
          // malformed frame — ignore rather than crash the page over a bad push
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
  }, [user, id]);

  // Fallback polling — only runs while WS isn't connected, so a working
  // live-push connection means zero polling traffic, but a dropped/blocked
  // WebSocket (proxy issues, browser extension, etc.) still degrades
  // gracefully to the same behavior this page had before WS existed.
  useEffect(() => {
    if (wsConnected) return;
    if (!submission || submission.status !== 'processing' || aiReports.length > 0) return;
    const interval = setInterval(reload, 4000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submission, aiReports, wsConnected]);

  async function handleResubmit(e: FormEvent) {
    e.preventDefault();
    if (!file || !id) return;
    setResubmitting(true);
    try {
      await api.resubmit(id, file);
      reload();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Resubmit failed');
    } finally {
      setResubmitting(false);
    }
  }

  async function handleSubmitForReview() {
    if (!id) return;
    setSubmittingForReview(true);
    try {
      await api.submitForReview(id);
      reload();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Could not submit for review');
    } finally {
      setSubmittingForReview(false);
    }
  }

  async function handleCameraReadySubmit(e: FormEvent) {
    e.preventDefault();
    if (!cameraReadyFile || !id) return;
    setCameraReadySubmitting(true);
    try {
      await api.submitCameraReady(id, cameraReadyFile, copyrightFile ?? undefined);
      setCameraReadySuccess(true);
      reload();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Camera-ready submission failed');
    } finally {
      setCameraReadySubmitting(false);
    }
  }

  async function handleReviewSubmit(e: FormEvent) {
    e.preventDefault();
    if (!id) return;
    setReviewSubmitting(true);
    try {
      await api.submitReview(id, { recommendation, comments });
      setReviewSuccess(true);
      reload();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Review submission failed');
    } finally {
      setReviewSubmitting(false);
    }
  }

  if (isLoading || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-[var(--color-ink)]/50">Loading…</div>;
  }

  const myExistingReview = reviews.find((r) => r.reviewer_id === user.id);

  return (
    <div className="min-h-screen bg-[var(--color-paper)]">
      <AppHeader />
      <main className="mx-auto max-w-[900px] px-8 py-12">
        {error && <div role="alert" className="mb-6 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        {submission && (
          <>
            <div className="flex items-center gap-3">
              <h1 className="font-display-bold text-3xl">{submission.title}</h1>
              <StatusBadge status={submission.status} />
            </div>

            {submission.previously_rejected_disclosure && (
              <div className="mt-4 border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                <span className="font-bold">Researcher-disclosed history:</span> {submission.previously_rejected_disclosure}
              </div>
            )}

            {decision && (
              <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Final Decision</h2>
                <p className="mt-2 font-extrabold capitalize">{decision.decision.replace('_', ' ')}</p>
                {decision.notes && <p className="mt-1 text-sm text-[var(--color-ink)]/60">{decision.notes}</p>}
              </div>
            )}

            <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
              <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Version History</h2>
              <ul className="mt-3 space-y-2">
                {history.map((v) => (
                  <li key={v.id} className="flex justify-between text-sm">
                    <span>v{v.version_number} — {v.original_filename}</span>
                  </li>
                ))}
              </ul>
            </div>

            {history.length > 0 && (
              <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Paper</h2>
                <PdfAnnotationViewer
                  versionId={history[history.length - 1].id}
                  canAnnotate={user.role === 'reviewer'}
                  currentUserId={user.id}
                  aiHighlights={extractAiHighlights(aiReports)}
                />
              </div>
            )}

            <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
              <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">AI Feedback</h2>

              {submission.status === 'processing' && aiReports.length === 0 && (
                <p className="mt-3 text-sm text-[var(--color-ink)]/50">Checks are running…</p>
              )}

              {aiReports.length === 0 && submission.status !== 'processing' && (
                <p className="mt-3 text-sm text-[var(--color-ink)]/45">No checks have run yet.</p>
              )}

              {aiReports.length > 0 && (
                <>
                  <div className="mt-4">
                    <CheckStepper reports={aiReports} activeCheck={activeCheck} onSelect={setActiveCheck} />
                  </div>

                  {(() => {
                    const report = aiReports.find((r) => r.check_type === activeCheck);
                    if (!report) {
                      return (
                        <p className="mt-4 text-sm text-[var(--color-ink)]/45">
                          This check hasn&apos;t run yet — its report will appear here once it completes.
                        </p>
                      );
                    }
                    const card = (() => {
                      if (report.check_type === 'grammar') return <GrammarReportCard key={report.id} report={report} />;
                      if (report.check_type === 'format') return <FormatReportCard key={report.id} report={report} />;
                      if (report.check_type === 'table_figure') return <TableFigureReportCard key={report.id} report={report} />;
                      if (report.check_type === 'ai_text') return <AiTextDetectionReportCard key={report.id} report={report} />;
                      if (report.check_type === 'citation') return <CitationReportCard key={report.id} report={report} />;
                      if (report.check_type === 'logical_consistency') return <LogicalConsistencyReportCard key={report.id} report={report} />;
                      if (report.check_type === 'plagiarism') return <PlagiarismReportCard key={report.id} report={report} />;
                      return (
                        <div key={report.id} className="text-sm">
                          <span className="font-bold capitalize">{report.check_type.replace('_', ' ')}</span> — {report.status}
                        </div>
                      );
                    })();
                    // Every ReportCard's own root div hardcodes "mt-3 border-t
                    // pt-*" — the right look when several were stacked one
                    // after another, but a stray leading divider line with
                    // nothing above it now that only one renders at a time
                    // under the stepper. [&>*] targets only that single
                    // direct root, not anything nested inside it.
                    return <div className="[&>*]:mt-0 [&>*]:border-t-0 [&>*]:pt-0">{card}</div>;
                  })()}
                </>
              )}
            </div>

            {/* update51 — the researcher's explicit review-then-submit
                checkpoint. "ai_review_passed" means every configured hard
                gate passed, but the paper has NOT yet been sent to
                reviewers — that only happens once the researcher reviews
                the results above and clicks this button themselves. */}
            {user.role === 'researcher' && submission.status === 'ai_review_passed' && (
              <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Ready to Submit</h2>
                <p className="mt-2 text-sm text-[var(--color-ink)]/60">
                  Your paper has passed every required check above. Review the results, then submit it for human
                  review when you&apos;re ready — this cannot be undone.
                </p>
                <button
                  onClick={handleSubmitForReview}
                  disabled={submittingForReview}
                  className="mt-4 bg-[var(--color-accent)] px-6 py-2.5 text-sm font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
                  style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
                >
                  {submittingForReview ? 'Submitting…' : 'Submit for Review'}
                </button>
              </div>
            )}

            {user.role === 'researcher' && submission.status === 'ai_review_hard_failed' && (
              <div className="mt-6 border border-red-200 bg-red-50 p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-red-700">Cannot Be Submitted Yet</h2>
                <p className="mt-2 text-sm text-red-700">
                  This paper didn&apos;t pass one or more required checks above, so it can&apos;t be sent for review
                  in its current form. Revise your paper based on the feedback and upload a new version below to
                  try again.
                </p>
              </div>
            )}

            {user.role === 'researcher' && submission.status === 'accepted' && !submission.camera_ready_file_url && (
              <form onSubmit={handleCameraReadySubmit} className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Submit Camera-Ready Paper</h2>
                <p className="mt-2 text-sm text-[var(--color-ink)]/60">
                  Your paper has been accepted. Upload the final camera-ready version below. A signed copyright
                  transfer form is optional.
                </p>
                {cameraReadySuccess && (
                  <p className="mt-3 text-sm font-semibold text-[var(--color-accent)]">Camera-ready paper submitted.</p>
                )}
                <label className="mt-4 block text-sm font-medium">Camera-ready file</label>
                <input
                  type="file" accept=".docx,.pdf" required
                  onChange={(e) => setCameraReadyFile(e.target.files?.[0] ?? null)}
                  className="mt-1.5 w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                />
                <label className="mt-4 block text-sm font-medium">Signed copyright transfer (optional)</label>
                <input
                  type="file" accept=".docx,.pdf"
                  onChange={(e) => setCopyrightFile(e.target.files?.[0] ?? null)}
                  className="mt-1.5 w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                />
                <button
                  type="submit" disabled={cameraReadySubmitting}
                  className="mt-4 bg-[var(--color-accent)] px-6 py-2.5 text-sm font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
                  style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
                >
                  {cameraReadySubmitting ? 'Uploading…' : 'Submit Camera-Ready Paper'}
                </button>
              </form>
            )}

            {submission.camera_ready_file_url && (
              <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Camera-Ready Paper</h2>
                <p className="mt-2 text-sm text-[var(--color-ink)]/60">
                  Submitted{submission.copyright_transfer_file_url ? ' with a signed copyright transfer.' : '.'}
                </p>
              </div>
            )}

            {user.role === 'researcher' && (submission.status === 'revise_resubmit' || submission.status === 'ai_review_hard_failed') && (
              <form onSubmit={handleResubmit} className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Resubmit</h2>
                <input
                  type="file" accept=".docx,.pdf" required
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="mt-3 w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                />
                <button
                  type="submit" disabled={resubmitting}
                  className="mt-4 bg-[var(--color-accent)] px-6 py-2.5 text-sm font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
                  style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
                >
                  {resubmitting ? 'Resubmitting…' : 'Resubmit'}
                </button>
              </form>
            )}

            {user.role === 'reviewer' && (
              <form onSubmit={handleReviewSubmit} className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">
                  {myExistingReview ? 'Update Your Review' : 'Submit Your Review'}
                </h2>
                {reviewSuccess && <div className="mt-3 border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">Review saved.</div>}
                <div className="mt-4">
                  <label className="mb-1.5 block text-sm font-medium">Recommendation</label>
                  <select
                    value={recommendation} onChange={(e) => setRecommendation(e.target.value)}
                    className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                  >
                    <option value="accept">Accept</option>
                    <option value="minor_revision">Minor Revision</option>
                    <option value="major_revision">Major Revision</option>
                    <option value="reject">Reject</option>
                  </select>
                </div>
                <div className="mt-4">
                  <label className="mb-1.5 block text-sm font-medium">Comments</label>
                  <textarea
                    value={comments} onChange={(e) => setComments(e.target.value)} rows={4}
                    className="w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
                  />
                </div>
                <button
                  type="submit" disabled={reviewSubmitting}
                  className="mt-4 bg-[var(--color-accent)] px-6 py-2.5 text-sm font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
                  style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
                >
                  {reviewSubmitting ? 'Saving…' : 'Submit Review'}
                </button>
              </form>
            )}

            {(user.role === 'organizer' || user.role === 'platform_admin') && (
              <div className="mt-6 border border-[var(--color-line)] bg-white p-6">
                <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">
                  Reviews ({reviews.length})
                </h2>
                <ul className="mt-3 space-y-3">
                  {reviews.map((r) => (
                    <li key={r.id} className="border-t border-[var(--color-line)] pt-3 text-sm">
                      <span className="font-bold capitalize">{r.recommendation.replace('_', ' ')}</span>
                      {r.comments && <p className="mt-1 text-[var(--color-ink)]/60">{r.comments}</p>}
                    </li>
                  ))}
                </ul>
                <DecisionForm submissionId={id} onDecided={reload} />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function DecisionForm({ submissionId, onDecided }: { submissionId: string; onDecided: () => void }) {
  const [decision, setDecision] = useState('accept');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.makeDecision(submissionId, { decision, notes });
      onDecided();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-5 border-t border-[var(--color-line)] pt-5">
      <h3 className="text-sm font-bold uppercase tracking-wide text-[var(--color-ink)]/50">Make Final Decision</h3>
      <select
        value={decision} onChange={(e) => setDecision(e.target.value)}
        className="mt-3 w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
      >
        <option value="accept">Accept</option>
        <option value="revise_resubmit">Revise & Resubmit</option>
        <option value="reject">Reject</option>
      </select>
      <textarea
        value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Notes for the researcher"
        className="mt-3 w-full border border-[var(--color-line)] bg-white px-3.5 py-2.5 text-sm"
      />
      <button
        type="submit" disabled={submitting}
        className="mt-3 bg-[var(--color-ink)] px-6 py-2.5 text-sm font-extrabold uppercase tracking-wide text-white disabled:opacity-50"
        style={{ clipPath: 'polygon(3% 0, 100% 0, 97% 100%, 0 100%)' }}
      >
        {submitting ? 'Saving…' : 'Submit Decision'}
      </button>
    </form>
  );
}
