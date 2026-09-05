from app.core.key_encryption import decrypt_api_key, encrypt_api_key, mask_api_key


def test_encrypt_decrypt_round_trip():
    original = "sk-gptzero-real-key-abc123xyz789"
    encrypted = encrypt_api_key(original)
    assert encrypted != original
    assert decrypt_api_key(encrypted) == original


def test_encrypted_value_never_contains_plaintext_substring():
    original = "winston-secret-token-DO-NOT-LEAK"
    encrypted = encrypt_api_key(original)
    assert "winston-secret-token" not in encrypted
    assert "DO-NOT-LEAK" not in encrypted


def test_mask_shows_only_last_four_characters():
    masked = mask_api_key("sk-gptzero-real-key-abc123xyz789")
    assert masked.endswith("z789")
    assert "sk-gptzero" not in masked
    assert "real-key" not in masked


def test_mask_very_short_key_is_fully_masked():
    masked = mask_api_key("abc")
    assert masked == "***"
    assert "abc" not in masked


def test_multiple_encryptions_of_same_key_both_decrypt_correctly():
    """Fernet includes a random nonce per encryption, so ciphertexts for
    the same plaintext differ — confirms that's harmless, both still
    decrypt back to the original."""
    plaintext = "same-key-encrypted-twice"
    e1 = encrypt_api_key(plaintext)
    e2 = encrypt_api_key(plaintext)
    assert decrypt_api_key(e1) == plaintext
    assert decrypt_api_key(e2) == plaintext
