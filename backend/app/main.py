import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.core.logging_utils import configure_logging, get_logger
from app.core.system_metrics import collect_metrics
from app.core.ws_manager import get_manager
from app.models import core as _models_core  # noqa: F401
from app.models import conferences as _models_conferences  # noqa: F401
from app.models import submissions as _models_submissions  # noqa: F401
from app.models import admin as _models_admin  # noqa: F401
from app.routers import auth, conferences, submissions, reviews, analytics, files, ws, admin

configure_logging()
logger = get_logger("grmt.main")

# Dev convenience only — real environments migrate through Alembic (backend/alembic/),
# never through create_all().
if settings.environment == "development":
    Base.metadata.create_all(bind=engine)
    logger.info("dev mode: Base.metadata.create_all() ran against %s", settings.database_url)

# How often the admin panel's real-time hardware dashboard refreshes
# (update44). 2s is frequent enough to feel "live" without hammering
# nvidia-smi (a subprocess spawn, not a free call) on every tick.
_METRICS_BROADCAST_INTERVAL_SECONDS = 2


async def _broadcast_system_metrics_loop():
    """Runs for the lifetime of the app process — publishes real hardware
    metrics to the "admin:system-metrics" WS channel (already
    authorization-gated to platform_admin in ws.py's _authorize_channel)
    on a fixed interval. publish() itself no-ops cheaply when nobody's
    subscribed (see ws_manager.py), so this costs nothing when no admin
    has the dashboard open — collect_metrics() still runs every tick
    regardless, which is a deliberate, cheap trade-off (keeps the disk/
    network rate-tracking state in system_metrics.py continuously warmed
    up, rather than producing a misleading first-sample-is-always-zero
    read the moment an admin opens the dashboard)."""
    manager = get_manager()
    while True:
        try:
            metrics = collect_metrics()
            await manager.publish("admin:system-metrics", {"type": "system_metrics", "data": metrics})
        except Exception:
            logger.exception("system metrics broadcast tick failed — will retry next interval")
        await asyncio.sleep(_METRICS_BROADCAST_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Gated the same way create_all() above is — conftest.py sets
    # ENVIRONMENT=test before importing this module, specifically so this
    # background task never starts during the test suite. Untested-by-me
    # interaction between a long-lived asyncio task and TestClient's
    # lifespan handling (fastapi/starlette aren't installable in the
    # sandbox this was written in — no network) is a real risk worth
    # closing conservatively rather than assuming away.
    task = None
    if settings.environment != "test":
        task = asyncio.create_task(_broadcast_system_metrics_loop())
    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="GRMT API", version="0.1.0", lifespan=lifespan)

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
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
