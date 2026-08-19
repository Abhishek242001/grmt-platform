from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import admin, auth, conferences, files, submissions

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB schema is owned by Alembic migrations (backend/alembic/) — see
    # development_rule.md §4 and README "Database setup". We deliberately do
    # NOT call Base.metadata.create_all() here: once migrations exist, that
    # call would mask a forgotten migration by quietly creating the missing
    # table instead of failing loudly. Run `alembic upgrade head` before
    # starting the app.
    import app.models  # noqa: F401 — ensure every model is registered, useful for tooling/tests that import app.main directly

    yield


app = FastAPI(
    title="Gudsky Research Management Tool (GRMT) API",
    description="AI-powered conference & paper management system — backend API.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(conferences.router, prefix="/api")
app.include_router(submissions.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(files.router, prefix="/api")


@app.get("/api/health")
def health():
    """development_rule.md §2.3 — one-call health check for backend + admin panel."""
    return {"status": "ok", "service": "grmt-backend"}
