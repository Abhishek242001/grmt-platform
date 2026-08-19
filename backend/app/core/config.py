"""
GRMT backend settings.

Loaded from environment variables / .env at process startup. See
.env.example at the repo root for the full list of variables and
development_rule.md §6.3 for the secrets-management rules that apply here
(never commit real values; RS256 keys are files referenced by path, not
inlined).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    # Defaults to a local SQLite file so `pytest` and local dev work with zero
    # external services. Point DATABASE_URL at Postgres for anything beyond
    # local smoke-testing — see docker-compose.yml at the repo root.
    database_url: str = "sqlite:///./grmt_dev.db"

    # --- Auth / JWT (RS256 per development_rule.md §6.3) ---
    jwt_private_key_path: str = "./secrets/jwt_private.pem"
    jwt_public_key_path: str = "./secrets/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 14  # 14 days

    # --- App ---
    environment: str = "development"
    log_file_path: str = "../log.txt"  # repo-root log.txt, see development_rule.md §3
    cors_allow_origins: str = "http://localhost:3000"

    # --- External AI services (URLs — see development_rule.md §1.3) ---
    languagetool_url: str = "http://localhost:8010"
    grobid_url: str = "http://localhost:8070"
    embeddings_service_url: str = "http://localhost:8001"
    gpu_inference_service_url: str = "http://localhost:8002"
    ollama_url: str = "http://localhost:11434"

    # --- Storage (signed-URL streaming for PDFs, development_rule.md §6.4) ---
    storage_encryption_key: str = "CHANGE_ME_32_BYTE_KEY_xxxxxxxxxx"
    pdf_signed_url_ttl_seconds: int = 300  # 5 minutes, per development_rule.md §6.4


@lru_cache
def get_settings() -> Settings:
    return Settings()
