""""Try it with a sample image" — the empty-app onboarding demo.

Three tiny endpoints back a single Dashboard card: check whether the generated
demo target exists, create it on one tap, and remove it when the newcomer is
done. The heavy lifting (generate → ingest → QC → inject WCS) lives in
:mod:`webapp.sample_data`; this is just the HTTP surface.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from webapp import deps, sample_data

router = APIRouter(prefix="/api/sample", tags=["sample"])


class SampleStatusOut(BaseModel):
    loaded: bool
    safe: str | None = None
    n_frames: int = 0
    # The second, opt-in demo (a 2×2 mosaic, its own target). Additive fields
    # with defaults, so every existing caller and bookmark reads exactly what it
    # read before: `loaded` still means "the single-field sample is loaded".
    mosaic_loaded: bool = False
    mosaic_safe: str | None = None
    mosaic_n_frames: int = 0


class SampleLoadIn(BaseModel):
    """Which demo to build. Absent body → the single field, as before."""

    shape: Literal["field", "mosaic"] = "field"


def _to_out(
    status: sample_data.SampleStatus,
    mosaic: sample_data.SampleStatus | None = None,
) -> SampleStatusOut:
    return SampleStatusOut(
        loaded=status.loaded, safe=status.safe, n_frames=status.n_frames,
        mosaic_loaded=bool(mosaic and mosaic.loaded),
        mosaic_safe=mosaic.safe if mosaic else None,
        mosaic_n_frames=mosaic.n_frames if mosaic else 0,
    )


@router.get("", response_model=SampleStatusOut)
def sample_status(request: Request) -> SampleStatusOut:
    lib = deps.open_library(request)
    try:
        return _to_out(
            sample_data.get_sample_status(lib),
            sample_data.get_sample_status(lib, shape="mosaic"),
        )
    finally:
        lib.close()


@router.post("", response_model=SampleStatusOut, status_code=201)
def load_sample(request: Request, body: SampleLoadIn | None = None) -> SampleStatusOut:
    lib = deps.open_library(request)
    try:
        shape = (body or SampleLoadIn()).shape
        sample_data.load_sample(lib, shape=shape)
        return _to_out(
            sample_data.get_sample_status(lib),
            sample_data.get_sample_status(lib, shape="mosaic"),
        )
    finally:
        lib.close()


@router.delete("", response_model=SampleStatusOut)
def remove_sample(request: Request) -> SampleStatusOut:
    lib = deps.open_library(request)
    try:
        sample_data.remove_sample(lib)
        return _to_out(
            sample_data.get_sample_status(lib),
            sample_data.get_sample_status(lib, shape="mosaic"),
        )
    finally:
        lib.close()
