"""
Signed-URL file streaming — development_rule.md §6.4: PDFs are never served
as a direct downloadable file URL. Every view goes through a short-lived
signed URL, generated per view request, streamed into the viewer.

This is the retrieval half of app/core/storage.py's local-disk placeholder.
The /api/submissions/{id}/file-url endpoint (submissions.py) issues a token;
this router's /api/files/{token} is the only thing that can actually read
the bytes, and only while the token is valid.
"""
from fastapi import APIRouter, HTTPException, Response

from app.core.storage import InvalidSignedUrlError, read_file, verify_signed_url_token

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{token:path}")
def get_file(token: str):
    """
    ':path' converter is required here — the token embeds storage_key, which
    itself contains '/' (e.g. 'submissions/<id>/v1/paper.pdf'), so the
    default single-segment path parameter would 404 on any real token.
    """
    try:
        storage_key = verify_signed_url_token(token)
        content = read_file(storage_key)
    except InvalidSignedUrlError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    return Response(content=content, media_type="application/pdf")
