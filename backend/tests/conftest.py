import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_grmt.db")
os.environ.setdefault("LOG_FILE_PATH", "./test_log.txt")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.config import get_settings
import app.models  # noqa: F401 — register all models on Base.metadata


@pytest.fixture(scope="function")
def db_engine(tmp_path):
    """Fresh SQLite file per test function — fully isolated, no cross-test state."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_engine):
    from app.main import app

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def signup_and_login(client, email="user@example.com", password="testpass123", role="researcher", name="Test User"):
    client.post("/api/auth/signup", json={"email": email, "password": password, "role": role, "name": name})
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
