"""seestack.diag.filter_card — tallies the subs' FILTER card per value, target,
night and catalogue family, reading headers only, and never lets a value that
is not a short plain word into the published result.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from seestack.diag import DiagnosticStopped, check_result_is_safe, registry
from seestack.diag import filter_card as fc
from tests.synth import write_seestar_fits


def _write(path, night: str, i: int, **cards):
    from astropy.io import fits

    write_seestar_fits(path, width=64, height=48, n_stars=5, noise_seed=i,
                       date_obs=f"2026-01-{night}T03:{i:02d}:00")
    with fits.open(path, mode="update") as hdul:
        for k, v in cards.items():
            hdul[0].header[k] = v


@pytest.fixture
def lib_and_incoming(tmp_path):
    from seestack.io.library import Library
    from seestack.io.scanner import scan_and_organize

    inc = tmp_path / "incoming"
    # M 42: filter in on both nights.
    d = inc / "M 42_sub"
    d.mkdir(parents=True)
    for i in range(4):
        _write(d / f"a{i}.fit", ("10", "11")[i % 2], i, FILTER="LP")
    # M 31: out on night 12, in on 13; night 14 is mixed; also a private card.
    d = inc / "M 31_sub"
    d.mkdir(parents=True)
    _write(d / "b0.fit", "12", 0, FILTER="IRCUT", FILTPOS=1)
    _write(d / "b1.fit", "13", 1, FILTER="LP", FILTPOS=2)
    _write(d / "b2.fit", "14", 2, FILTER="IRCUT", FILTPOS=1)
    _write(d / "b3.fit", "14", 3, FILTER="LP", FILTPOS=2)
    # M 13: no card at all; one sub carries a value that must not be published.
    d = inc / "M 13_sub"
    d.mkdir(parents=True)
    _write(d / "c0.fit", "15", 0)
    _write(d / "c1.fit", "15", 1, FILTER="/data/incoming/x")
    _write(d / "c2.fit", "16", 2, FILTER="SN 20261234")
    lib = Library.open_or_create(tmp_path / "library")
    scan_and_organize(lib, inc, copy_to_cache=False)
    yield lib, inc
    lib.close()


def _digest(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
            h.update(str(p.stat().st_mtime_ns).encode())
    return h.hexdigest()


def test_tallies_the_filter_card(lib_and_incoming):
    lib, _ = lib_and_incoming
    r = fc.run(lib)
    assert r["subs_sampled"] == 11 and r["subs_read"] == 11 and r["subs_unreadable"] == 0
    assert r["targets"] == 3 and r["nights"] == 7
    lp, ircut, absent = (r["filter_card"][k] for k in ("LP", "IRCUT", "(absent)"))
    assert (lp["subs"], lp["targets"], lp["nights"]) == (6, 2, 4)
    assert (ircut["subs"], ircut["targets"], ircut["nights"]) == (2, 1, 2)
    assert (absent["subs"], absent["targets"]) == (1, 1)
    assert sum(lp["by_family"].values()) == 6
    # A value that is not a plain word is counted, never shown.
    assert r["filter_card_other_values"] == {"subs": 2, "distinct": 2}
    assert set(r["filter_card"]) == {"LP", "IRCUT", "(absent)"}
    # The Seestar's own keyword, if it has one, is found by name.
    assert r["other_filter_keywords"]["FILTPOS"]["subs"] == 4
    # M 31's night 14 mixes LP and IRCUT; M 13's night 15 mixes a missing card
    # with a withheld value. Every other target-night has one value.
    assert r["target_nights_with_more_than_one_value"] == 2
    assert r["target_nights_read"] == 7


def test_result_is_safe_to_publish(lib_and_incoming):
    lib, _ = lib_and_incoming
    r = fc.run(lib)
    check_result_is_safe(r)
    text = json.dumps(r)
    assert "/data" not in text and "20261234" not in text and "incoming" not in text


def test_reads_incoming_without_touching_it(lib_and_incoming):
    lib, inc = lib_and_incoming
    before = _digest(inc)
    fc.run(lib)
    assert _digest(inc) == before


def test_it_stops_when_asked(lib_and_incoming):
    lib, _ = lib_and_incoming
    with pytest.raises(DiagnosticStopped):
        fc.run(lib, should_stop=lambda: True)


def test_sampling_spreads_over_nights_and_is_bounded(lib_and_incoming, monkeypatch):
    lib, _ = lib_and_incoming
    monkeypatch.setattr(fc, "SUBS_PER_TARGET", 2)
    r = fc.run(lib)
    assert r["subs_sampled"] == 6
    # Two subs of a two-night target come from its two nights.
    assert r["filter_card"]["LP"]["nights"] >= 2
    monkeypatch.setattr(fc, "MAX_SUBS", 3)
    assert fc.run(lib)["subs_sampled"] == 3


@pytest.mark.parametrize("value, token", [
    ("LP", "LP"), (" IRCUT ", "IRCUT"), ("UV/IR", "UV/IR"), ("Duo-Band", "Duo-Band"),
    ("", "(blank)"), (True, "(true)"),
    ("/mnt/tank/x", None), ("C:\\x", None), ("SN12345", None),
    ("a very long filter name", None), ("lat 51.5 -0.1", None),
])
def test_token_lets_only_plain_words_through(value, token):
    assert fc._token(value) == token


def test_ready_and_registered(lib_and_incoming, tmp_path):
    from seestack.io.library import Library

    lib, _ = lib_and_incoming
    assert fc.ready(lib)
    empty = Library.open_or_create(tmp_path / "empty")
    try:
        assert not fc.ready(empty)
    finally:
        empty.close()
    assert ("filter_card_values", 1) in [(d.name, d.version) for d in registry()]
