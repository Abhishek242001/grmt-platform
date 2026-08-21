from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.core.logging_utils import configure_logging, get_logger
from app.models import core as _models_core  # noqa: F401
from app.models import conferences as _models_conferences  # noqa: F401
from app.models import submissions as _models_submissions  # noqa: F401
from app.routers import auth, conferences, submissions, reviews, analytics, files, ws

configure_logging()
logger = get_logger("grmt.main")

# Dev convenience only — real environments migrate through Alembic (backend/alembic/),
# never through create_all().
if settings.environment == "development":
    Base.metadata.create_all(bind=engine)
    logger.info("dev mode: Base.metadata.create_all() ran against %s", settings.database_url)

app = FastAPI(title="GRMT API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(conferences.router)
app.include_router(submissions.router)
app.include_router(reviews.router)
app.include_router(analytics.router)
app.include_router(files.router)
app.include_router(ws.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
