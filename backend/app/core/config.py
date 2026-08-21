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

    log_level: str = "INFO"
    log_file: str = "../log.txt"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
