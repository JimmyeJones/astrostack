"""What a "mosaic" fixture can and cannot vouch for — and how to say so.

Three findings in a row came from the same mechanism, not from three different
bugs: the *code* was tested and the *fixture* was the wrong assumption.

* **A1** — Auto's contrast curve read the STF's zero-clip spike as the sky, pinned
  by fixtures that had no spike.
* **D1** — ``well_covered_mask`` measured "well covered" against the coverage
  map's *peak*, pinned by six tests whose "mosaic" was one plateau plus a fringe,
  so the peak and a panel were the same number and the bug was invisible.
* **The 2026-09-08 thin-note bug** — ``_COVERAGE_THIN_SHARE`` was calibrated on
  "an even three-panel mosaic": no four-way corner, no weight jitter, while the
  owner shoots 3x3 and 12x8 rasters with uneven panel depth.

Each survived every sweep of the code it lived in. So a fixture that calls itself
a mosaic now **states its claim and asserts it**, and the vocabulary below is
deliberately small — these are the distinctions that actually bit:

* **statistically alike** panels — each panel draws its own star field, so the
  panels resemble each other but the *same star* is not in both. Enough for
  anything measured inside one panel (levels, depth, NaN/coverage semantics,
  which method a rule dispatches); useless for anything measured *across* a join.
* **positionally alike** panels — the panels are windows onto one catalog
  (:func:`tests.synth.star_catalog` + :func:`tests.synth.make_shared_sky_field`),
  so an overlap really holds the same stars at the same sky position. Required by
  anything measuring a seam, a gain, or a level step *between* panels: an overlap
  of unrelated stars let a new pass invent a 2.6x gain and call it measured
  (v0.387.0).
* **even vs uneven panel depth** — the owner's panels are not equally deep. A
  rule taken from a whole-target or *peak* number instead of a per-panel one is
  correct on even depth and wrong on his.
* **two-way vs four-way overlap** — a 1xN strip or a 2x2 at low overlap never
  produces the 4x plateau a 3x3 raster's interior corners do, which is where the
  gap between "the peak" and "a panel" is widest.
* **integer vs weighted coverage** — with ``quality_weighted`` on (the walk-away
  default) a coverage value is a sum of per-frame *weights*, not a frame count,
  so plateaus are found by relative tolerance and an integer-depth fixture
  exercises none of that.
* **blocky vs dithered panels** — every mosaic fixture here puts its panels on a
  fixed grid with flat interiors, so some depth always holds a real share of the
  canvas and ``panel_coverage_level`` always finds a plateau. The owner's panels
  are dithered and re-framed night to night, so his depths are a **continuum**
  with no plateau anywhere, and that is the one shape where the function's
  fall-through decides the answer (see :func:`assert_depths_are_a_continuum`).
* **a continuum with no plateau vs one that presents a PHANTOM plateau** — and
  "dithered" is not one case but two, which is how D1 came back a fifth time. The
  plateau search's tolerance is *relative*, so the window it tests is ``tol`` ×
  the depth it tests at: a continuum of roughly even density satisfies it only
  high up, where the window is widest, i.e. at the band where two panels
  **overlap**. So one dithered canvas declines outright (the fourth instalment's
  case) and the next hands back a level at 2x a panel — the pre-D1 answer — from
  the *other* branch. Over 20 seeds of one dithered 2x2 shape, 13 declined and
  **7 presented a phantom plateau**. A fixture that says "dithered" must therefore
  say which of the two it is: :func:`assert_depths_are_a_continuum` or
  :func:`assert_the_plateau_search_finds_a_phantom`.

Nothing here changes a fixture that works for what it was built for. The
deliverable is the assertion that says what each one **is**.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.coverage_trim import (
    PANEL_LEVEL_MIN_FRAC,
    PANEL_LEVEL_MIN_PIXELS,
    PANEL_LEVEL_TOL,
    panel_coverage_level,
)


def covered_values(cov) -> np.ndarray:
    """The finite, strictly-positive values of a 2-D coverage map."""
    a = np.asarray(cov, dtype=np.float64)
    if a.ndim != 2:
        raise ValueError(f"coverage shape claims are about 2-D maps, got {a.shape}")
    return a[np.isfinite(a) & (a > 0)]


def panel_level(cov) -> float | None:
    """One panel's depth, **by the same definition the trim itself uses**.

    Deliberately :func:`seestack.edit.coverage_trim.panel_coverage_level` rather
    than a second opinion written for the tests: a fixture's claim is only worth
    anything if it is stated in the units the rule under test measures in.
    """
    v = covered_values(cov)
    return None if v.size == 0 else panel_coverage_level(v)


def peak_over_panel(cov) -> float:
    """Peak coverage in units of one panel — how many panels meet at the deepest
    point. ~1 = a single field (or panels that never overlap), ~2 = a strip or a
    grid's edge seams, ~4 = the interior corner of a raster, which is where the
    gap between "the peak" and "a panel" is widest and where D1 hurt most.

    Weight jitter lifts the peak (it is a maximum over many pixels) without moving
    the panel level (a median), so a jittered fixture reads a little above its
    integer geometry. Assert with a floor, not for equality.
    """
    v = covered_values(cov)
    level = panel_level(cov)
    if v.size == 0 or not level:
        return 0.0
    return float(v.max()) / float(level)


def level_share(cov, level: float, *, tol: float = 0.15) -> float:
    """Share of the covered pixels sitting within ``tol`` of ``level``."""
    v = covered_values(cov)
    if v.size == 0:
        return 0.0
    return float(np.mean(np.abs(v - level) <= tol * level))


def describe_coverage(cov) -> str:
    """A one-line shape summary, for an assertion message worth reading."""
    v = covered_values(cov)
    if v.size == 0:
        return "nothing covered"
    level = panel_level(cov)
    return (f"panel {level:.2f}, peak {float(v.max()):.2f} "
            f"({peak_over_panel(cov):.2f}x a panel), thinnest {float(v.min()):.2f}, "
            f"{100.0 * (1 - v.size / np.asarray(cov).size):.1f}% of the canvas "
            f"uncovered")


def assert_weighted(cov, *, what: str = "fixture") -> None:
    """Assert coverage really is a sum of *weights*, not a frame count.

    ``quality_weighted`` is on by default on the walk-away path, so a real panel
    reads as N +/- jitter; an integer-depth fixture exercises none of the relative
    -tolerance machinery that exists for exactly that and cannot vouch for it.
    """
    v = covered_values(cov)
    assert not np.allclose(v, np.round(v)), (
        f"{what}: coverage is integral ({describe_coverage(cov)}), so this "
        f"fixture cannot vouch for anything about weighted coverage")


def panels_below_reference_share(cov, *, min_frac: float = 0.5) -> float:
    """Share of the covered pixels the trim's depth threshold would discard.

    ``min_frac * panel_level`` is exactly the threshold
    :func:`seestack.edit.coverage_trim.well_covered_mask` applies, so this is
    "how much real, covered picture does the depth rule call fringe here?". On a
    single field and on an evenly-deep mosaic it is ~0; on a dense raster with
    uneven panel depth it is whole panels, which is the shape D1's fix still got
    wrong and no fixture in this suite held.
    """
    v = covered_values(cov)
    level = panel_level(cov)
    if v.size == 0 or not level:
        return 0.0
    return float(np.mean(v < min_frac * level))


def assert_panels_thinner_than_the_reference(cov, *, share: float = 0.02,
                                             what: str = "fixture") -> None:
    """Assert the fixture really holds panels the depth threshold would discard.

    Without this, a "12x8 with uneven depth" fixture can be built whose thinnest
    panel still clears the threshold — in which case the test passes for the wrong
    reason and vouches for nothing. Uneven depth alone is not enough: a 1x2 at
    400/150 subs is uneven, and there the reference correctly *is* the thin panel.
    """
    got = panels_below_reference_share(cov)
    assert got >= share, (
        f"{what}: {describe_coverage(cov)} -- only {100 * got:.2f}% of the covered "
        f"canvas sits below the depth threshold, so this fixture cannot catch a "
        f"rule that crops thin panels away")


def assert_depths_are_a_continuum(cov, *, what: str = "fixture") -> None:
    """Assert the fixture's depths hold **no plateau at all** — the shape on which
    :func:`seestack.edit.coverage_trim.panel_coverage_level` has no level to point
    at and falls through to :func:`~seestack.edit.coverage_trim._continuum_level`.

    The fifth entry in the list at the top of this module, and the same mechanism
    as the other four: every "mosaic" fixture here is **blocky** — panels on a
    fixed grid, each interior flat, so one depth holds a real share of the canvas
    and the plateau search always finds one. The owner's mosaics are the same few
    pointings revisited across many nights, each sub dithered and each night
    re-framed, so every panel edge lands somewhere new on every visit and the
    depth climbs in hundreds of small steps. Measured on his own library (observer
    report #1109): 13 of 88 current pictures hold their largest level in under 8 %
    of the sample, every one of them a mosaic.

    Stated in the units the rule measures in, like :func:`panel_level`: the claim
    is that the *search* declines, not that some hand-rolled histogram is flat.

    **And it asserts the search, not its answer** (tightened with D1's fifth
    instalment). ``panel_coverage_level`` now *clamps* a plateau to the median, so
    "the reference is the median" is true both when the search declines and when
    it found a phantom plateau and was overruled — i.e. the old form of this
    assertion would pass on either, and a fixture claiming the fall-through could
    in fact be exercising the clamp. :func:`plateau_search_level` is what
    distinguishes them.
    """
    v = covered_values(cov)
    assert v.size >= 256, (
        f"{what}: {describe_coverage(cov)} -- only {v.size} covered pixels, so "
        f"`panel_coverage_level` declines on sample size (PANEL_LEVEL_MIN_PIXELS) "
        f"rather than on the shape, and this fixture is not the case it claims")
    found = plateau_search_level(cov)
    assert found is None, (
        f"{what}: {describe_coverage(cov)} -- the plateau search found a level at "
        f"{found:.2f}, so this fixture exercises the clamp rather than the "
        f"fall-through and cannot vouch for the no-plateau path")
    level = panel_level(cov)
    median = float(np.median(v))
    assert level == pytest_approx(median), (
        f"{what}: {describe_coverage(cov)} -- the reference is {level}, not the "
        f"median {median:.2f}, so a plateau *was* found and this fixture cannot "
        f"vouch for the no-plateau path")


def plateau_search_level(cov) -> float | None:
    """The level ``panel_coverage_level``'s plateau *search* lands on, **before**
    the median ceiling is applied — or ``None`` when no window anywhere is tight
    and the search declines.

    The one thing in this module that mirrors production arithmetic rather than
    calling it, and deliberately: the whole point is to see which **branch** a
    fixture takes, which the clamped answer no longer reveals (a phantom plateau
    and an honest decline both come back as the median). It reads the module's own
    constants, so a fixture's claim still moves with the rule it is about; only the
    four lines of the window test are restated. If those four lines ever change,
    this is the place that has to follow — which is cheaper than a fixture that
    silently stops exercising the case its name claims.
    """
    vals = np.sort(covered_values(cov))
    n = vals.size
    if n == 0:
        return None
    need = max(PANEL_LEVEL_MIN_PIXELS, int(np.ceil(PANEL_LEVEL_MIN_FRAC * n)))
    if need > n:
        return None
    lo = vals[: n - need + 1]
    hi = vals[need - 1:]
    tight = np.flatnonzero(hi - lo <= PANEL_LEVEL_TOL * np.maximum(hi, 1e-12))
    if tight.size == 0:
        return None
    start = int(tight[0])
    stop = int(np.searchsorted(vals, vals[start] * (1.0 + PANEL_LEVEL_TOL),
                               side="right"))
    return float(np.median(vals[start:max(stop, start + 1)]))


def assert_the_plateau_search_finds_a_phantom(cov, *, ratio: float = 1.5,
                                              what: str = "fixture") -> None:
    """The *other* dithered claim: this canvas's depths are a continuum, and the
    plateau search nevertheless finds a window — above one panel, at the band
    where panels overlap, because its tolerance is relative to the depth it tests.

    This is the shape D1's fifth instalment is about, and the one no fixture in the
    suite had: the fourth instalment's fall-through is never reached here, so a map
    like this took the pre-D1 answer under a stamp certifying it was gone.
    ``ratio`` is how far above the median the phantom must sit for the fixture to
    be worth anything — at 1.0 the bug would have no room to be wrong.
    """
    v = covered_values(cov)
    median = float(np.median(v))
    found = plateau_search_level(cov)
    assert found is not None, (
        f"{what}: {describe_coverage(cov)} -- the plateau search declines here, so "
        f"this is the fall-through case (assert_depths_are_a_continuum), not the "
        f"phantom-plateau one")
    assert found >= ratio * median, (
        f"{what}: {describe_coverage(cov)} -- the search lands at {found:.2f}, only "
        f"{found / max(median, 1e-12):.2f}x the median {median:.2f}, so the clamp "
        f"has too little to do for this fixture to pin it")


def uncovered_share(cov) -> float:
    """Share of the canvas no frame reached (NaN or zero coverage)."""
    a = np.asarray(cov)
    if a.ndim != 2 or a.size == 0:
        return 0.0
    return float(1.0 - covered_values(a).size / a.size)


def assert_fully_tiled(cov, *, what: str = "fixture") -> None:
    """Assert the canvas has **no uncovered pixel at all**.

    The distinction the fourth D1 instalment turned on. A border trim exists to
    remove the ragged edge where the data runs out — so on a canvas where it never
    runs out, the honest answer is *no crop*, and every pixel a trim removes is
    real picture. A fixture that merely has uneven panel depth cannot say that: it
    may also have a ragged outline, in which case a crop is expected and the test
    cannot tell an honest trim from a panel being eaten.
    """
    got = uncovered_share(cov)
    assert got == 0.0, (
        f"{what}: {describe_coverage(cov)} -- {100 * got:.2f}% of the canvas is "
        f"uncovered, so this fixture cannot vouch for 'there is no border here'")


def assert_has_a_ragged_outline(cov, *, share: float = 0.005,
                                what: str = "fixture") -> None:
    """The opposite claim: the canvas really does run out of data somewhere, so a
    border trim has something honest to remove."""
    got = uncovered_share(cov)
    assert got >= share, (
        f"{what}: {describe_coverage(cov)} -- only {100 * got:.2f}% of the canvas "
        f"is uncovered, so this fixture has no ragged border to trim")


def assert_reference_is_the_thinnest_panel(cov, *, what: str = "fixture") -> None:
    """The opposite claim, for a fixture whose panels *are* individually
    substantial: the reference depth lands on the thinnest panel, so nothing real
    is below the threshold at all."""
    v = covered_values(cov)
    level = panel_level(cov)
    assert level == pytest_approx(float(v.min())), (
        f"{what}: {describe_coverage(cov)} -- the reference is not the thinnest "
        f"panel, so this fixture is not the case it says it is")
    assert panels_below_reference_share(cov) == 0.0, describe_coverage(cov)


def pytest_approx(value, rel: float = 1e-3):
    """A tiny local approx so this module stays importable without pytest."""
    class _Approx:
        def __eq__(self, other) -> bool:
            return abs(float(other) - float(value)) <= rel * max(abs(float(value)), 1e-12)

        def __repr__(self) -> str:
            return f"~{value}"
    return _Approx()
