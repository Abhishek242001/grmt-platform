import time

import pytest

from app.core.storage import (
    InvalidSignedUrlError,
    generate_signed_url_token,
    read_file,
    save_file,
    verify_signed_url_token,
)


def test_save_and_read_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.storage.UPLOAD_ROOT", tmp_path)
    storage_key, file_hash = save_file("sub-1", 1, "paper.pdf", b"%PDF-1.4 fake content")
    assert storage_key == "submissions/sub-1/v1/paper.pdf"
    assert len(file_hash) == 64  # sha256 hex digest

    content = read_file(storage_key)
    assert content == b"%PDF-1.4 fake content"


def test_save_file_strips_path_components_from_filename(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.storage.UPLOAD_ROOT", tmp_path)
    storage_key, _ = save_file("sub-2", 1, "../../etc/passwd", b"malicious")
    assert ".." not in storage_key
    assert storage_key == "submissions/sub-2/v1/passwd"


def test_signed_url_token_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.storage.UPLOAD_ROOT", tmp_path)
    storage_key, _ = save_file("sub-3", 1, "paper.pdf", b"content")
    token, expires_at = generate_signed_url_token(storage_key, ttl_seconds=300)
    assert expires_at > time.time()

    recovered_key = verify_signed_url_token(token)
    assert recovered_key == storage_key


def test_signed_url_token_rejects_expired_token(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.storage.UPLOAD_ROOT", tmp_path)
    storage_key, _ = save_file("sub-4", 1, "paper.pdf", b"content")
    token, _ = generate_signed_url_token(storage_key, ttl_seconds=-1)  # already expired

    with pytest.raises(InvalidSignedUrlError, match="expired"):
        verify_signed_url_token(token)


def test_signed_url_token_rejects_tampered_signature(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.storage.UPLOAD_ROOT", tmp_path)
    storage_key, _ = save_file("sub-5", 1, "paper.pdf", b"content")
    token, _ = generate_signed_url_token(storage_key, ttl_seconds=300)

    expires_at_str, signature, key = token.split(".", 2)
    tampered_token = f"{expires_at_str}.{signature}.submissions/sub-999/v1/other.pdf"

    with pytest.raises(InvalidSignedUrlError, match="signature is invalid"):
        verify_signed_url_token(tampered_token)


def test_signed_url_token_rejects_malformed_token():
    with pytest.raises(InvalidSignedUrlError, match="Malformed"):
        verify_signed_url_token("not-a-real-token")
