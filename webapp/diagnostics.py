"""Run the shipped library diagnostics once each, and keep their results.

The questions live in :mod:`seestack.diag`; this module decides *when* they run
and *where* the answers go. After every boot, any diagnostic whose
``(name, version)`` has no stored result is queued as one ordinary job of kind
``"diagnostics"`` — serialised with stacks by the single worker, cancellable
from the Jobs page, and never run twice for the same version. Results are JSON
under ``state/diagnostics/`` and are served by ``GET /api/diagnostics``, which
the observer's read-only token may read (``webapp.main._READONLY_GET_PATHS``).

Nothing here writes outside ``state/diagnostics/``, and the diagnostics
themselves are read-only by contract (:mod:`seestack.diag`).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from seestack.diag import Diagnostic, DiagnosticStopped, check_result_is_safe, registry
from webapp.config import Settings

log = logging.getLogger(__name__)

JOB_KIND = "diagnostics"


def results_dir(settings: Settings) -> Path:
    return settings.state_dir / "diagnostics"


def _result_path(settings: Settings, d: Diagnostic) -> Path:
    return results_dir(settings) / f"{d.name}-v{d.version}.json"


def pending(settings: Settings) -> list[Diagnostic]:
    """Diagnostics with no stored result for their current version."""
    return [d for d in registry() if not _result_path(settings, d).exists()]


def _write(settings: Settings, d: Diagnostic, payload: dict[str, Any]) -> None:
    out = _result_path(settings, d)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.part")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, out)


def run_one(settings: Settings, d: Diagnostic, *, progress=None, should_stop=None
            ) -> dict[str, Any]:
    """Run ``d`` against the library and store the outcome — a result, or the
    reason it failed (stored too, so a diagnostic that cannot run on this
    install is reported once rather than retried at every boot)."""
    from seestack.io.library import Library

    started = time.time()
    payload: dict[str, Any] = {
        "name": d.name, "version": d.version, "question": d.question,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
    }
    try:
        from webapp import __version__ as app_version
        payload["app_version"] = app_version
    except Exception:  # noqa: BLE001
        pass
    lib = Library.open_or_create(settings.resolved_library_root)
    try:
        result = d.run(lib, progress=progress, should_stop=should_stop)
        check_result_is_safe(result)
        payload.update(status="done", result=result)
    except DiagnosticStopped:
        raise
    except Exception as exc:  # noqa: BLE001 — recorded, never fatal
        log.warning("diagnostic %s v%s failed", d.name, d.version, exc_info=True)
        # The exception's class only: its message can carry a path.
        payload.update(status="error", error=type(exc).__name__)
    finally:
        lib.close()
    payload["seconds"] = round(time.time() - started, 1)
    _write(settings, d, payload)
    return payload


def ready_to_run(settings: Settings) -> list[Diagnostic]:
    """Pending diagnostics whose ``ready`` check passes on this library."""
    from seestack.io.library import Library

    todo = pending(settings)
    if not todo:
        return []
    lib = Library.open_or_create(settings.resolved_library_root)
    try:
        out = []
        for d in todo:
            try:
                if d.ready is None or d.ready(lib):
                    out.append(d)
            except Exception:  # noqa: BLE001 — a broken check skips that one
                log.warning("diagnostic %s readiness check failed", d.name, exc_info=True)
        return out
    finally:
        lib.close()


def submit_pending_diagnostics(settings: Settings, jm) -> Any:  # noqa: ANN001 — JobManager
    """Queue one job that runs every pending, ready diagnostic — the boot-time
    call from :func:`webapp.main.lifespan`. ``None`` when nothing is ready or a
    run is already queued or running."""
    if jm.active_of_kind(JOB_KIND):
        return None
    todo = ready_to_run(settings)
    if not todo:
        return None

    def body(job) -> dict[str, Any]:  # noqa: ANN001
        ran = []
        for i, d in enumerate(todo):
            def progress(phase: str, done: int, total: int, _i=i, _d=d) -> None:
                job.set_progress(phase, done, total,
                                 f"{_d.name} ({_i + 1}/{len(todo)}): {done}/{total}")
            try:
                out = run_one(settings, d, progress=progress,
                              should_stop=job.cancel_requested)
            except DiagnosticStopped:
                # Honour the Jobs page's Cancel: the explicit sentinel is what
                # makes JobManager mark this run 'cancelled' — a bare
                # ``{"ran": [...]}`` is truthy and would read as 'done'. What
                # did finish is kept (and listed); the rest stays pending and
                # is queued again at the next start.
                return {"ran": ran, "cancelled": True}
            ran.append({"name": d.name, "version": d.version, "status": out["status"]})
        return {"ran": ran}

    return jm.submit(JOB_KIND, body)


def all_results(settings: Settings) -> dict[str, Any]:
    """Every stored result (all versions, newest first per name) plus what is
    still pending. Read-only."""
    out: list[dict[str, Any]] = []
    d = results_dir(settings)
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(p.read_text()))
            except (OSError, ValueError):
                continue
    out.sort(key=lambda r: (r.get("name", ""), -int(r.get("version", 0))))
    return {
        "results": out,
        "pending": [{"name": x.name, "version": x.version, "question": x.question}
                    for x in pending(settings)],
    }
