"""How fast is the owner's NAS at the work a stack does, per sub?

Roadmap 1.0, test R2. The audit's stack-time estimates (his biggest target:
~8 h plain on a fast box, ~22 h on a slow one) hinge on a CPU nobody has
measured. This reports what the container sees (cores, memory and its limit,
free disk) and times the per-sub steps every stack repeats on a sample of his
own subs: reading the file, debayering, the per-frame sky flatten, and QC.

Read-only: files are opened to read; nothing is written.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import statistics
import time
from pathlib import Path
from typing import Any

from seestack.diag import Diagnostic, DiagnosticStopped, iter_sub_refs, sub_path

SAMPLE = 16


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def _machine(library) -> dict[str, Any]:  # noqa: ANN001
    cpu_model = None
    for line in _read_text("/proc/cpuinfo").splitlines():
        if line.lower().startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()[:80]
            break
    mem_gb = None
    for line in _read_text("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            mem_gb = round(int(line.split()[1]) / 1024 / 1024, 1)
    limit = _read_text("/sys/fs/cgroup/memory.max").strip()
    limit_gb = (round(int(limit) / 1024 ** 3, 1) if limit.isdigit() else
                ("none" if limit == "max" else None))
    try:
        usage = shutil.disk_usage(str(library.root))
        disk = {"free_gb": round(usage.free / 1024 ** 3, 1),
                "total_gb": round(usage.total / 1024 ** 3, 1)}
    except (OSError, AttributeError):
        disk = None
    try:
        affinity = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = None
    return {"cpu_model": cpu_model, "cpu_count": os.cpu_count(), "cpus_usable": affinity,
            "memory_gb": mem_gb, "container_memory_limit_gb": limit_gb,
            "library_disk": disk}


def _sample_paths(library, n: int) -> list[str]:  # noqa: ANN001
    entries = sorted(library.list_targets(), key=lambda e: -(e.n_frames_accepted or 0))
    for e in entries[:5]:
        try:
            proj = library.open_target(e.safe_name)
        except Exception:  # noqa: BLE001
            continue
        try:
            refs = list(iter_sub_refs(proj, accepted_only=True))
        finally:
            proj.close()
        if len(refs) < 4:
            continue
        step = max(1, len(refs) // n)
        paths = [p for p in (sub_path(r) for r in refs[::step][:n]) if p]
        if len(paths) >= 4:
            return paths
    return []


def run(library, *, progress=None, should_stop=None) -> dict[str, Any]:  # noqa: ANN001
    import numpy as np

    from seestack.bg.per_frame import BackgroundOptions, subtract_background
    from seestack.io.fits_loader import bilinear_debayer, load_seestar_raw
    from seestack.qc.metrics import compute_frame_metrics

    out: dict[str, Any] = {"machine": _machine(library)}
    paths = _sample_paths(library, SAMPLE)
    times: dict[str, list[float]] = {"read": [], "debayer": [], "sky_flatten": [], "qc": []}
    mb: list[float] = []
    for i, p in enumerate(paths):
        if should_stop is not None and should_stop():
            raise DiagnosticStopped("stopped")
        if progress is not None:
            progress("timing subs", i, len(paths))
        try:
            t0 = time.perf_counter()
            raw, info = load_seestar_raw(p, debayer=False)
            t1 = time.perf_counter()
            rgb = bilinear_debayer(raw, pattern=info.bayer_pattern or "RGGB")
            t2 = time.perf_counter()
            subtract_background(rgb.astype(np.float32), BackgroundOptions(), use_gpu=False)
            t3 = time.perf_counter()
            compute_frame_metrics(p)
            t4 = time.perf_counter()
        except Exception:  # noqa: BLE001 — an unreadable sub is skipped
            continue
        times["read"].append(t1 - t0)
        times["debayer"].append(t2 - t1)
        times["sky_flatten"].append(t3 - t2)
        times["qc"].append(t4 - t3)
        with contextlib.suppress(OSError):
            mb.append(os.path.getsize(p) / 1e6)
    out["subs_timed"] = len(times["read"])
    out["seconds_per_sub_median"] = {k: round(statistics.median(v), 3)
                                     for k, v in times.items() if v}
    if times["read"] and mb:
        out["read_mb_per_s"] = round(sum(mb) / max(sum(times["read"]), 1e-6), 1)
    out["note"] = "single-threaded timings, one sub at a time, while the app may be busy"
    return out


DIAGNOSTIC = Diagnostic(
    name="machine_speed",
    version=1,
    question=("What CPU, memory and disk does the app have, and how long does each per-sub "
              "stacking step take on the owner's own subs? (1.0 roadmap R2)"),
    run=run,
    on_demand=True,
    ready=lambda library: any((e.n_frames_accepted or 0) >= 8 for e in library.list_targets()),
)
