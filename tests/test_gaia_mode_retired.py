"""The Gaia colour-calibration mode is gone, and an old value that names it is safe.

Filed by the fourth external audit (2026-09-10) and confirmed in the running
image: ``color_calibration_mode="gaia"`` imported ``astroquery.gaia``, which is in
no dependency list and is absent from the shipped image, so the import raised
``ModuleNotFoundError``, the broad ``except`` in ``calibrate_color`` swallowed it,
and the solve silently became gray-star with only a log line. It was also a
SIMBAD/CDS **network** call, which AGENTS.md §1 declines as standing policy. So
the editor and the Stack form offered a mode that could not run, and picking it
did nothing and said nothing.

Retiring a choice is a tightening, so the other half of this file is AGENTS.md §9:
a value a previous version legitimately wrote must keep loading. Three surfaces
could have stored one — a saved editor recipe, the global
``default_stack_options`` in ``config.json``, and a per-target stack-defaults blob
— and removing the option from a descriptor's ``options`` would have made
``validate_stack_options`` **reject** it, 422-ing the Stack form on every submit.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.edit.recipe import recipe_from_dict  # noqa: E402
from seestack.edit.registry import EditContext, get_op  # noqa: E402
from seestack.post.color_cal import (  # noqa: E402
    GAIA_RETIRED_NOTE,
    MODE_GAIA,
    MODE_GRAY_STAR,
    ColorCalibrationOptions,
    calibrate_color,
)
from webapp.schemas import (  # noqa: E402
    coerce_stack_options,
    normalise_retired_option_values,
    stack_option_fields,
    validate_stack_options,
)


def _starfield(seed: int = 7) -> np.ndarray:
    """A small RGB frame with enough stars for a gray-star solve to run.

    The cast is deliberate and asymmetric (R high, B low) so a solve that really
    happened is visible in the output rather than inferred from a return code.
    """
    rng = np.random.default_rng(seed)
    h = w = 160
    rgb = rng.normal(0.02, 0.0015, size=(h, w, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(90):
        cy, cx = rng.uniform(6, h - 6), rng.uniform(6, w - 6)
        amp = rng.uniform(0.25, 0.8)
        star = amp * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * 1.4**2))
        rgb += star[..., None].astype(np.float32)
    rgb[..., 0] *= 1.35  # the OSC cast the calibration exists to remove
    rgb[..., 2] *= 0.70
    return rgb


# --------------------------------------------------------------------------
# Nothing offers it any more
# --------------------------------------------------------------------------


def test_the_editor_no_longer_offers_the_gaia_mode() -> None:
    spec = get_op("tone.color_calibrate")
    assert spec is not None
    mode = next(p for p in spec.params if p.key == "mode")
    assert mode.options == [MODE_GRAY_STAR], (
        "the editor is offering a colour-calibration mode the image cannot run"
    )
    assert MODE_GAIA not in (mode.option_labels or {})
    # The help text must not promise the catalogue either — the op's help is what
    # the editor shows beside the control.
    assert "gaia" not in (spec.help or "").lower()
    assert "gaia" not in (mode.help or "").lower()


def test_the_stack_form_no_longer_offers_the_gaia_mode() -> None:
    fld = next(f for f in stack_option_fields() if f.key == "color_calibration_mode")
    assert fld.options == [MODE_GRAY_STAR]
    assert "gaia" not in (fld.help or "").lower()


# --------------------------------------------------------------------------
# The engine answers a stored "gaia" honestly instead of failing quietly
# --------------------------------------------------------------------------


def test_a_stored_gaia_mode_solves_gray_star_and_says_so() -> None:
    """The behaviour is the same; what changes is that it is now *reported*.

    Before: ``ModuleNotFoundError`` → swallowed → ``mode_used`` was still stamped
    ``gray_star``, which happened to be true, but nothing recorded that the
    requested mode had not run. Now the result carries a plain-language note, and
    no import of ``astroquery`` is attempted at all.
    """
    rgb = _starfield()
    calibrated, result = calibrate_color(
        rgb, None, ColorCalibrationOptions(enabled=True, mode=MODE_GAIA)
    )
    assert result.mode_used == MODE_GRAY_STAR
    assert GAIA_RETIRED_NOTE in result.notes
    assert result.n_stars_used > 0
    # It really calibrated: the planted red cast is pulled back toward neutral.
    assert result.scale_rgb[0] < 1.0 < result.scale_rgb[2]
    assert np.isfinite(calibrated).all()


def test_asking_for_gaia_never_reaches_astroquery(monkeypatch: pytest.MonkeyPatch) -> None:
    """The inert branch must be inert by construction, not by exception handling.

    ``astroquery`` is absent from the image, so a swallowed import error looked
    exactly like a working fallback.

    This **records** attempted imports rather than raising on them, which matters:
    the pre-fix code wrapped the import in ``except Exception``, so an assertion
    raised from inside would have been swallowed and this test would have passed
    against the very code it is meant to catch. Verified by restoring the old
    dispatch in a scratch script — it logs
    ``Gaia calibration failed (No module named 'astroquery')`` and fails here.
    """
    import builtins

    real_import = builtins.__import__
    attempted: list[str] = []

    def _record(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("astroquery"):
            attempted.append(name)
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _record)
    _, result = calibrate_color(
        _starfield(), None, ColorCalibrationOptions(enabled=True, mode=MODE_GAIA)
    )
    assert attempted == [], f"the retired gaia path still imports {attempted}"
    assert result.mode_used == MODE_GRAY_STAR


def test_the_editor_op_degrades_a_gaia_param_for_a_direct_caller() -> None:
    """``validate_ops`` normally rewrites it first; the op guards its own door too.

    A direct engine caller (a script, a test, the historical GUI) can hand the op
    raw params that never went through the recipe validator.
    """
    spec = get_op("tone.color_calibrate")
    assert spec is not None
    out = spec.apply(_starfield(), {"mode": MODE_GAIA}, ctx := EditContext())
    notes = ctx.op_notes["tone.color_calibrate"]
    assert notes["mode_used"] == MODE_GRAY_STAR
    assert GAIA_RETIRED_NOTE in notes["notes"]
    assert np.isfinite(out).all()


# --------------------------------------------------------------------------
# Upgrade safety (§9): every stored shape still loads
# --------------------------------------------------------------------------


def test_a_saved_recipe_naming_gaia_still_loads_as_gray_star() -> None:
    """An editor recipe saved before v0.418.0 must not fail to deserialise."""
    recipe = recipe_from_dict(
        {
            "version": 1,
            "ops": [{"id": "tone.color_calibrate", "params": {"mode": "gaia"}}],
        }
    )
    assert [op.id for op in recipe.ops] == ["tone.color_calibrate"]
    assert recipe.ops[0].params["mode"] == MODE_GRAY_STAR


def test_a_stored_gaia_default_is_translated_not_rejected() -> None:
    """This is the §9 regression: the Stack form must not start 422-ing.

    ``validate_stack_options`` raises on a value outside a descriptor's
    ``options``, and an install whose ``default_stack_options`` (or per-target
    stack-defaults blob) holds ``"gaia"`` feeds exactly that value back into every
    submit — including the unattended auto-stack chain.
    """
    stored = {"color_calibration": True, "color_calibration_mode": "gaia"}
    validate_stack_options(stored)  # must not raise
    assert coerce_stack_options(stored).color_calibration_mode == MODE_GRAY_STAR
    # And a value that is simply wrong is still rejected — the translation must
    # not have become a blanket "accept any string".
    with pytest.raises(ValueError):
        validate_stack_options({"color_calibration_mode": "nonsense"})


def test_normalising_retired_values_is_the_identity_on_everything_else() -> None:
    """It runs on every stack submit, so it must be a no-op in the normal case."""
    ordinary = {
        "color_calibration": True,
        "color_calibration_mode": "gray_star",
        "sigma_kappa": 2.5,
        "mosaic_canvas": "auto",
        "max_workers": None,
    }
    out = normalise_retired_option_values(ordinary)
    assert out == ordinary
    assert out is not ordinary, "must not mutate the caller's dict"
    # A key that is absent, and a non-string value under a retired key, pass through.
    assert normalise_retired_option_values({}) == {}
    assert normalise_retired_option_values({"color_calibration_mode": 3}) == {
        "color_calibration_mode": 3
    }
