"""
Dark / flat / bias frame calibration.

Calibration removes two instrument signatures from each light frame *before*
it is debayered and stacked:

  * **Dark subtraction** — a master dark (mean/median of many dark frames taken
    at the same exposure, gain and sensor temperature) captures thermal current
    and the sensor bias/amp-glow. Subtracting it removes hot pixels and the
    fixed thermal pattern: ``light − dark``.

  * **Flat division** — a master flat (frames of an evenly-lit field) captures
    vignetting and dust shadows. Dividing by the *mean-normalised* flat evens
    the illumination out: ``light / (flat / mean(flat))``.

Both corrections happen in the **raw Bayer domain** (the 2-D mosaic, before
debayering) because that's where the calibration frames themselves live — a
dark/flat is a raw sensor readout, so subtracting/dividing per-mosaic-pixel is
the physically correct operation. See :func:`CalibrationMasters.apply_raw`.

The module is split into:

  * :mod:`seestack.calibrate.masters` — *build* a master frame from a set of
    raw FITS files and read/write it as FITS.
  * :mod:`seestack.calibrate.apply` — *apply* loaded masters to a light frame.
"""

from __future__ import annotations

from seestack.calibrate.apply import CalibrationMasters
from seestack.calibrate.masters import (
    MasterMeta,
    build_master,
    load_master,
    save_master,
)

__all__ = [
    "CalibrationMasters",
    "MasterMeta",
    "build_master",
    "load_master",
    "save_master",
]
