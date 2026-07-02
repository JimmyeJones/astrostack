"""
Apply master calibration frames to a raw light frame.

A :class:`CalibrationMasters` bundle is built **once per stack** (loading the
master FITS into RAM) and then shared, read-only, across the worker threads
that load each light frame. Each worker calls :meth:`apply_raw` on the raw
Bayer mosaic before debayering.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Flat values below this fraction of the mean are floored before dividing, so a
# near-black corner of the flat (or a dead pixel) can't explode into a huge
# spike in the calibrated light frame.
_FLAT_FLOOR = 0.1


@dataclass
class CalibrationMasters:
    """Loaded master dark / flat ready to apply to raw frames.

    The flat is stored *pre-normalised* to a mean of 1.0 (with a floor) so the
    per-frame hot path is a single divide.
    """

    dark: np.ndarray | None = None
    flat_norm: np.ndarray | None = None
    dark_path: str | None = None
    flat_path: str | None = None

    @classmethod
    def load(
        cls,
        dark_path: str | None = None,
        flat_path: str | None = None,
        flat_dark_path: str | None = None,
    ) -> "CalibrationMasters":
        """Load masters from disk. Any path may be ``None``.

        ``flat_dark_path`` is an optional dark/bias matched to the flat's own
        exposure. When given it is subtracted from the flat *before*
        normalising, so the flat captures only the illumination pattern rather
        than the illumination pattern riding on the flat's dark-current + bias
        pedestal — a more correct flat (this is what DSS/Siril call a
        "flat-dark"). Without it the flat is mean-normalised as-is, unchanged.
        """
        from seestack.calibrate.masters import load_master

        dark = None
        flat_norm = None
        if dark_path:
            dark, _ = load_master(dark_path)
            dark = np.asarray(dark, dtype=np.float32)
        if flat_path:
            flat, _ = load_master(flat_path)
            flat = np.asarray(flat, dtype=np.float32)
            if flat_dark_path:
                flat_dark, _ = load_master(flat_dark_path)
                flat_dark = np.asarray(flat_dark, dtype=np.float32)
                if flat_dark.shape == flat.shape:
                    flat = flat - flat_dark
                else:
                    log.warning(
                        "flat-dark %s is %s but the flat is %s; skipping the "
                        "flat-dark subtraction", flat_dark_path,
                        flat_dark.shape, flat.shape,
                    )
            mean = float(np.nanmean(flat))
            if not np.isfinite(mean) or mean <= 0:
                log.warning("flat master %s has non-positive mean; ignoring it", flat_path)
            else:
                fn = flat / mean
                # Floor tiny / non-finite values to 1.0 (= no correction there).
                flat_norm = np.where(np.isfinite(fn) & (fn > _FLAT_FLOOR), fn, 1.0
                                     ).astype(np.float32, copy=False)
        return cls(dark=dark, flat_norm=flat_norm,
                   dark_path=dark_path, flat_path=flat_path)

    @property
    def is_empty(self) -> bool:
        return self.dark is None and self.flat_norm is None

    def describe(self) -> str:
        parts = []
        if self.dark is not None:
            parts.append("dark")
        if self.flat_norm is not None:
            parts.append("flat")
        return "+".join(parts) if parts else "none"

    def validate(self, shape: tuple[int, int]) -> None:
        """Raise ``ValueError`` if a loaded master doesn't match ``shape``.

        Called once, up front, against the reference frame's raw dimensions so
        a camera/binning mismatch fails fast with a clear message instead of
        silently skipping the correction on every frame.
        """
        for name, arr in (("dark", self.dark), ("flat", self.flat_norm)):
            if arr is not None and tuple(arr.shape) != tuple(shape):
                raise ValueError(
                    f"calibration {name} master is {arr.shape[1]}×{arr.shape[0]} "
                    f"but the frames are {shape[1]}×{shape[0]} — they must match "
                    f"(same camera, binning and no debayering)."
                )

    def apply_raw(self, raw: np.ndarray) -> np.ndarray:
        """Return the calibrated raw mosaic: ``(raw − dark) / flat_norm``.

        Masters whose shape doesn't match ``raw`` are skipped (this is the
        defensive per-frame guard; :meth:`validate` is the up-front check).
        Returns a new float32 array — the input is not modified.
        """
        out = np.asarray(raw, dtype=np.float32)
        if self.dark is not None and self.dark.shape == out.shape:
            out = out - self.dark
        if self.flat_norm is not None and self.flat_norm.shape == out.shape:
            out = out / self.flat_norm
        return out.astype(np.float32, copy=False)
