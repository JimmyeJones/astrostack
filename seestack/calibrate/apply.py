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


def _sanitize_pedestal(arr: np.ndarray) -> np.ndarray:
    """Replace non-finite master dark/bias pixels with 0.0 (= no correction).

    ``build_master`` legitimately produces a NaN pixel where *no* input frame
    had finite data ("genuinely no data" — see ``masters.py``), and an imported
    third-party master can carry NaN/inf too. Subtracting such a pixel straight
    from the light (``light − dark``) would turn real, good signal into NaN/inf
    at that pixel of **every** calibrated frame — a permanent hole (NaN spreads
    through debayer and reads as zero coverage in the stack) or a reduction-
    poisoning ``±inf``. A no-data *pedestal* pixel means "no correction here",
    so it must subtract 0, mirroring the flat's floor-to-1.0 at load time
    (``flat_norm``). Done once at load, off the per-frame hot path.
    """
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


@dataclass
class CalibrationMasters:
    """Loaded master dark / flat ready to apply to raw frames.

    The flat is stored *pre-normalised* to a mean of 1.0 (with a floor) so the
    per-frame hot path is a single divide.
    """

    dark: np.ndarray | None = None
    flat_norm: np.ndarray | None = None
    bias: np.ndarray | None = None
    # Boolean mask of master-dark pixels that were non-finite before sanitizing
    # (= "genuinely no data"), or None when the dark is all-finite (the common
    # real-Seestar case, so no extra array is retained). Used only on the
    # exposure-scaling path to keep a no-data dark pixel meaning "no correction"
    # (see :meth:`_effective_dark`); the unscaled path already subtracts the
    # sanitized 0 there.
    dark_nodata_mask: np.ndarray | None = None
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
        dark_nodata_mask = None
        dark_exposure_s = None
        flat_norm = None
        bias = None
        bias_exposure_s = None
        if dark_path:
            dark, dark_meta = load_master(dark_path)
            dark = np.asarray(dark, dtype=np.float32)
            # Remember which dark pixels are genuinely no-data *before* they're
            # sanitized to 0, so the exposure-scaling path can keep them at
            # "no correction" instead of scaling the 0 into a spurious pedestal.
            nodata = ~np.isfinite(dark)
            dark_nodata_mask = nodata if bool(nodata.any()) else None
            dark = _sanitize_pedestal(dark)
            dark_exposure_s = dark_meta.exposure_s
        if bias_path:
            bias, bias_meta = load_master(bias_path)
            bias = _sanitize_pedestal(np.asarray(bias, dtype=np.float32))
            bias_exposure_s = bias_meta.exposure_s
        if flat_path:
            flat, _ = load_master(flat_path)
            flat = np.asarray(flat, dtype=np.float32)
            # Map non-finite flat pixels to NaN so an ``inf`` is handled exactly
            # like a NaN below (ignored by ``nanmean`` and floored to 1.0 = no
            # correction there) instead of poisoning the mean and dropping the
            # *whole* flat. A flat is multiplicative, so ``_sanitize_pedestal``'s
            # 0.0 would be wrong here — NaN is the right "no data" sentinel. This
            # mirrors the flat-dark sanitisation just below; ``build_master``
            # already emits NaN (not inf) for no-data pixels, so this only bites a
            # hand-crafted/imported flat FITS carrying an inf. An all-finite flat
            # (the common case) is byte-for-byte unchanged.
            if not np.isfinite(flat).all():
                flat = np.where(np.isfinite(flat), flat, np.nan).astype(
                    np.float32, copy=False)
            if flat_dark_path:
                flat_dark, _ = load_master(flat_dark_path)
                # Sanitize non-finite flat-dark pixels to 0 (= no subtraction
                # there), mirroring the master dark/bias. Without this an imported
                # third-party flat-dark carrying an inf makes the flat's nanmean
                # non-finite and silently drops the *whole* flat (below), while a
                # NaN would only be masked out later by the flat floor.
                flat_dark = _sanitize_pedestal(
                    np.asarray(flat_dark, dtype=np.float32))
                if flat_dark.shape == flat.shape:
                    flat = flat - flat_dark
                else:
                    log.warning(
                        "flat-dark %s is %s but the flat is %s; skipping the "
                        "flat-dark subtraction", flat_dark_path,
                        flat_dark.shape, flat.shape,
                    )
            mean = float(np.nanmean(flat))
            if not np.isfinite(mean):
                log.warning("flat master %s has a non-finite mean; ignoring it", flat_path)
            elif mean <= 0:
                log.warning("flat master %s has non-positive mean; ignoring it", flat_path)
            else:
                fn = flat / mean
                # Floor tiny / non-finite values to 1.0 (= no correction there).
                flat_norm = np.where(np.isfinite(fn) & (fn > _FLAT_FLOOR), fn, 1.0
                                     ).astype(np.float32, copy=False)
        return cls(dark=dark, flat_norm=flat_norm, bias=bias,
                   dark_nodata_mask=dark_nodata_mask,
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
                scaled = (self.bias + (dark - self.bias) * ratio).astype(
                    np.float32, copy=False)
                # A genuinely no-data dark pixel (sanitized to 0) must still mean
                # "no correction" here, exactly as on the unscaled path. Scaling
                # turns that 0 into ``bias·(1 − ratio)`` — a spurious pedestal
                # added into every calibrated light there — so restore 0 at those
                # pixels. ``scaled`` is a fresh array, so the in-place write can't
                # mutate the shared master dark/bias.
                if self.dark_nodata_mask is not None:
                    scaled[self.dark_nodata_mask] = 0.0
                return scaled
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
