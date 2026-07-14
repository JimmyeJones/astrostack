"""The stack-trigger endpoint validates option values up front (400), rather
than accepting a bad enum/range and failing the job cryptically in the engine."""

from __future__ import annotations

import pytest

from webapp.schemas import validate_stack_options


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
