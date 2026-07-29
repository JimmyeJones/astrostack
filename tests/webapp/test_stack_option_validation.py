"""The stack-trigger endpoint validates option values up front (400), rather
than accepting a bad enum/range and failing the job cryptically in the engine."""

from __future__ import annotations

import pytest

from webapp.schemas import coerce_stack_options, validate_stack_options


# --- unit: the validator itself -------------------------------------------


def test_validate_accepts_good_values_and_ignores_unknowns():
    # Valid enum + in-range number + an unknown key (coerce drops it) + None.
    validate_stack_options({
        "tiff_mode": "linear",
        "sigma_kappa": 3.0,
        "drizzle_scale": 2.0,
        "output_name": "m42",
        "not_a_real_option": "whatever",
        "background_mode": None,
    })


def test_validate_rejects_bad_enum():
    with pytest.raises(ValueError, match="TIFF mode"):
        validate_stack_options({"tiff_mode": "garbage"})


def test_validate_rejects_out_of_range_number():
    with pytest.raises(ValueError, match="below the minimum"):
        validate_stack_options({"sigma_kappa": 0.1})   # min is 1.0
    with pytest.raises(ValueError, match="above the maximum"):
        validate_stack_options({"drizzle_scale": 99.0})  # max is 4.0


def test_validate_rejects_non_numeric_for_numeric_field():
    with pytest.raises(ValueError, match="expected a number"):
        validate_stack_options({"sigma_kappa": "lots"})


def test_validate_rejects_fractional_float_for_int_field():
    # An int-typed option (e.g. max_workers) must be a whole number. A fractional
    # float would otherwise slip past coerce_stack_options (no coercion) into the
    # engine as a float.
    with pytest.raises(ValueError, match="whole number"):
        validate_stack_options({"max_workers": 3.5})
    with pytest.raises(ValueError, match="whole number"):
        validate_stack_options({"min_max_reject_count": 2.7})


def test_validate_accepts_integral_float_for_int_field():
    # A float that happens to be integral (3.0 — how JSON often carries an int)
    # is a valid whole number and must still be accepted.
    validate_stack_options({"max_workers": 3.0, "background_box_size": 128.0})


# --- coerce: a cleared numeric field posts null; must fall back to default -


def test_coerce_drops_null_numeric_falls_back_to_default():
    # Backspacing over "Sigma κ" in the React form posts sigma_kappa=null. Coerce
    # must NOT write None into the (non-optional) dataclass field — that reaches
    # the engine as `NoneType * float` and dies with a raw TypeError.
    opts = coerce_stack_options({"sigma_clip": True, "sigma_kappa": None})
    assert opts.sigma_kappa == 3.0  # the dataclass default, not None
    assert opts.sigma_clip is True


def test_coerce_preserves_optional_none_fields():
    # For a genuinely-optional field the default is itself None, so dropping a
    # null key yields the identical value (max_workers stays None = auto).
    opts = coerce_stack_options({"max_workers": None, "output_name": "m42"})
    assert opts.max_workers is None
    assert opts.output_name == "m42"


# --- endpoint: bad options -> 400, not a submitted-then-errored job --------


def test_trigger_stack_rejects_bad_enum_with_400(client, solved_library):
    r = client.post("/api/targets/M_42/stack", json={"tiff_mode": "garbage"})
    assert r.status_code == 400
    assert "tiff" in r.json()["detail"].lower()


def test_trigger_stack_rejects_out_of_range_with_400(client, solved_library):
    r = client.post("/api/targets/M_42/stack", json={"drizzle_scale": 99.0})
    assert r.status_code == 400
    assert "maximum" in r.json()["detail"].lower()


def test_trigger_stack_still_accepts_valid_options(client, solved_library):
    # A well-formed request is unaffected by the new guard.
    r = client.post(
        "/api/targets/M_42/stack",
        json={"output_name": "valid_master", "sigma_clip": False,
              "background_flatten": False, "suppress_hot_pixels": False,
              "tiff_mode": "linear", "max_workers": 2},
    )
    assert r.status_code == 200
    assert "job_id" in r.json()


def test_stack_defaults_does_not_persist_a_cleared_numeric_null(client, solved_library):
    # Backspacing over "Sigma κ" then "Save as defaults" posts sigma_kappa=null.
    # It must NOT be stored — a persisted null would poison every future stack
    # for this target (including the walk-away auto-stack) with an engine TypeError.
    r = client.put(
        "/api/targets/M_42/stack-defaults",
        json={"sigma_clip": True, "sigma_kappa": None},
    )
    assert r.status_code == 200
    assert "sigma_kappa" not in r.json()
    # And it round-trips clean from the GET (no null lurking in the saved defaults).
    got = client.get("/api/targets/M_42/stack-defaults").json()
    assert got.get("sigma_kappa") != None  # noqa: E711 — explicitly assert not None
