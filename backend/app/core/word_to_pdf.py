"""Word-to-PDF conversion via LibreOffice headless (`soffice --headless
--convert-to pdf`) — not `docx2pdf`, which is Windows/COM-only and not
viable server-side (handoff doc §6's own stated reasoning for this choice).
Deterministic, external-process-based; not an AI model.

Unlocks two downstream pieces of Phase 2 infrastructure that only work
against PDF: the reviewer's PDF annotation viewer (the `PDFAnnotation`
model — page_number-indexed — already existed from Phase 1, built for
exactly this, just never had a PDF to point at for .docx submissions) and
GROBID's citation-completeness check (GROBID is PDF-only).

Real gotcha, not a hypothetical one: LibreOffice headless instances
sharing the same user-profile directory can lock/clash when invoked
concurrently — well-documented upstream LibreOffice behavior, not specific
to this codebase. Under real traffic, two uploads finishing conversion
around the same time would otherwise race on the same default profile.
Each call here gets its own throwaway profile directory
(`-env:UserInstallation=file://...`), removed after the call, so
concurrent conversions can never collide.
"""
import os
import shutil
import subprocess
import tempfile

# Generous but bounded — LibreOffice's cold start alone can take a few
# seconds; a genuinely stuck/hung soffice process shouldn't block a
# background task indefinitely.
_CONVERT_TIMEOUT_SECONDS = 90


class ConversionError(Exception):
    """Raised for any HARD conversion failure — missing binary, missing
    input file, timeout, non-zero exit, or LibreOffice reporting success
    but producing no output file. Callers should never receive a partial
    or missing path.

    Does NOT catch every quality problem: confirmed empirically, LibreOffice
    is extremely permissive about malformed input. A genuinely corrupt or
    non-docx file does NOT raise a non-zero exit — soffice falls back to
    interpreting the raw bytes as plain text and produces a PDF containing
    that text verbatim, exit code 0, no stderr. This conversion step is
    therefore NOT a validity check for the source file; that's already
    python-docx's job (via docx_utils.open_docx(), used by the AI checks,
    which DOES raise loudly on a genuinely corrupt .docx)."""


def convert_to_pdf(source_path: str, output_dir: str) -> str:
    """Converts source_path (.docx, or anything LibreOffice can read) to
    PDF, writing into output_dir under LibreOffice's own naming
    (`<original basename>.pdf`). Returns the resulting PDF's path."""
    if shutil.which("soffice") is None:
        raise ConversionError("LibreOffice ('soffice') is not installed or not on PATH")

    if not os.path.isfile(source_path):
        raise ConversionError(f"Source file not found: {source_path}")

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile_dir:
        try:
            result = subprocess.run(
                [
                    "soffice", "--headless", "--norestore",
                    f"-env:UserInstallation=file://{profile_dir}",
                    "--convert-to", "pdf", "--outdir", output_dir, source_path,
                ],
                capture_output=True, text=True, timeout=_CONVERT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise ConversionError(f"LibreOffice conversion timed out after {_CONVERT_TIMEOUT_SECONDS}s") from e

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no output captured"
            raise ConversionError(f"LibreOffice conversion failed (exit {result.returncode}): {detail}")

    base_name = os.path.splitext(os.path.basename(source_path))[0]
    expected_pdf = os.path.join(output_dir, f"{base_name}.pdf")
    if not os.path.isfile(expected_pdf):
        raise ConversionError(f"Conversion reported success but no output file found at {expected_pdf}")

    return expected_pdf
