"""System info + health check."""

from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Request

from webapp import deps

router = APIRouter(tags=["system"])


def _astap_info(settings) -> dict:  # noqa: ANN001
    try:
        from seestack.solve.astap import find_astap

        path = find_astap(settings.astap_path)
        return {"found": path is not None, "path": str(path) if path else None}
    except Exception as exc:  # noqa: BLE001
        return {"found": False, "path": None, "error": str(exc)}


def _gpu_available() -> bool:
    try:
        from seestack.core.xp import GPU_AVAILABLE

        return bool(GPU_AVAILABLE)
    except Exception:  # noqa: BLE001
        return False


@router.get("/api/health")
def health(request: Request) -> dict:
    settings = deps.get_settings(request)
    return {
        "ok": True,
        "astap_found": _astap_info(settings)["found"],
        "library_ok": settings.resolved_library_root.exists(),
    }


@router.get("/api/system")
def system(request: Request) -> dict:
    settings = deps.get_settings(request)
    astap = _astap_info(settings)
    disk = {}
    try:
        usage = shutil.disk_usage(settings.data_root)
        disk = {
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb": round(usage.used / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
        }
    except OSError:
        pass
    return {
        "version": __import__("webapp").__version__,
        "data_root": settings.data_root,
        "cpu_count": os.cpu_count(),
        "cpu_workers": settings.cpu_workers,
        "gpu_available": _gpu_available(),
        "astap": astap,
        "disk": disk,
        "watcher_enabled": settings.watcher_enabled,
    }
