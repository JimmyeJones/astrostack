"""FastAPI application entry point.

Lifespan wiring:
  * create the SettingsStore (reads/writes config.json in the dataset),
  * create + start the JobManager (single worker thread),
  * create + start the Watcher (auto-runs the pipeline on new files).

The built React SPA (if present in ``webapp/static``) is served at ``/`` with an
SPA fallback so client-side routes work on refresh.
"""

from __future__ import annotations

import contextlib
import logging
import multiprocessing
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from webapp import logbuffer, pipeline
from webapp.config import SettingsStore
from webapp.jobs import JobManager
from webapp.routers import (
    auth as auth_router,
    calibration, editor, frames, gallery, jobs, logs, plan, seestar, settings, sky,
    stack, stats, storage, system, targets,
)
from webapp.routers import pipeline as pipeline_router
from webapp.seestar.manager import SeestarManager
from webapp.watcher import Watcher

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def _on_batch_ready(app: FastAPI) -> bool:
    """Watcher callback: enqueue a pipeline run unless one is already active.

    Returns ``True`` when a pipeline was enqueued (the batch was consumed), or
    ``False`` when one is already queued/running. On ``False`` the watcher keeps
    the batch pending and re-offers it on a later poll, so files that stabilise
    while a prior pipeline is mid-run are still picked up once it finishes —
    rather than being silently dropped forever (the running pipeline scanned
    before they existed, and the stability tracker never re-offers them).
    """
    jm: JobManager = app.state.job_manager
    store: SettingsStore = app.state.settings_store
    # Use the unbounded in-memory `active_of_kind` rather than scanning `list()`:
    # `list(limit=N)` merges live + DB jobs, sorts by created_utc, and truncates,
    # so a long-running pipeline (old created_utc) can be pushed past the window
    # once N newer jobs exist — making the guard miss it and enqueue a duplicate.
    active = jm.active_of_kind("pipeline")
    if active is not None:
        log.info("pipeline already %s; deferring trigger", active.state)
        return False
    job = pipeline.submit_pipeline(store.get(), jm)
    # Remember which pipeline is responsible for importing this batch so a later
    # poll can re-offer the batch if that pipeline *fails before ingesting* (see
    # `_stranded_batch_needs_retry`). Mark the job as a recovery retry when this
    # enqueue is itself the re-offer, so a persistently-failing pipeline can be
    # retried at most once and never loops.
    st = app.state
    st.watcher_pipeline_id = job.id
    st.watcher_pipeline_is_recovery = getattr(st, "watcher_recovery_next", False)
    st.watcher_recovery_next = False
    return True


def _stranded_batch_needs_retry(app: FastAPI) -> bool:
    """Watcher hook: True when the last auto-ingest pipeline failed before importing.

    When ``_on_batch_ready`` enqueues a pipeline it treats the batch as consumed
    (the stability tracker won't re-offer those files). If that pipeline then
    *errors before it ingests* — a scan/QC crash, an OOM refusal — the
    newly-stable files stay unimported in ``incoming/`` with nothing to re-trigger
    them until another file arrives or the user manually scans. This lets the
    watcher re-offer the batch once: enqueuing a fresh pipeline re-scans the whole
    incoming dir (idempotently), so the stranded files get imported.

    Bounded to a single retry per strand — a pipeline enqueued *as* a recovery is
    flagged, so a persistently-failing pipeline can't loop. Only a genuine
    ``error`` re-offers; a user ``cancel`` (deliberate) is left alone.
    """
    jm: JobManager = app.state.job_manager
    st = app.state
    pid = getattr(st, "watcher_pipeline_id", None)
    if pid is None:
        return False
    if jm.active_of_kind("pipeline") is not None:
        return False  # a pipeline is running; let it finish before deciding
    job = jm.get(pid)
    if job is None or job.state != "error":
        return False  # succeeded, cancelled by the user, or no longer known
    if getattr(st, "watcher_pipeline_is_recovery", False):
        return False  # this failure was already a retry — don't loop
    st.watcher_recovery_next = True
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=os.environ.get("ASTROSTACK_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Capture logs into an in-memory ring buffer, surfaced at /api/logs so the
    # cause of a crash/error is visible in the app, not just in docker logs.
    logbuffer.install()
    # spawn keeps ProcessPoolExecutor behavior consistent across base images.
    with contextlib.suppress(RuntimeError):
        multiprocessing.set_start_method("spawn", force=True)

    store = SettingsStore()
    app.state.settings_store = store

    jm = JobManager(store.get().jobs_db_path,
                    max_history=store.get().job_history_limit)
    jm.start()
    app.state.job_manager = jm

    watcher = Watcher(
        get_settings=store.get,
        on_batch_ready=lambda: _on_batch_ready(app),
        on_check_stranded=lambda: _stranded_batch_needs_retry(app),
    )
    watcher.start()
    app.state.watcher = watcher

    seestar_mgr = SeestarManager(get_settings=store.get)
    seestar_mgr.start()
    app.state.seestar_manager = seestar_mgr

    log.info("AstroStack web started; data_root=%s", store.get().data_root)
    try:
        yield
    finally:
        seestar_mgr.stop()
        watcher.stop()
        jm.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="AstroStack", version=__import__("webapp").__version__, lifespan=lifespan)

    for r in (
        targets.router, frames.router, stack.router, jobs.router,
        pipeline_router.router, settings.router, system.router, sky.router,
        gallery.router, logs.router, stats.router, storage.router,
        seestar.router, editor.router, calibration.router, auth_router.router,
        plan.router,
    ):
        app.include_router(r)

    _install_auth_gate(app)
    _mount_spa(app)
    return app


# Paths reachable without auth even when a password is set. The Docker
# healthcheck must keep working, and the browser needs the 401 challenge itself.
_AUTH_OPEN_PATHS = frozenset({"/api/health"})


def _install_auth_gate(app: FastAPI) -> None:
    from starlette.responses import JSONResponse

    from webapp import auth

    @app.middleware("http")
    async def _auth_gate(request, call_next):  # noqa: ANN001
        store = getattr(request.app.state, "settings_store", None)
        if store is not None and request.url.path not in _AUTH_OPEN_PATHS:
            settings = store.get()
            if auth.is_enabled(settings) and not auth.check_basic_auth(
                settings, request.headers.get("Authorization")
            ):
                return JSONResponse(
                    {"detail": "Authentication required"},
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="AstroStack"'},
                )
        return await call_next(request)


def _mount_spa(app: FastAPI) -> None:
    """Serve the built frontend, with an SPA fallback for client routes."""
    if not STATIC_DIR.exists():
        @app.get("/")
        def _placeholder() -> JSONResponse:
            return JSONResponse(
                {"message": "AstroStack API is running. Frontend not built.",
                 "docs": "/docs"}
            )
        return

    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    index = STATIC_DIR / "index.html"
    static_root = STATIC_DIR.resolve()

    @app.get("/{full_path:path}")
    def spa(full_path: str):  # noqa: ANN202
        # API routes are already matched above; anything else → the SPA shell.
        # Confine the resolved candidate to the static root: Starlette decodes
        # percent-encoded "../" (``%2e%2e``) into ``full_path`` *after* routing,
        # so without this an unauthenticated request could escape STATIC_DIR and
        # read arbitrary files (e.g. ``/%2e%2e/%2e%2e/etc/passwd``). A path that
        # escapes the root falls through to the SPA shell, same as any unknown
        # client route.
        candidate = (STATIC_DIR / full_path).resolve()
        if (
            full_path
            and candidate.is_relative_to(static_root)
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "webapp.main:app",
        host=os.environ.get("ASTROSTACK_HOST", "0.0.0.0"),
        port=int(os.environ.get("ASTROSTACK_PORT", "8000")),
        workers=1,
    )


if __name__ == "__main__":
    run()
