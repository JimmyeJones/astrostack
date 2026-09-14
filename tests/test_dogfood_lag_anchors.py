"""``agent-dogfood.sh --incoming-lag`` must still be pointing at real things.

The seeding step reaches into the app by **name**: it calls
``webapp.sample_data._write_sample_fits`` to write the subs and reads
``/api/incoming-lag`` to report what the app then says. Both links are strings in
a shell script, and a string is exactly the kind of link that rots silently —
rename either and the pass keeps running, prints a warning nobody reads, and the
one state this flag exists to photograph quietly stops being reachable. That is
the failure `test_dogfood_probe_anchors.py` was written for, one file over; this
is the same guard for the other half of the tooling.
"""

from __future__ import annotations

import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "agent-dogfood.sh"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_flag_is_wired_and_off_by_default():
    """A fault state must never be what the default pass measures — that is the
    whole argument for it being a flag (see the script's own header)."""
    src = _script()
    assert "DO_LAG=0" in src, "the flag no longer defaults off"
    assert "--incoming-lag) DO_LAG=1" in src, "the flag is no longer parsed"
    assert "--incoming-lag" in src.split("set -euo pipefail")[0], (
        "the flag vanished from the usage header, which is what `-h` prints"
    )


def test_the_writer_it_calls_still_exists_with_that_signature():
    from webapp.sample_data import _write_sample_fits

    assert "_write_sample_fits" in _script()
    params = inspect.signature(_write_sample_fits).parameters
    # The script calls it as `_write_sample_fits(p, index=i, star_shift=(0., 0.))`.
    assert set(params) >= {"path", "index", "star_shift"}


def test_the_endpoint_it_reads_still_exists():
    from webapp.main import create_app

    assert "/api/incoming-lag" in _script()
    assert "/api/incoming-lag" in create_app().openapi()["paths"]


def test_the_seeded_subs_are_old_enough_for_the_note_to_speak():
    """The note deliberately stays silent on a folder that is still changing
    (`LAG_MIN_AGE_S`), so a pass that seeded *fresh* subs would photograph
    nothing and read as a clean Dashboard — the exact false negative this flag
    exists to remove."""
    from webapp.incominglag import LAG_MIN_AGE_S

    src = _script()
    assert "DOGFOOD_LAG_DAYS:-11" in src
    assert 11 * 86400 > LAG_MIN_AGE_S
