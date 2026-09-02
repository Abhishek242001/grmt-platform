'use client';

import { useEffect, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import * as api from '@/lib/api';

// pdf.js needs its worker script's URL explicitly — react-pdf doesn't wire
// this up automatically, and without it every render silently fails.
// `new URL(..., import.meta.url)` is the bundler-agnostic way to point at
// the copy shipped inside pdfjs-dist itself, rather than depending on it
// being separately hosted or copied into /public.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString();

const ANNOTATION_COLORS = ['yellow', 'pink', 'sky', 'lime'] as const;
const COLOR_DOT: Record<string, string> = {
  yellow: '#eab308',
  pink: '#ec4899',
  sky: '#0ea5e9',
  lime: '#84cc16',
};

interface PendingPin {
  page: number;
  xPct: number;
  yPct: number;
}

export default function PdfAnnotationViewer({
  versionId,
  canAnnotate,
  currentUserId,
  aiHighlights,
}: {
  versionId: string;
  canAnnotate: boolean;
  currentUserId: string;
  // Optional — AI-text-detection's flagged passages, pre-flattened across
  // all flagged chunks (possibly several entries sharing the same page
  // number, from different chunks). Purely visual, no interaction — unlike
  // the click-to-comment pins above, these aren't something a reviewer
  // creates or deletes. Absent entirely when the caller has no AI-text
  // report yet, or the check found nothing to flag.
  aiHighlights?: api.HighlightBoxesForPage[];
}) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [annotations, setAnnotations] = useState<api.Annotation[]>([]);
  const [pending, setPending] = useState<PendingPin | null>(null);
  const [openAnnotationId, setOpenAnnotationId] = useState<string | null>(null);
  const [commentDraft, setCommentDraft] = useState('');
  const [colorDraft, setColorDraft] = useState<(typeof ANNOTATION_COLORS)[number]>('yellow');
  const [saving, setSaving] = useState(false);

  function loadAnnotations() {
    api.getAnnotations(versionId).then(setAnnotations).catch(() => {});
  }

  useEffect(() => {
    setPdfUrl(null);
    setLoadError(null);
    setPageNumber(1);
    setPending(null);
    api
      .getPdfUrl(versionId)
      .then((signed) => setPdfUrl(signed.url))
      .catch((err) => setLoadError(err instanceof api.ApiError ? err.detail : 'Could not load PDF'));
    loadAnnotations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId]);

  function handlePageClick(e: React.MouseEvent<HTMLDivElement>) {
    if (!canAnnotate) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const xPct = ((e.clientX - rect.left) / rect.width) * 100;
    const yPct = ((e.clientY - rect.top) / rect.height) * 100;
    setOpenAnnotationId(null);
    setPending({ page: pageNumber, xPct, yPct });
    setCommentDraft('');
    setColorDraft('yellow');
  }

  async function savePending() {
    if (!pending) return;
    setSaving(true);
    try {
      await api.createAnnotation(versionId, {
        page_number: pending.page,
        position_json: JSON.stringify({ x: pending.xPct, y: pending.yPct }),
        color: colorDraft,
        comment: commentDraft.trim() || undefined,
      });
      setPending(null);
      loadAnnotations();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(annotationId: string) {
    await api.deleteAnnotation(annotationId);
    setOpenAnnotationId(null);
    loadAnnotations();
  }

  if (loadError) {
    return (
      <p className="mt-3 text-sm text-[var(--color-ink)]/45">
        {loadError === 'No PDF available for this version yet'
          ? 'A PDF isn\u2019t available for this version yet — conversion may still be in progress, or this version predates the PDF pipeline.'
          : loadError}
      </p>
    );
  }

  if (!pdfUrl) {
    return <p className="mt-3 text-sm text-[var(--color-ink)]/45">Loading PDF\u2026</p>;
  }

  const pageAnnotations = annotations.filter((a) => a.page_number === pageNumber);

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
            disabled={pageNumber <= 1}
            className="border border-[var(--color-line)] px-2 py-1 text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/60 disabled:opacity-30"
          >
            Prev
          </button>
          <span className="text-xs text-[var(--color-ink)]/50">
            Page {pageNumber} of {numPages || '…'}
          </span>
          <button
            type="button"
            onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
            disabled={pageNumber >= numPages}
            className="border border-[var(--color-line)] px-2 py-1 text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/60 disabled:opacity-30"
          >
            Next
          </button>
        </div>
        {canAnnotate && (
          <span className="text-xs text-[var(--color-ink)]/40">Click anywhere on the page to leave a note</span>
        )}
      </div>

      <div className="relative mt-3 inline-block border border-[var(--color-line)] bg-white">
        <div className="relative" onClick={handlePageClick}>
          <Document
            file={pdfUrl}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            onLoadError={() =>
              // Distinct from the getPdfUrl() failure path above: pdf-url
              // succeeding only means a syntactically valid signed URL came
              // back (see files.py's own docstring — it never validates a
              // real PDF exists). The ACTUAL fetch of the PDF bytes happens
              // here, inside <Document>, and can fail independently (404
              // from pdf-stream, expired signature, etc.) — without this
              // handler, that failure only surfaced as a console warning
              // react-pdf logs internally, leaving the user looking at a
              // stuck/blank viewer with no explanation.
              setLoadError('No PDF available for this version yet')
            }
            loading="Rendering…"
          >
            <Page pageNumber={pageNumber} width={640} />
          </Document>

          {/* AI-text-detection highlight boxes — purely visual, rendered
              underneath the interactive pin annotations below. Filtered to
              entries matching the CURRENTLY DISPLAYED page only; a chunk
              spanning two pages contributes a separate entry per page (see
              ai_text_highlighting.py's compute_highlight_boxes), so this
              naturally only shows what belongs on this page without extra
              logic here. pointer-events-none so these never intercept
              clicks meant for handlePageClick (leaving a new pin) or the
              pins/popovers themselves. */}
          {aiHighlights &&
            aiHighlights
              .filter((entry) => entry.page === pageNumber)
              .flatMap((entry) => entry.boxes)
              .map((box, i) => (
                <div
                  key={i}
                  className="pointer-events-none absolute border-2 border-amber-500 bg-amber-400/25"
                  style={{
                    left: `${box.xPct}%`,
                    top: `${box.yPct}%`,
                    width: `${box.wPct}%`,
                    height: `${box.hPct}%`,
                  }}
                  title="Flagged as possibly AI-generated"
                />
              ))}

          {pageAnnotations.map((a) => {
            let pos = { x: 50, y: 50 };
            try {
              pos = JSON.parse(a.position_json);
            } catch {
              // malformed position_json — skip rendering this pin rather than crash the viewer
              return null;
            }
            const isOwner = a.reviewer_id === currentUserId;
            const isOpen = openAnnotationId === a.id;
            return (
              <div
                key={a.id}
                style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
                className="absolute -translate-x-1/2 -translate-y-1/2"
                onClick={(e) => {
                  e.stopPropagation();
                  setPending(null);
                  setOpenAnnotationId(isOpen ? null : a.id);
                }}
              >
                <div
                  className="h-4 w-4 cursor-pointer rounded-full border-2 border-white shadow"
                  style={{ backgroundColor: COLOR_DOT[a.color] ?? COLOR_DOT.yellow }}
                />
                {isOpen && (
                  <div className="absolute left-1/2 top-5 z-10 w-56 -translate-x-1/2 border border-[var(--color-line)] bg-white p-3 text-sm shadow-lg">
                    <p className="text-[var(--color-ink)]/70">{a.comment || 'No comment'}</p>
                    {isOwner && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(a.id);
                        }}
                        className="mt-2 text-xs font-bold uppercase tracking-wide text-red-600"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {pending && (
            <div
              style={{ left: `${pending.xPct}%`, top: `${pending.yPct}%` }}
              className="absolute -translate-x-1/2 -translate-y-1/2"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="h-4 w-4 rounded-full border-2 border-white bg-[var(--color-accent)] shadow" />
              <div className="absolute left-1/2 top-5 z-10 w-64 -translate-x-1/2 border border-[var(--color-line)] bg-white p-3 shadow-lg">
                <textarea
                  autoFocus
                  value={commentDraft}
                  onChange={(e) => setCommentDraft(e.target.value)}
                  placeholder="Leave a note for the author…"
                  rows={3}
                  className="w-full resize-none border border-[var(--color-line)] p-2 text-sm"
                />
                <div className="mt-2 flex items-center justify-between">
                  <div className="flex gap-1.5">
                    {ANNOTATION_COLORS.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => setColorDraft(c)}
                        aria-label={c}
                        className={`h-5 w-5 rounded-full border-2 ${colorDraft === c ? 'border-[var(--color-ink)]' : 'border-white'}`}
                        style={{ backgroundColor: COLOR_DOT[c] }}
                      />
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setPending(null)}
                      className="text-xs font-bold uppercase tracking-wide text-[var(--color-ink)]/50"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={savePending}
                      disabled={saving}
                      className="bg-[var(--color-accent)] px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-white disabled:opacity-50"
                    >
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
