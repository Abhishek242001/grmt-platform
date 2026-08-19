from app.core.security import create_access_token, decode_token, hash_password, verify_password


def test_password_hash_is_not_plaintext():
    hashed = hash_password("mysecretpassword")
    assert hashed != "mysecretpassword"
    assert hashed.startswith("$argon2")  # Argon2id, per development_rule.md §6.3


def test_password_verify_succeeds_for_correct_password():
    hashed = hash_password("correcthorsebattery")
    assert verify_password("correcthorsebattery", hashed) is True


def test_password_verify_fails_for_wrong_password():
    hashed = hash_password("correcthorsebattery")
    assert verify_password("wrongpassword", hashed) is False


def test_jwt_roundtrip_preserves_claims():
    token = create_access_token(user_id="user-123", role="researcher")
    decoded = decode_token(token)
    assert decoded["sub"] == "user-123"
    assert decoded["role"] == "researcher"
    assert decoded["type"] == "access"


def test_jwt_is_rs256_not_hs256():
    """development_rule.md §6.3 — RS256 specifically, not HS256."""
    import jose.jwt as jose_jwt

    token = create_access_token(user_id="user-456", role="organizer")
    header = jose_jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"


def test_no_router_logs_a_raw_password():
    """
    development_rule.md §3.3 — passwords must never be logged. This is a
    static-analysis tripwire: it scans every router source file for a
    `log.` call whose arguments reference `password` (excluding the word
    `password_hash`, which is safe to log — it's not a secret). If someone
    adds `log.info(req_id, f"... {payload.password} ...")` in the future,
    this test fails and catches it before it ships.
    """
    import re
    from pathlib import Path

    routers_dir = Path(__file__).parent.parent / "app" / "routers"
    violations = []
    for py_file in routers_dir.glob("*.py"):
        text = py_file.read_text()
        for match in re.finditer(r"log\.(info|warn|error)\([^)]*\)", text, re.DOTALL):
            call_text = match.group(0)
            if re.search(r"\bpassword\b", call_text) and "password_hash" not in call_text:
                violations.append(f"{py_file.name}: {call_text[:120]}")
    assert not violations, f"Found log calls referencing raw password: {violations}"
