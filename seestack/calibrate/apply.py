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
    bias: np.ndarray | None = None
    dark_path: str | None = None
    flat_path: str | None = None
    bias_path: str | None = None
    # Exposure of the master dark / bias in seconds (from their FITS headers),
    # None when the header didn't carry it. Used only for optional dark
    # exposure-scaling (see ``scale_dark_to_light`` / :meth:`_effective_dark`).
    dark_exposure_s: float | None = None
    bias_exposure_s: float | None = None
    # When True *and* a master bias is available, a master dark shot at a
    # different exposure than the light is scaled to the light's integration
    # time before subtraction (see :meth:`_effective_dark`). Off by default.
    scale_dark_to_light: bool = False

    @classmethod
    def load(
        cls,
        dark_path: str | None = None,
        flat_path: str | None = None,
        flat_dark_path: str | None = None,
        bias_path: str | None = None,
        *,
        scale_dark_to_light: bool = False,
    ) -> "CalibrationMasters":
        """Load masters from disk. Any path may be ``None``.

        ``flat_dark_path`` is an optional dark/bias matched to the flat's own
        exposure. When given it is subtracted from the flat *before*
        normalising, so the flat captures only the illumination pattern rather
        than the illumination pattern riding on the flat's dark-current + bias
        pedestal — a more correct flat (this is what DSS/Siril call a
        "flat-dark"). Without it the flat is mean-normalised as-is, unchanged.

        ``bias_path`` is an optional master bias, subtracted from the *lights*
        as the readout pedestal — but **only when no master dark is chosen**. A
        master dark already contains the bias, so subtracting both would
        double-subtract it; when ``dark_path`` is given the bias is loaded for
        provenance/shape reasons but never applied to the lights (see
        :meth:`apply_raw`). This gives a correct ``(light − bias) / flat``
        calibration for the common bias+flat (no dark) workflow.

        ``scale_dark_to_light`` opts into exposure-scaling the dark: when a
        master bias is also loaded and the dark's exposure differs from the
        light's, the dark's *dark current* is scaled to the light's integration
        time — ``dark = bias + (dark − bias)·(t_light / t_dark)`` — so a dark
        library shot at one exposure can still calibrate subs at another. It
        needs the bias to hold the exposure-independent readout pedestal fixed;
        without a bias (or an unknown exposure) the dark is used unscaled.
        """
        from seestack.calibrate.masters import load_master

        dark = None
        dark_exposure_s = None
        flat_norm = None
        bias = None
        bias_exposure_s = None
        if dark_path:
            dark, dark_meta = load_master(dark_path)
            dark = np.asarray(dark, dtype=np.float32)
            dark_exposure_s = dark_meta.exposure_s
        if bias_path:
            bias, bias_meta = load_master(bias_path)
            bias = np.asarray(bias, dtype=np.float32)
            bias_exposure_s = bias_meta.exposure_s
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
        return cls(dark=dark, flat_norm=flat_norm, bias=bias,
                   dark_path=dark_path, flat_path=flat_path, bias_path=bias_path,
                   dark_exposure_s=dark_exposure_s, bias_exposure_s=bias_exposure_s,
                   scale_dark_to_light=scale_dark_to_light)

    @property
    def is_empty(self) -> bool:
        return self.dark is None and self.flat_norm is None and self.bias is None

    @property
    def _bias_applies(self) -> bool:
        """The master bias is subtracted from lights only when no dark is set —
        a dark already carries the bias pedestal, so applying both would
        double-subtract it."""
        return self.dark is None and self.bias is not None

    def describe(self) -> str:
        parts = []
        if self.dark is not None:
            parts.append("dark")
        elif self._bias_applies:
            parts.append("bias")
        if self.flat_norm is not None:
            parts.append("flat")
        return "+".join(parts) if parts else "none"

    def validate(self, shape: tuple[int, int]) -> None:
        """Raise ``ValueError`` if a loaded master doesn't match ``shape``.

        Called once, up front, against the reference frame's raw dimensions so
        a camera/binning mismatch fails fast with a clear message instead of
        silently skipping the correction on every frame.
        """
        for name, arr in (("dark", self.dark), ("flat", self.flat_norm),
                          ("bias", self.bias)):
            if arr is not None and tuple(arr.shape) != tuple(shape):
                raise ValueError(
                    f"calibration {name} master is {arr.shape[1]}×{arr.shape[0]} "
                    f"but the frames are {shape[1]}×{shape[0]} — they must match "
                    f"(same camera, binning and no debayering)."
                )

    def _effective_dark(self, light_exposure_s: float | None) -> np.ndarray | None:
        """The dark to subtract, exposure-scaled to the light when opted in.

        Returns the stored dark unchanged unless ``scale_dark_to_light`` is on,
        a master bias with the dark's shape is available, and both exposures are
        known and positive. In that case it returns
        ``bias + (dark − bias)·(t_light / t_dark)`` — the dark current scaled to
        the light's integration time while the exposure-independent bias pedestal
        stays fixed — so a dark shot at one exposure calibrates subs at another.
        A ratio of ~1 (matched exposures) is left as the plain dark to avoid
        needless float work and rounding.
        """
        dark = self.dark
        if (self.scale_dark_to_light and dark is not None and self.bias is not None
                and self.bias.shape == dark.shape
                and self.dark_exposure_s and light_exposure_s
                and self.dark_exposure_s > 0 and light_exposure_s > 0):
            ratio = float(light_exposure_s) / float(self.dark_exposure_s)
            if abs(ratio - 1.0) > 1e-3:
                return (self.bias + (dark - self.bias) * ratio).astype(
                    np.float32, copy=False)
        return dark

    def apply_raw(self, raw: np.ndarray,
                  light_exposure_s: float | None = None) -> np.ndarray:
        """Return the calibrated raw mosaic: ``(raw − pedestal) / flat_norm``.

        The subtracted pedestal is the master dark when one is set, otherwise
        the master bias if one is set (``(light − bias) / flat``) — never both,
        so the bias is not double-subtracted through a dark that already
        contains it. When ``scale_dark_to_light`` is enabled and a bias is
        available, the dark is first scaled to ``light_exposure_s`` (see
        :meth:`_effective_dark`); passing ``None`` (the default, and what direct
        callers use) simply leaves the dark unscaled. Masters whose shape
        doesn't match ``raw`` are skipped (this is the defensive per-frame guard;
        :meth:`validate` is the up-front check). Returns a new float32 array —
        the input is not modified.
        """
        out = np.asarray(raw, dtype=np.float32)
        dark = self._effective_dark(light_exposure_s)
        if dark is not None and dark.shape == out.shape:
            out = out - dark
        elif self._bias_applies and self.bias.shape == out.shape:
            out = out - self.bias
        if self.flat_norm is not None and self.flat_norm.shape == out.shape:
            out = out / self.flat_norm
        result = out.astype(np.float32, copy=False)
        # Honour the "returns a new array" contract even on the no-masters path:
        # if nothing above produced a fresh array (an empty bundle applied to an
        # already-float32 input aliases ``raw``), copy so a caller that mutates
        # the result in place can never corrupt the shared source frame. Any
        # applied master already yields a fresh array, so this only copies on the
        # otherwise-aliasing empty path — never a hot-path double-copy.
        if result is raw:
            result = result.copy()
        return result
