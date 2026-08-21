import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.file_signing import generate_signed_url, verify_signed_url
from app.models.conferences import Conference, ConferenceCoAdmin, ConferenceReviewer
from app.models.core import User
from app.models.submissions import PDFAnnotation, Submission, SubmissionVersion
from app.schemas.files import AnnotationIn, AnnotationOut, SignedUrlOut

router = APIRouter(prefix="/api/submissions", tags=["files"])


def _get_version_with_visibility_or_404(version_id: str, user: User, db: Session) -> SubmissionVersion:
    version = db.query(SubmissionVersion).filter(SubmissionVersion.id == version_id).first()
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    sub = db.query(Submission).filter(Submission.id == version.submission_id).first()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if sub.researcher_id == user.id or user.role == "platform_admin":
        return version

    conf = db.query(Conference).filter(Conference.id == sub.conference_id).first()
    if conf and conf.organizer_id == user.id:
        return version

    is_coadmin = (
        db.query(ConferenceCoAdmin)
        .filter(ConferenceCoAdmin.conference_id == sub.conference_id, ConferenceCoAdmin.user_id == user.id)
        .first() is not None
    )
    is_reviewer = (
        db.query(ConferenceReviewer)
        .filter(ConferenceReviewer.conference_id == sub.conference_id, ConferenceReviewer.reviewer_id == user.id)
        .first() is not None
    )
    if is_coadmin or is_reviewer:
        return version

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/versions/{version_id}/pdf-url", response_model=SignedUrlOut)
def get_pdf_url(version_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Issues a short-lived signed URL. Signs `version_id` itself, not the
    raw filesystem path — the actual path is resolved server-side by
    pdf-stream below, so this never leaks the container's filesystem
    layout to the client. Doesn't validate a PDF actually exists yet
    (matches the original contract this endpoint already had, before any
    real upload path existed) — a missing/not-yet-converted file is
    discovered at fetch time by pdf-stream, the same way a presigned
    object-storage URL wouldn't validate object existence upfront either."""
    _get_version_with_visibility_or_404(version_id, user, db)
    from app.core.config import settings

    signed = generate_signed_url(version_id)
    query = signed.split("?", 1)[1]  # generate_signed_url appends "?expires=...&signature=..."
    url = f"/api/submissions/versions/{version_id}/pdf-stream?{query}"
    return SignedUrlOut(url=url, expires_in_seconds=settings.signed_url_expire_seconds)


@router.get("/versions/{version_id}/pdf-stream")
def stream_pdf(version_id: str, expires: int, signature: str, db: Session = Depends(get_db)):
    """The endpoint pdf-url's signed URL actually points at — genuinely
    streams the PDF bytes. Deliberately has NO `get_current_user`
    dependency: the whole point of a signed URL is that a browser's native
    PDF viewer (`<embed>`/`<iframe>`/PDF.js) can fetch it directly without
    attaching an Authorization header, which it has no way to do. The
    signature itself (verified via HMAC, checked for expiry) is the auth
    for this endpoint — matches file_signing.py's own documented security
    model ("short-lived signed streaming URLs only, never a direct
    downloadable link"). Auth for WHO can obtain a signature already
    happened at pdf-url, gated by _get_version_with_visibility_or_404."""
    if not verify_signed_url(version_id, expires, signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired signature")

    version = db.query(SubmissionVersion).filter(SubmissionVersion.id == version_id).first()
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    path = version.converted_pdf_url or version.original_file_url
    if not path or not path.lower().endswith(".pdf") or not os.path.isfile(path):
        # Covers three real cases distinctly, but the same response for all
        # of them: no PDF yet (conversion pending/failed and original was
        # .docx), a placeholder/non-real path (pre-real-upload test data),
        # or a path that no longer exists on disk.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No PDF available for this version yet")

    return FileResponse(path, media_type="application/pdf")


@router.post("/versions/{version_id}/annotations", response_model=AnnotationOut, status_code=status.HTTP_201_CREATED)
def create_annotation(
    version_id: str,
    payload: AnnotationIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_version_with_visibility_or_404(version_id, user, db)
    if user.role not in ("reviewer", "platform_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only reviewers can annotate")

    annotation = PDFAnnotation(submission_version_id=version_id, reviewer_id=user.id, **payload.model_dump())
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.get("/versions/{version_id}/annotations", response_model=list[AnnotationOut])
def list_annotations(version_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_version_with_visibility_or_404(version_id, user, db)
    return db.query(PDFAnnotation).filter(PDFAnnotation.submission_version_id == version_id).all()


@router.delete("/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(annotation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    annotation = db.query(PDFAnnotation).filter(PDFAnnotation.id == annotation_id).first()
    if annotation is None or annotation.reviewer_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    db.delete(annotation)
    db.commit()
