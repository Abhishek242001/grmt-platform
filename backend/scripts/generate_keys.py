"""
Generate the RS256 keypair used to sign/verify JWTs — development_rule.md
§6.3. Run this once per environment and point .env's JWT_PRIVATE_KEY_PATH /
JWT_PUBLIC_KEY_PATH at the output files. Without this, app/core/security.py
falls back to an ephemeral in-memory keypair (fine for a single pytest run,
NOT fine for anything that needs tokens to survive a process restart).

Usage:
    python scripts/generate_keys.py
    python scripts/generate_keys.py --out-dir ./secrets
"""
import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="./secrets")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    priv_path = out_dir / "jwt_private.pem"
    pub_path = out_dir / "jwt_public.pem"

    if priv_path.exists() or pub_path.exists():
        print(f"[SKIP] Keys already exist at {out_dir} — delete them first if you really want to rotate.")
        print("       Rotating invalidates every currently-issued token immediately.")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    priv_path.chmod(0o600)  # private key readable only by the owner

    print(f"[OK] Wrote {priv_path} and {pub_path}")
    print(f"[ACTION REQUIRED] Set these in your .env:")
    print(f"    JWT_PRIVATE_KEY_PATH={priv_path}")
    print(f"    JWT_PUBLIC_KEY_PATH={pub_path}")
    print("Do NOT commit these files — .gitignore already excludes secrets/.")


if __name__ == "__main__":
    main()
