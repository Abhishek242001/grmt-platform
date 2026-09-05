import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_PRIVATE_KEY_PATH"] = "secrets/jwt_private.pem"
os.environ["JWT_PUBLIC_KEY_PATH"] = "secrets/jwt_public.pem"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database as database_module
from app.core.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Reassigning the module ATTRIBUTE (not a name some other module already
# imported via `from ... import SessionLocal`) — anything that accesses
# `database_module.SessionLocal()` at call time, including background tasks
# that can't use Depends(get_db), picks up the test database too. This is
# what closes the gap that `Depends(get_db)`-based overrides alone can't reach.
database_module.SessionLocal = TestingSessionLocal


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def client():
    return TestClient(app)
