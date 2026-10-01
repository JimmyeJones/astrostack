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
    calibration, editor, frames, gallery, glossary, incominglag, jobs, lifelist,
    logs, newsubs, overtrim, plan, sample, seestar, settings, sky, stack,
    stackfailures, stats, storage, system, targets, unstretched, updates, upload, video,
    wishlist,
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
        plan.router, upload.router, sample.router, video.router, lifelist.router,
        stackfailures.router, newsubs.router, wishlist.router, overtrim.router,
        glossary.router, incominglag.router, unstretched.router, updates.router,
    ):
        app.include_router(r)

    _install_auth_gate(app)
    _mount_spa(app)
    return app


# Paths reachable without auth even when a password is set. The Docker
# healthcheck must keep working, and the browser needs the 401 challenge itself.
_AUTH_OPEN_PATHS = frozenset({"/api/health"})

# Paths the optional **read-only token** may GET (see `webapp/auth.py`). These are
# deliberately NOT in `_AUTH_OPEN_PATHS`: they still require a credential — this
# is a narrower credential, not an open door. Opening them to the whole LAN would
# be a strictly worse trade than the problem the token solves.
#
# Exact paths, not prefixes, and only the diagnostics an observer needs: the list
# is the *whole* privilege, so it should be readable in one glance and grown
# deliberately (additively, one path at a time) rather than by a prefix that
# quietly gains whatever GET route is added under it next.
_READONLY_GET_PATHS = frozenset({
    "/api/health", "/api/logs", "/api/stats", "/api/jobs", "/api/targets",
    # Added deliberately, one path: the observer's own reason for existing is
    # that a frame which never reached the library cannot be seen to be absent
    # from the record it reads, and this is the one endpoint that answers it.
    # Read-only by construction (it compares counts and touches nothing), and it
    # names folders and numbers, never a path outside the library.
    "/api/incoming-lag",
})


# Methods that change state. A cross-site page can make a browser send any of
# these at the app with no CORS preflight (an auto-submitting <form>), so they
# are the ones the site check below guards; a GET can be embedded in an <img>
# and refusing it would gain nothing.
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_CROSS_SITE_DETAIL = (
    "This request came from another site, so AstroStack refused it. Open "
    "AstroStack in its own tab and try again.")


def _origin_host(url: str, default_port: int | None = None) -> tuple[str, int] | None:
    """``(hostname, port)`` of an ``Origin``/``Referer`` value, the port made
    explicit — from the scheme, or from ``default_port`` for a bare ``Host``
    value. ``None`` when it names no host (``null``, junk)."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url.strip())
        host, port = parts.hostname, parts.port
    except ValueError:
        return None
    if not host or parts.scheme not in ("http", "https"):
        return None
    if port is None:
        port = default_port if default_port is not None else (443 if parts.scheme == "https" else 80)
    return host.lower(), port


def _request_hosts(request, default_port: int) -> set[tuple[str, int]]:  # noqa: ANN001
    """The names this request was addressed to: ``Host``, and ``X-Forwarded-Host``
    when a reverse proxy rewrote the former. A page on another site cannot set
    the forwarded header without a preflight, so accepting it opens nothing.
    A value with no port means the port the *source's* scheme implies."""
    out: set[tuple[str, int]] = set()
    for name in ("host", "x-forwarded-host"):
        raw = request.headers.get(name)
        if not raw:
            continue
        # The first entry when a proxy chain appended its own.
        parsed = _origin_host(f"http://{raw.split(',', 1)[0].strip()}", default_port)
        if parsed:
            out.add(parsed)
    return out


def cross_site_reason(request) -> str | None:  # noqa: ANN001
    """Why a state-changing request is a cross-site one, or ``None`` to allow it.

    The app has no password by default, and a password would not help here: a
    browser resends cached Basic credentials on a cross-site form submission. So
    this is checked *before* the password, once, for every state-changing
    method, from what the browser itself says about where the request came from:

    * ``Sec-Fetch-Site`` — set by the browser and unforgeable from a page.
      ``cross-site`` is refused outright; ``same-origin`` and ``none`` (a typed
      URL, a bookmark) are allowed outright, which also keeps a reverse proxy
      that rewrites ``Host`` working; ``same-site`` falls through to the check
      below.
    * ``Origin``, else ``Referer`` — must name the host and port this request
      was addressed to (``Host``, or ``X-Forwarded-Host`` behind a proxy). Every
      browser sends ``Origin`` on a cross-site POST; ``Origin: null`` (a
      sandboxed frame) names no host and is refused.

    A request carrying none of the three — curl, the observer's scripts, the
    owner's own tooling — is allowed: that is the standard trade for an app
    whose API is also driven from a shell, and a browser never sends a
    state-changing request with none of them. (Audit 2026-09-30, C-F2.)
    """
    if request.method not in _STATE_CHANGING_METHODS:
        return None
    fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if fetch_site == "cross-site":
        return "Sec-Fetch-Site: cross-site"
    if fetch_site in ("same-origin", "none"):
        return None
    for name in ("origin", "referer"):
        raw = request.headers.get(name)
        if raw is None:
            continue
        source = _origin_host(raw)
        if source is None:
            return f"{name.title()}: {raw.strip()[:80] or '(empty)'}"
        # A bare Host means the port the source's scheme implies (80 or 443).
        implied = 443 if raw.strip().lower().startswith("https:") else 80
        if source not in _request_hosts(request, implied):
            return f"{name.title()} names {source[0]}:{source[1]}, not this app"
        return None
    return None


def _install_auth_gate(app: FastAPI) -> None:
    from starlette.responses import JSONResponse

    from webapp import auth

    @app.middleware("http")
    async def _auth_gate(request, call_next):  # noqa: ANN001
        # The site check goes first: it does not depend on whether a password is
        # set, and a cross-site request must never get as far as the password
        # check, whose answer the browser would supply for the victim.
        why = cross_site_reason(request)
        if why is not None:
            log.warning("refused a cross-site %s %s (%s)", request.method,
                        request.url.path, why)
            return JSONResponse({"detail": _CROSS_SITE_DETAIL}, status_code=403)
        store = getattr(request.app.state, "settings_store", None)
        if store is not None and request.url.path not in _AUTH_OPEN_PATHS:
            settings = store.get()
            if auth.is_enabled(settings):
                header = request.headers.get("Authorization")
                # Cost note: this only ever asks about the token when the password
                # check has already said no, so the owner's own browsing pays one
                # KDF as before and a request with no header pays none (both
                # checks refuse an absent header before hashing). A request
                # carrying the token pays two, which is fine for a diagnostics
                # poll, and a *wrong* password pays two, which is not a problem to
                # have.
                if not auth.check_basic_auth(settings, header):
                    if auth.check_readonly_auth(settings, header):
                        # A credential we recognise, on a request it may not make.
                        # 403, not 401: the caller is authenticated and retrying
                        # with the same token would be pointless, and the refusal
                        # then reads unambiguously in a log — which is the whole
                        # point of a token whose limits someone has to trust.
                        if (request.method == "GET"
                                and request.url.path in _READONLY_GET_PATHS):
                            return await call_next(request)
                        return JSONResponse(
                            {"detail": "This read-only token may only GET "
                                       "diagnostics (health, logs, stats, jobs, "
                                       "targets)."},
                            status_code=403,
                        )
                    return JSONResponse(
                        {"detail": "Authentication required"},
                        status_code=401,
                        headers={"WWW-Authenticate": 'Basic realm="AstroStack"'},
                    )
        return await call_next(request)


def _mount_spa(app: FastAPI) -> None:
    """Serve the built frontend, with an SPA fallback for client routes."""
    index = STATIC_DIR / "index.html"
    # "Is the frontend built?" is `index.html`, not the *directory*. The dir can
    # exist and be empty — `vite build` sets `emptyOutDir`, so it deletes this
    # tree before it writes it, and an interrupted build (or a half-copied image
    # layer) leaves exactly that. The old guard checked only the directory and
    # then mounted `static/assets` unconditionally, so that state raised
    # `RuntimeError: Directory '…/static/assets' does not exist` out of
    # `create_app()` and **the whole app refused to boot** — API, Settings and
    # all — over a missing *frontend*. AGENTS.md §9 asks the opposite: the
    # container must still boot. Reproduced 14 times in one run, by a pytest
    # session that happened to overlap a `vite build`.
    if not index.is_file():
        @app.get("/")
        def _placeholder() -> JSONResponse:
            return JSONResponse(
                {"message": "AstroStack API is running. Frontend not built.",
                 "docs": "/docs"}
            )
        return

    # Mounted only when it is really there. Nothing is lost if it is not: the SPA
    # catch-all below already serves any *file* under the static root, so a build
    # that emitted its chunks elsewhere still works — just without the mount's
    # own caching path.
    if (STATIC_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
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
