from unittest.mock import Mock, patch

import httpx

from app.ai.winston_plagiarism_client import (
    WinstonApiError,
    build_request_payload,
    call_winston_plagiarism_api,
    parse_winston_response,
    run_winston_plagiarism_check,
    validate_text_length,
)

# A real, substantial text sample — well within Winston's 100-120,000 char bounds.
_SAMPLE_TEXT = "Industrial IoT deployments generate high-volume sensor streams. " * 5  # ~450 chars


# ── validate_text_length — pure, real constraint from Winston's own docs ──

def test_text_within_bounds_passes():
    validate_text_length(_SAMPLE_TEXT)  # should not raise


def test_text_too_short_raises():
    try:
        validate_text_length("too short")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "at least" in str(e)


def test_text_too_long_raises():
    too_long = "a" * 120_001
    try:
        validate_text_length(too_long)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "120" in str(e)
        assert "chunk" in str(e).lower()  # confirms the guidance note is present, not just a bare number


def test_exactly_at_minimum_boundary_passes():
    validate_text_length("a" * 100)


def test_exactly_at_maximum_boundary_passes():
    validate_text_length("a" * 120_000)


def test_one_under_minimum_fails():
    try:
        validate_text_length("a" * 99)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_one_over_maximum_fails():
    try:
        validate_text_length("a" * 120_001)
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── build_request_payload — pure ──

def test_build_payload_default_language_is_auto():
    payload = build_request_payload(_SAMPLE_TEXT)
    assert payload["text"] == _SAMPLE_TEXT
    assert payload["language"] == "auto"
    assert "excluded_sources" not in payload  # omitted, not sent as empty/null, when not given


def test_build_payload_includes_excluded_sources_when_given():
    payload = build_request_payload(_SAMPLE_TEXT, excluded_sources=["example.com"])
    assert payload["excluded_sources"] == ["example.com"]


def test_build_payload_custom_language():
    payload = build_request_payload(_SAMPLE_TEXT, language="fr")
    assert payload["language"] == "fr"


# ── parse_winston_response — pure, using Winston's REAL published schema ──

def _real_shaped_winston_response(score=27.0, credits_used=200, credits_remaining=1800):
    """Mirrors the exact field names/nesting from Winston's own published
    OpenAPI schema (docs.gowinston.ai/api-reference/v2/plagiarism/post),
    not an invented shape."""
    return {
        "status": 200,
        "scanInformation": {"service": "plagiarism", "scanTime": "2026-09-04T00:00:00Z", "inputType": "text", "language": "en"},
        "result": {
            "score": score,
            "sourceCounts": 2,
            "textWordCounts": 100,
            "totalPlagiarismWords": 27,
            "identicalWordCounts": 20,
            "similarWordCounts": 7,
        },
        "sources": [
            {
                "score": 18.0,
                "canAccess": True,
                "url": "https://example.com/paper-a",
                "title": "A Prior Paper On The Same Topic",
                "plagiarismWords": 18,
                "identicalWordCounts": 15,
                "similarWordCounts": 3,
                "totalNumberOfWords": 100,
                "author": "Jane Doe",
                "description": None,
                "publishedDate": None,
                "source": None,
                "citation": False,
                "plagiarismFound": [
                    {"startIndex": 10, "endIndex": 45, "sequence": "a matched passage of real text here"},
                ],
                "is_excluded": False,
            },
            {
                "score": 9.0,
                "canAccess": True,
                "url": "https://example.com/paper-b",
                "title": "Another Source",
                "plagiarismWords": 9,
                "identicalWordCounts": 9,
                "similarWordCounts": 0,
                "totalNumberOfWords": 100,
                "author": None,
                "description": None,
                "publishedDate": None,
                "source": None,
                "citation": True,
                "plagiarismFound": [],
                "is_excluded": False,
            },
        ],
        "attackDetected": {"zero_width_space": False, "homoglyph_attack": False},
        "text": _SAMPLE_TEXT,
        "similarWords": [],
        "citations": ["https://example.com/paper-b"],
        "indexes": [],
        "credits_used": credits_used,
        "credits_remaining": credits_remaining,
    }


def test_parse_extracts_overall_score():
    result = parse_winston_response(_real_shaped_winston_response(score=27.0))
    assert result["overall_similarity_pct"] == 27.0


def test_parse_extracts_credits_info():
    result = parse_winston_response(_real_shaped_winston_response(credits_used=200, credits_remaining=1800))
    assert result["credits_used"] == 200
    assert result["credits_remaining"] == 1800


def test_parse_extracts_per_source_matches_sorted_by_similarity():
    result = parse_winston_response(_real_shaped_winston_response())
    assert len(result["matches"]) == 2
    assert result["matches"][0]["source_url"] == "https://example.com/paper-a"
    assert result["matches"][0]["similarity_pct"] == 18.0
    assert result["matches"][1]["similarity_pct"] == 9.0


def test_parse_extracts_matched_spans_with_char_offsets():
    result = parse_winston_response(_real_shaped_winston_response())
    spans = result["matches"][0]["matched_spans"]
    assert len(spans) == 1
    assert spans[0]["start_char"] == 10
    assert spans[0]["end_char"] == 45
    assert spans[0]["text"] == "a matched passage of real text here"


def test_parse_surfaces_can_access_flag_per_source():
    """update50 — confirms canAccess is captured, not silently dropped.
    Both fixture sources have canAccess: True; the inaccessible-source
    case is covered separately below."""
    result = parse_winston_response(_real_shaped_winston_response())
    assert result["matches"][0]["can_access"] is True
    assert result["matches"][1]["can_access"] is True


def test_inaccessible_source_can_score_zero_with_can_access_false():
    """The specific real-world scenario this field exists to explain: a
    source Winston found and listed (a real candidate) but could not fetch
    full text for — canAccess: False, score: 0 — must be distinguishable
    from a source that was genuinely compared and found dissimilar."""
    raw = _real_shaped_winston_response()
    raw["sources"][0]["canAccess"] = False
    raw["sources"][0]["score"] = 0.0
    result = parse_winston_response(raw)

    inaccessible_match = result["matches"][1]  # was sorted second after the zero-score edit
    assert inaccessible_match["source_url"] == "https://example.com/paper-a"
    assert inaccessible_match["similarity_pct"] == 0.0
    assert inaccessible_match["can_access"] is False


def test_parse_excludes_sources_marked_is_excluded():
    raw = _real_shaped_winston_response()
    raw["sources"][1]["is_excluded"] = True
    result = parse_winston_response(raw)
    assert len(result["matches"]) == 1
    assert result["matches"][0]["source_url"] == "https://example.com/paper-a"


def test_parse_handles_zero_sources_cleanly():
    raw = _real_shaped_winston_response()
    raw["sources"] = []
    result = parse_winston_response(raw)
    assert result["matches"] == []


# ── call_winston_plagiarism_api — mocked network layer (real network call is genuinely untestable here) ──

def test_call_api_success_returns_raw_json():
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = _real_shaped_winston_response()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = call_winston_plagiarism_api("fake-api-key", _SAMPLE_TEXT)

    assert result["result"]["score"] == 27.0
    # Confirms the real, documented auth header shape was actually used.
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer fake-api-key"


def test_call_api_401_raises_with_real_error_shape():
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.json.return_value = {
        "error": "UNAUTHORIZED",
        "description": "Pass a valid API key in the Authorization header as a Bearer token.",
    }

    with patch("httpx.post", return_value=mock_response):
        try:
            call_winston_plagiarism_api("bad-key", _SAMPLE_TEXT)
            assert False, "expected WinstonApiError"
        except WinstonApiError as e:
            assert e.status_code == 401
            assert e.error_code == "UNAUTHORIZED"


def test_call_api_402_insufficient_credits_raises_with_real_error_shape():
    """The realistic failure mode given the free tier's 2,000-credit
    budget — confirms this is caught and surfaced clearly, not as a
    generic crash."""
    mock_response = Mock()
    mock_response.status_code = 402
    mock_response.json.return_value = {
        "error": "PAYMENT_REQUIRED",
        "description": "Insufficient credits. Make sure you have enough credits to make the request.",
    }

    with patch("httpx.post", return_value=mock_response):
        try:
            call_winston_plagiarism_api("fake-key", _SAMPLE_TEXT)
            assert False, "expected WinstonApiError"
        except WinstonApiError as e:
            assert e.status_code == 402
            assert e.error_code == "PAYMENT_REQUIRED"


def test_call_api_validates_length_before_making_network_call():
    """Confirms the length check runs BEFORE the network call — a request
    that would fail Winston's own validation shouldn't consume the
    network round-trip (or, on a real account, credits) just to find that out."""
    with patch("httpx.post") as mock_post:
        try:
            call_winston_plagiarism_api("fake-key", "too short")
            assert False, "expected ValueError"
        except ValueError:
            pass
    mock_post.assert_not_called()


# ── run_winston_plagiarism_check — orchestrator, mocked ──

def test_orchestrator_success_path():
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = _real_shaped_winston_response(score=27.0)

    with patch("httpx.post", return_value=mock_response):
        result = run_winston_plagiarism_check("fake-key", _SAMPLE_TEXT)

    assert result["status"] == "complete"
    assert result["overall_similarity_pct"] == 27.0
    assert "response_time_ms" in result


def test_orchestrator_error_path_returns_clean_error_shape_not_raise():
    mock_response = Mock()
    mock_response.status_code = 402
    mock_response.json.return_value = {"error": "PAYMENT_REQUIRED", "description": "Insufficient credits."}

    with patch("httpx.post", return_value=mock_response):
        result = run_winston_plagiarism_check("fake-key", _SAMPLE_TEXT)

    assert result["status"] == "error"
    assert result["error_code"] == "PAYMENT_REQUIRED"


def test_orchestrator_text_too_short_returns_clean_error_no_network_call():
    with patch("httpx.post") as mock_post:
        result = run_winston_plagiarism_check("fake-key", "too short")

    assert result["status"] == "error"
    assert result["error_code"] == "TEXT_LENGTH_INVALID"
    mock_post.assert_not_called()


def test_orchestrator_connection_failure_returns_clean_error_not_raise():
    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        result = run_winston_plagiarism_check("fake-key", _SAMPLE_TEXT)

    assert result["status"] == "error"
    assert result["error_code"] == "REQUEST_FAILED"
