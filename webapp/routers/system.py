"""System info + health check."""

from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Request

from webapp import deps

router = APIRouter(tags=["system"])


def _astap_info(settings) -> dict:  # noqa: ANN001
    """Report ASTAP availability *and* whether it can actually solve.

    A common failure mode is "binary found but no star database" — every solve
    then fails. We surface the database directory + ``.290`` count and a short
    self-test so the cause is obvious from the Settings page.
    """
    try:
        import subprocess

        from seestack.solve.astap import find_astap, find_star_db_dir

        path = find_astap(settings.astap_path)
        if path is None:
            return {
                "found": False, "path": None, "star_db_found": False,
                "star_db_dir": None, "star_db_count": 0,
                "hint": "ASTAP binary not found. Set astap_path or SEESTACK_ASTAP_PATH.",
            }

        db_dir = find_star_db_dir(path)
        db_count = (
            len(list(db_dir.glob("*.290"))) + len(list(db_dir.glob("*.1476")))
            if db_dir else 0
        )
        info = {
            "found": True,
            "path": str(path),
            "star_db_found": db_count > 0,
            "star_db_dir": str(db_dir) if db_dir else None,
            "star_db_count": db_count,
        }
        # Quick "does it even run" probe (does not solve a frame).
        try:
            proc = subprocess.run(  # noqa: S603
                [str(path), "-h"], capture_output=True, text=True, timeout=15, check=False,
            )
            out = (proc.stdout + proc.stderr)
            ver = next((ln for ln in out.splitlines() if "version" in ln.lower()), "")
            info["runs"] = True
            info["version"] = ver.strip()[:120] or None
        except Exception as exc:  # noqa: BLE001
            info["runs"] = False
            info["error"] = f"ASTAP failed to run: {exc}"
        if db_count == 0:
            info["hint"] = (
                "ASTAP is installed but no star database (*.290) was found next "
                "to it — every solve will fail. Add one (e.g. d05) to "
                f"{path.parent} or set SEESTACK_ASTAP_DATA."
            )
        return info
    except Exception as exc:  # noqa: BLE001
        return {"found": False, "path": None, "error": str(exc)}


def _gpu_available() -> bool:
    try:
        from seestack.core.xp import GPU_AVAILABLE

        return bool(GPU_AVAILABLE)
    except Exception:  # noqa: BLE001
        return False


@router.get("/api/health")
async def health() -> dict:
    """Liveness probe. Deliberately trivial — no subprocess, no disk, no locks.

    This is what Docker's HEALTHCHECK hits. It must answer *instantly* even when
    the job worker is pinning every core on a long stack; anything heavier here
    (e.g. shelling out to ASTAP, which is slow under load) can blow the probe's
    timeout, get the container restarted mid-stack, and leave jobs "interrupted".
    Rich status (ASTAP, disk, GPU) lives on ``/api/system`` instead.
    """
    return {"ok": True}


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
