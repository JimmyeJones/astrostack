"""Settings redesign slice 5 — "How pictures are made" (v0.500.0).

The four picture cards are UI only, but two of their claims are about the
server, and these pin them:

* the drizzle card's **"Let AstroStack decide instead"** sends the global
  ``default_stack_options`` back *without* its ``drizzle`` key. That only hands
  the choice back if a settings PUT **replaces** the blob rather than merging
  into it — otherwise the saved ``drizzle`` would survive the save and the card
  would be lying one reload later;
* an old ``config.json`` carrying the four fields the cards write, and a
  stacking-defaults blob, loads and round-trips unchanged (§9).
"""

from __future__ import annotations

import json
from pathlib import Path

from webapp.config import SettingsStore
from webapp.walkaway import apply_auto_drizzle, rejection_choice_expressed


def _auto_drizzle_allowed(dso: dict) -> bool:
    return apply_auto_drizzle(dict(dso), enabled=True, unattended=True)["auto_drizzle"]


def test_dropping_drizzle_from_the_defaults_hands_the_choice_back(client):
    client.put("/api/settings", json={
        "auto_drizzle": True,
        "default_stack_options": {"drizzle": True, "quality_weighted": True},
    })
    before = client.get("/api/settings").json()["default_stack_options"]
    assert before["drizzle"] is True
    assert _auto_drizzle_allowed(before) is False   # the saved choice wins

    # What the card's button puts in the form, saved the way the page saves.
    r = client.put("/api/settings", json={
        "auto_drizzle": True, "default_stack_options": {"quality_weighted": True},
    })
    assert r.status_code == 200
    after = client.get("/api/settings").json()["default_stack_options"]
    assert "drizzle" not in after
    assert after == {"quality_weighted": True}      # nothing else touched
    assert _auto_drizzle_allowed(after) is True


def test_the_outlier_card_reads_the_same_keys_the_server_does():
    # `picturesMade.REJECT_KEYS` mirrors `walkaway.AUTO_REJECT_OPT_KEYS`; this is
    # the server half of that pairing (the vitest pins the client half).
    for key in ("auto_reject", "sigma_clip", "min_max_reject"):
        assert rejection_choice_expressed({key: False}) is True
    assert rejection_choice_expressed({"drizzle": True, "quality_weighted": True}) is False


def test_an_old_config_with_the_card_fields_round_trips_unchanged(tmp_path: Path):
    cfg = {
        "auto_reject_on_unattended": True, "auto_drizzle": False,
        "auto_crop_border": False, "auto_bind_calibration": True,
        "default_stack_options": {"drizzle": True, "sigma_clip": True},
    }
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "config.json").write_text(json.dumps(cfg))

    s = SettingsStore(str(tmp_path)).get()
    for k, v in cfg.items():
        assert getattr(s, k) == v

    # And again after the store has re-saved the file, as every boot does.
    s2 = SettingsStore(str(tmp_path)).get()
    for k, v in cfg.items():
        assert getattr(s2, k) == v
