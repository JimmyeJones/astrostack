"""output_name must never be able to write outside <project>/output/.

output_name flows in unvalidated from the web API (stack + editor "output
name" fields) all the way to write_stack_outputs' out_basename. A value like
"../../../etc/x" or "/etc/x" must not escape the project's output directory.
"""

from __future__ import annotations

import numpy as np
import pytest

from seestack.stack.output import _sanitize_basename, write_stack_outputs


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("master", "master"),
        ("../../../etc/passwd", "etc_passwd"),
        ("/etc/passwd", "etc_passwd"),
        ("..", "master"),
        ("...", "master"),
        ("", "master"),
        ("   ", "master"),
        ("a/b/../../c", "a_b_.._.._c"),
        ("m42 final!", "m42_final"),
    ],
)
def test_sanitize_basename(raw, expected):
    assert _sanitize_basename(raw) == expected


def test_sanitize_basename_strips_leading_trailing_separators():
    assert _sanitize_basename("-.hidden.-") == "hidden"


def test_sanitize_basename_caps_length():
    assert len(_sanitize_basename("a" * 500)) == 128


def test_write_stack_outputs_confines_files_to_project_output_dir(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    outside = tmp_path / "outside_marker"
    assert not outside.exists()

    rgb = np.zeros((8, 8, 3), dtype=np.float32)
    coverage = np.ones((8, 8), dtype=np.float32)

    paths = write_stack_outputs(
        project_dir=project_dir,
        rgb=rgb,
        coverage=coverage,
        wcs_text=None,
        out_basename="../../outside_marker",
    )

    # Nothing was written outside project_dir/output/.
    assert not outside.exists()
    for key in ("fits", "tiff", "preview", "coverage"):
        p = paths[key]
        assert p.is_relative_to(project_dir / "output")
        assert p.exists()
