#!/usr/bin/env python3
import argparse
import os
import stat

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_THIS_FILE = os.path.abspath(__file__)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
SECRETS_DIR = os.path.join(_BACKEND_DIR, "secrets")
PRIVATE_KEY_PATH = os.path.join(SECRETS_DIR, "jwt_private.pem")
PUBLIC_KEY_PATH = os.path.join(SECRETS_DIR, "jwt_public.pem")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    os.makedirs(SECRETS_DIR, exist_ok=True)

    if os.path.exists(PRIVATE_KEY_PATH) and not args.force:
        print(f"[skip] {PRIVATE_KEY_PATH} already exists — use --force to overwrite")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(private_pem)
    os.chmod(PRIVATE_KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)

    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_pem)

    print(f"[ok] wrote {PRIVATE_KEY_PATH}")
    print(f"[ok] wrote {PUBLIC_KEY_PATH}")


if __name__ == "__main__":
    main()
