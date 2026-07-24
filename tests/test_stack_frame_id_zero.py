"""Per-frame weight/photometric-scale lookups must honour a frame whose DB id is 0.

The weight and photometric-scale maps are keyed by the frame's real ``id`` (frames
with ``id is None`` are skipped when the maps are built — see
``weighting.compute_frame_weights`` / ``photometric.compute_photometric_scales``).
The stacking passes used to read them with ``mapping.get(f.id or -1, 1.0)``, which
silently drops a frame with ``id == 0`` (``0 or -1 == -1``) to the neutral default
instead of its real value — a store-key/lookup-key mismatch that corrupts that
frame's contribution to the *final image*. Unreachable today (SQLite autoincrement
ids start at 1) but a genuine latent correctness bug in the hot path; the lookup now
uses ``f.id if f.id is not None else -1`` so store- and lookup-keys stay identical.
"""

import numpy as np
import pytest

pytest.importorskip("astropy")

from seestack.io.project import FrameRow
from seestack.stack import stacker
from seestack.stack.stacker import StackOptions, _pass


def test_pass_applies_weight_and_scale_for_frame_id_zero(monkeypatch):
    # A frame whose DB id is exactly 0 — a legitimate map key the old
    # ``f.id or -1`` lookup dropped to the default.
    frame = FrameRow(id=0, source_path="a.fit")
    win = np.ones((2, 2, 3), dtype=np.float32)

    # Bypass the real load→calibrate→debayer→reproject; hand the pass a fixed
    # window so we can observe exactly the weight/scale it applies.
    monkeypatch.setattr(stacker, "_align_for_stack",
                        lambda *a, **k: (win.copy(), 0, 0, False))

    captured: list[tuple[float, float]] = []

    def consumer(rgb, y0, x0, w):
        captured.append((float(rgb[0, 0, 0]), float(w)))

    used = _pass(
        [frame], frame, "wcs-text", (2, 2),
        {0: 3.0},                       # this frame's real quality weight
        options=StackOptions(max_workers=1),
        phase_label="Stack",
        consumer=consumer,
        progress=lambda *a, **k: None,
        cancel=lambda: False,
        errors=[],
        photometric_scales={0: 2.0},    # this frame's real photometric scale
    )

    assert used == 1
    assert len(captured) == 1
    scaled_val, weight = captured[0]
    # Before the fix both fell through to the 1.0 default; now the id-0 frame
    # gets its real weight and its pixels are scaled by its real photometric scale.
    assert weight == pytest.approx(3.0)
    assert scaled_val == pytest.approx(2.0)  # 1.0 * scale 2.0
