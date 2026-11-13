"""A download named after an editor export's typed *Output name* still downloads.

An editor export stores what the user typed in *Output name* as the run's
``output_basename`` (only the files on disk are sanitised), and the Full-res PNG,
phone-wallpaper and share-JPEG routes built ``Content-Disposition`` from it with
``f'attachment; filename="{name}"'``. "Orion – final" (an en dash) or "M42 ✨"
made Starlette's Latin-1 header encoding raise — a 500 instead of the picture —
and a ``"`` in the name closed the quoted filename early. The fix routes every
hand-built header through ``webapp.routers._disposition.attachment`` (RFC 6266:
an ASCII fallback plus ``filename*=UTF-8''…``), the shape ``FileResponse``
already sends for the FITS/TIFF/preview downloads of the same run.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from webapp.routers._disposition import attachment

# The solved-run and job-wait helpers of the export-WCS tests, loaded by path:
# putting ``tests/webapp`` on ``sys.path`` would shadow the ``webapp`` package.
_spec = importlib.util.spec_from_file_location(
    "_export_wcs_helpers", Path(__file__).with_name("test_editor_export_wcs.py"))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
_make_solved_run, _wait_job = _helpers._make_solved_run, _helpers._wait_job

ROUTERS = Path(__file__).resolve().parents[2] / "webapp" / "routers"


def _offered_name(header: str) -> str:
    """What a client that honours RFC 5987 (every current browser, and the
    frontend's ``DownloadMenuItem``) saves the file as."""
    star = re.search(r"filename\*=UTF-8''([^;]+)", header)
    if star:
        return unquote(star.group(1))
    plain = re.fullmatch(r'attachment; filename="([^"]*)"', header)
    assert plain, header
    return plain.group(1)


@pytest.mark.parametrize("name", [
    "M_42_edit.jpg", "Orion – final.jpg", "M42 ✨.jpg", 'my "best" M42.jpg',
    "Orión.jpg", "back\\slash.png",
])
def test_attachment_header_is_latin1_safe_and_round_trips(name):
    header = attachment(name)
    header.encode("latin-1")  # what Starlette does to every header value
    assert header.isascii()
    assert _offered_name(header) == name
    # The quoted fallback never carries a bare quote or backslash.
    fallback = re.match(r'attachment; filename="([^"]*)"', header)
    assert fallback and "\\" not in fallback.group(1)


def test_a_plain_ascii_name_keeps_the_old_header_byte_for_byte():
    assert attachment("M_42_edit_fullres.png") == \
        'attachment; filename="M_42_edit_fullres.png"'


def test_no_router_hand_builds_a_filename_header_from_a_variable():
    """Pin the class, not the three routes: a new ``Response`` download that
    formats a name into the header by hand reintroduces the 500."""
    offenders = []
    for path in ROUTERS.glob("*.py"):
        if path.name == "_disposition.py":
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"""f['"]attachment; filename=\S*\{(?!year\})""", line):
                offenders.append(f"{path.name}:{i}")
    assert offenders == []


@pytest.mark.parametrize("typed", ["Orion – final", "M42 ✨", 'my "best" M42'])
def test_downloads_of_an_export_with_a_typed_name_answer(client, solved_library,
                                                         typed):
    safe = client.get("/api/targets").json()[0]["safe_name"]
    rid, _ = _make_solved_run(solved_library, safe)
    r = client.post(f"/api/targets/{safe}/stack-runs/{rid}/editor/export",
                    json={"recipe": {"ops": [{"id": "stretch.stf", "params": {}}]},
                          "output_name": typed})
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["state"] == "done", job
    new_id = job["result"]["run_id"]

    for route, suffix in (("full-res-png", "_fullres.png"),
                          ("wallpaper", "_phone_wallpaper.jpg"),
                          ("jpeg", ".jpg")):
        resp = client.get(f"/api/targets/{safe}/stack-runs/{new_id}/{route}")
        assert resp.status_code == 200, (route, resp.text[:200])
        assert _offered_name(resp.headers["content-disposition"]) == typed + suffix
