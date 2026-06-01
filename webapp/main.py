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
from webapp.routers import frames, gallery, jobs, logs, settings, sky, stack, system, targets
from webapp.routers import pipeline as pipeline_router
from webapp.watcher import Watcher

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def _on_batch_ready(app: FastAPI) -> None:
    """Watcher callback: enqueue a pipeline run unless one is already pending."""
    jm: JobManager = app.state.job_manager
    store: SettingsStore = app.state.settings_store
    active = [j for j in jm.list(limit=20)
              if j.kind == "pipeline" and j.state in ("queued", "running")]
    if active:
        log.info("pipeline already %s; skipping duplicate trigger", active[0].state)
        return
    pipeline.submit_pipeline(store.get(), jm)


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

    jm = JobManager(store.get().jobs_db_path)
    jm.start()
    app.state.job_manager = jm

    watcher = Watcher(
        get_settings=store.get,
        on_batch_ready=lambda: _on_batch_ready(app),
    )
    watcher.start()
    app.state.watcher = watcher
    log.info("AstroStack web started; data_root=%s", store.get().data_root)
    try:
        yield
    finally:
        watcher.stop()
        jm.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="AstroStack", version=__import__("webapp").__version__, lifespan=lifespan)

    for r in (
        targets.router, frames.router, stack.router, jobs.router,
        pipeline_router.router, settings.router, system.router, sky.router,
        gallery.router, logs.router,
    ):
        app.include_router(r)

    _mount_spa(app)
    return app


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

    @app.get("/{full_path:path}")
    def spa(full_path: str):  # noqa: ANN202
        # API routes are already matched above; anything else → the SPA shell.
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
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
