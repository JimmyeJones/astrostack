""""Try it with a sample image" — the empty-app onboarding demo.

Three tiny endpoints back a single Dashboard card: check whether the generated
demo target exists, create it on one tap, and remove it when the newcomer is
done. The heavy lifting (generate → ingest → QC → inject WCS) lives in
:mod:`webapp.sample_data`; this is just the HTTP surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps, sample_data

router = APIRouter(prefix="/api/sample", tags=["sample"])


class SampleStatusOut(BaseModel):
    loaded: bool
    safe: str | None = None
    n_frames: int = 0


def _to_out(status: sample_data.SampleStatus) -> SampleStatusOut:
    return SampleStatusOut(loaded=status.loaded, safe=status.safe, n_frames=status.n_frames)


@router.get("", response_model=SampleStatusOut)
def sample_status(request: Request) -> SampleStatusOut:
    lib = deps.open_library(request)
    try:
        return _to_out(sample_data.get_sample_status(lib))
    finally:
        lib.close()


@router.post("", response_model=SampleStatusOut, status_code=201)
def load_sample(request: Request) -> SampleStatusOut:
    lib = deps.open_library(request)
    try:
        return _to_out(sample_data.load_sample(lib))
    finally:
        lib.close()


@router.delete("", response_model=SampleStatusOut)
def remove_sample(request: Request) -> SampleStatusOut:
    lib = deps.open_library(request)
    try:
        sample_data.remove_sample(lib)
        return _to_out(sample_data.get_sample_status(lib))
    finally:
        lib.close()
