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

Nothing here changes a fixture that works for what it was built for. The
deliverable is the assertion that says what each one **is**.
"""

from __future__ import annotations

import numpy as np

from seestack.edit.coverage_trim import panel_coverage_level


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
