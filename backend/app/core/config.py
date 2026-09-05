from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./grmt_dev.db"
    cors_allow_origins: str = "http://localhost:3000"

    jwt_private_key_path: str = "secrets/jwt_private.pem"
    jwt_public_key_path: str = "secrets/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # Signs short-lived PDF-viewing URLs — separate from JWT signing so file-URL
    # tokens and login tokens are independently rotatable.
    file_signing_secret: str = "dev-only-change-in-production"
    signed_url_expire_seconds: int = 300

    # Phase 2 — AI checks
    languagetool_url: str = "http://localhost:8010/v2/check"
    upload_root: str = "uploads"  # relative to backend/, real .docx bytes land here

    # Admin panel (update44) — encrypts external plagiarism-provider API keys
    # at rest. Deliberately separate from file_signing_secret/JWT keys, same
    # reasoning as those already being independently rotatable from each
    # other — an encryption-key rotation here shouldn't force a JWT or
    # signed-URL rotation, and vice versa.
    api_key_encryption_secret: str = "dev-only-change-in-production-admin-keys"

    log_level: str = "INFO"
    log_file: str = "../log.txt"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
