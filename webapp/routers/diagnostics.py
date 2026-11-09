"""``GET /api/diagnostics`` — the answers the shipped library diagnostics gave.

Read-only. Lists every stored result of :mod:`seestack.diag` (numbers and
catalogue names only, by that package's contract) and which diagnostics are
still waiting to run. It is on the read-only token's allowlist so the observer
on the owner's NAS can collect new results and report them, which is the whole
point: a question about his real library is answered without anyone typing a
command (see :mod:`webapp.diagnostics`).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from webapp import deps
from webapp import diagnostics as diag

router = APIRouter(tags=["diagnostics"])


@router.get("/api/diagnostics")
def get_diagnostics(request: Request) -> dict[str, Any]:
    return diag.all_results(deps.get_settings(request))
