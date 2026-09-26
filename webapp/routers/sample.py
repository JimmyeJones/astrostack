""""Try it with a sample image" — the empty-app onboarding demo.

Three tiny endpoints back a single Dashboard card: check whether the generated
demo target exists, create it on one tap, and remove it when the newcomer is
done. The heavy lifting (generate → ingest → QC → inject WCS) lives in
:mod:`webapp.sample_data`; this is just the HTTP surface.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
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
    # The third, opt-in demo: the same 2×2 mosaic at full-size panels, whose
    # union canvas is past the editor's proxy cap. Additive and defaulted for
    # exactly the same reason the mosaic fields above are.
    big_loaded: bool = False
    big_safe: str | None = None
    big_n_frames: int = 0
    # The fourth, opt-in demo: one field shot many hundreds of times, so a
    # surface whose cost scales with the *number of subs* is finally exercised
    # at the owner's magnitude. Additive and defaulted, same as the two above.
    deep_loaded: bool = False
    deep_safe: str | None = None
    deep_n_frames: int = 0
    # The fifth, opt-in demo: a *pair* of targets on a patch of sky whose observing
    # season is ending, so ``/tonight``'s "Shoot these before they're gone" card
    # has something to say. ``closing_safe`` is the shallower of the two (the row
    # that card names first) and ``closing_n_frames`` the pair's total. Additive
    # and defaulted, like the three blocks above.
    closing_loaded: bool = False
    closing_safe: str | None = None
    closing_n_frames: int = 0


class SampleLoadIn(BaseModel):
    """Which demo to build. Absent body → the single field, as before."""

    shape: Literal["field", "mosaic", "big", "deep", "closing"] = "field"
    # Where to put it, for the one shape that has no fixed answer. A season closes
    # as a function of the target's right ascension against the *date*, so the
    # caller supplies the position (``seestack.nightplan.closing_sky_position``
    # asks the planner itself where such a target would sit). Every other shape is
    # fixed sky on purpose — its generated pixels are pinned bit-identical — so
    # passing coordinates with one is refused rather than ignored.
    ra_deg: float | None = None
    dec_deg: float | None = None


def _to_out(
    status: sample_data.SampleStatus,
    mosaic: sample_data.SampleStatus | None = None,
    big: sample_data.SampleStatus | None = None,
    deep: sample_data.SampleStatus | None = None,
    closing: sample_data.SampleStatus | None = None,
) -> SampleStatusOut:
    return SampleStatusOut(
        loaded=status.loaded, safe=status.safe, n_frames=status.n_frames,
        mosaic_loaded=bool(mosaic and mosaic.loaded),
        mosaic_safe=mosaic.safe if mosaic else None,
        mosaic_n_frames=mosaic.n_frames if mosaic else 0,
        big_loaded=bool(big and big.loaded),
        big_safe=big.safe if big else None,
        big_n_frames=big.n_frames if big else 0,
        deep_loaded=bool(deep and deep.loaded),
        deep_safe=deep.safe if deep else None,
        deep_n_frames=deep.n_frames if deep else 0,
        closing_loaded=bool(closing and closing.loaded),
        closing_safe=closing.safe if closing else None,
        closing_n_frames=closing.n_frames if closing else 0,
    )


def _all_shapes(lib) -> SampleStatusOut:  # noqa: ANN001 — Library, kept local
    """Every shape's status in one payload, the answer all three endpoints give."""
    return _to_out(
        sample_data.get_sample_status(lib),
        sample_data.get_sample_status(lib, shape="mosaic"),
        sample_data.get_sample_status(lib, shape="big"),
        sample_data.get_sample_status(lib, shape="deep"),
        sample_data.get_sample_status(lib, shape="closing"),
    )


@router.get("", response_model=SampleStatusOut)
def sample_status(request: Request) -> SampleStatusOut:
    lib = deps.open_library(request)
    try:
        return _all_shapes(lib)
    finally:
        lib.close()


@router.post("", response_model=SampleStatusOut, status_code=201)
def load_sample(request: Request, body: SampleLoadIn | None = None) -> SampleStatusOut:
    want = body or SampleLoadIn()
    center = _resolve_center(want)
    lib = deps.open_library(request)
    try:
        sample_data.load_sample(lib, shape=want.shape, center=center)
        return _all_shapes(lib)
    finally:
        lib.close()


def _resolve_center(want: SampleLoadIn) -> tuple[float, float] | None:
    """The requested sky centre, refusing the two ways it can be wrong.

    Checked before the library is opened so a bad request costs nothing, and
    answered with a sentence rather than a field name — the dogfood script is the
    caller, and a script's error message is read by whoever is debugging it.
    """
    has = want.ra_deg is not None and want.dec_deg is not None
    partial = (want.ra_deg is None) != (want.dec_deg is None)
    if partial:
        raise HTTPException(
            status_code=422,
            detail="Give both ra_deg and dec_deg, or neither.")
    if want.shape == "closing" and not has:
        raise HTTPException(
            status_code=422,
            detail="shape='closing' needs ra_deg and dec_deg: which patch of sky "
                   "is leaving depends on today's date, so the caller chooses it "
                   "(seestack.nightplan.closing_sky_position answers it).")
    if has and want.shape != "closing":
        raise HTTPException(
            status_code=422,
            detail=f"shape='{want.shape}' points at a fixed patch of sky; "
                   "ra_deg/dec_deg are only for shape='closing'.")
    return (float(want.ra_deg), float(want.dec_deg)) if has else None  # type: ignore[arg-type]


@router.delete("", response_model=SampleStatusOut)
def remove_sample(request: Request) -> SampleStatusOut:
    lib = deps.open_library(request)
    try:
        sample_data.remove_sample(lib)
        return _all_shapes(lib)
    finally:
        lib.close()
