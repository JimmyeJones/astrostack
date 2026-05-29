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


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def open_library(request: Request) -> Library:
    """Open the library. Caller MUST close it."""
    settings = request.app.state.settings_store.get()
    return Library.open_or_create(settings.resolved_library_root)


def open_target_project(request: Request, safe: str) -> tuple[Library, Project]:
    """Open (library, project) for ``safe``. Caller closes both. 404 if missing."""
    lib = open_library(request)
    entry = lib.find_target(safe)
    if entry is None:
        lib.close()
        raise HTTPException(status_code=404, detail=f"No target '{safe}'")
    proj = Project.open(lib.target_dir(entry))
    return lib, proj
