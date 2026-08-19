"""
SQLAlchemy engine & session factory.

Backend-agnostic on purpose: models avoid Postgres-only column types
(JSONB, native ARRAY, pgcrypto's gen_random_uuid()) so the exact same
models/migrations work against the SQLite dev default (DATABASE_URL unset)
and against Postgres in every other environment (docker-compose, Lightning
Studio dev backend, Render/Railway production — see the master build
document §2.2.5 / §4). UUIDs are generated application-side with Python's
uuid4() rather than a database function, which is portable across both.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
