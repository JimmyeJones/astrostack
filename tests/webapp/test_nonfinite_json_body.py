"""A request body carrying a ``NaN``/``Infinity`` literal is rejected with a 422,
not a 500.

The server's JSON parser accepts those literals, and FastAPI's default 422 echoes
the offending ``input`` back — which the response encoder (``allow_nan=False``)
could not write, so the rejection itself crashed with a traceback in the log.
"""

from __future__ import annotations

import pytest

_H = {"content-type": "application/json"}


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_literal_in_a_typed_body_is_a_422(client, built_library, literal):
    r = client.put("/api/targets/M_42/cover", content=f'{{"run_id": {literal}}}', headers=_H)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail
    assert detail[0]["loc"] == ["body", "run_id"]
    assert detail[0]["input"] == literal


def test_a_non_finite_literal_nested_in_a_rejected_body_is_a_422(client, built_library):
    # A preset missing its required ``label``: the error's ``input`` is the whole
    # body, with the NaN buried inside it.
    body = '{"name": "a", "ops": [{"id": "tone.stretch", "params": {"stretch": NaN}}]}'
    r = client.post("/api/editor/presets", content=body, headers=_H)
    assert r.status_code == 422, r.text
    err = r.json()["detail"][0]
    assert err["loc"] == ["body", "label"]
    assert err["input"]["ops"][0]["params"]["stretch"] == "NaN"


def test_an_ordinary_422_keeps_fastapis_shape(client, built_library):
    r = client.put("/api/targets/M_42/cover", json={"run_id": "abc"})
    assert r.status_code == 422
    err = r.json()["detail"][0]
    assert err["loc"] == ["body", "run_id"]
    assert err["input"] == "abc"
    assert err["type"] == "int_parsing"
