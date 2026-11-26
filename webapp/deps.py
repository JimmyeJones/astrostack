"""FastAPI dependencies — fetch shared singletons off ``app.state``.

The singletons (settings store, job manager, library handle factory) are
created in the app lifespan (see :mod:`webapp.main`).
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from seestack.io.library import Library
from seestack.io.project import Project
from webapp.config import Settings, SettingsStore
from webapp.jobs import JobManager


def get_settings_store(request: Request) -> SettingsStore:
    return request.app.state.settings_store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings_store.get()


def refuse_on_unsafe_layout(settings: Settings) -> None:
    """409 while the install sits in the unsafe nested folder layout.

    ``SettingsStore.update`` refuses to *enter* that layout, but an install that
    reached it earlier still boots (§9) — and there the library's own, correctly
    scoped deletes resolve inside ``incoming/``: with ``incoming/`` under
    ``library/targets`` the scan adopts each raw folder as a target's project
    folder and "Delete target, remove files" ``rmtree``s the raws (full audit
    2026-11-26, backend.md finding 9). Booting is fine; deleting is not
    (AGENTS.md §10). Called by every endpoint that removes files under the
    library, and by the scan.
    """
    conflict = settings.layout_conflict()
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail=("Stopped to protect your raw frames. " + conflict
                    + " Until the folders are fixed in Settings, the app won't "
                    "delete, merge, clear or scan anything."),
        )


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def get_seestar_manager(request: Request):
    """The Seestar device manager (created in the app lifespan)."""
    return request.app.state.seestar_manager


def open_library(request: Request) -> Library:
    """Open the library. Caller MUST close it."""
    settings = request.app.state.settings_store.get()
    return Library.open_or_create(settings.resolved_library_root)


def open_target_project(request: Request, safe: str) -> tuple[Library, Project]:
    """Open (library, project) for ``safe``. Caller closes both. 404 if missing."""
    lib = open_library(request)
    try:
        entry = lib.find_target(safe)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"No target '{safe}'")
        proj = Project.open(lib.target_dir(entry))
    except BaseException:
        lib.close()  # don't leak the library if lookup/open fails
        raise
    return lib, proj
