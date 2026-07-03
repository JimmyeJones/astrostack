"""Tone & colour operations: stretch (the boundary), curves, levels, saturation,
white balance, SCNR (green removal), and photometric colour calibration."""

from __future__ import annotations

import numpy as np

from seestack.edit.registry import (
    EditContext, EditParam, OpSpec, as_rgb, finite_mask, luminance, register,
)

_MODE_CC = ["gray_star", "gaia"]


# --- the single stretch boundary -------------------------------------------

def _stretch(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from seestack.render.thumbnail import asinh_stretch, autostretch

    mode = str(params.get("mode", "asinh"))
    if mode == "stf":
        return autostretch(rgb, target_bg=float(params.get("target_bg", 0.20)))
    return asinh_stretch(rgb, stretch=float(params.get("stretch", 0.5)),
                         black=float(params.get("black", 0.35)))


# --- nonlinear tone shapers (operate in display space [0,1]) ----------------

def _curves(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    pts = params.get("points") or [[0.0, 0.0], [1.0, 1.0]]
    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    grid = np.linspace(0.0, 1.0, 256)
    lut = np.interp(grid, xs, ys)  # monotone-ish piecewise-linear LUT
    out = as_rgb(rgb).copy()
    mask = finite_mask(out)
    for c in range(3):
        chan = out[..., c]
        chan[mask] = np.interp(np.clip(chan[mask], 0.0, 1.0), grid, lut)
    return out


def _levels(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    black = float(params.get("black", 0.0))
    white = float(params.get("white", 1.0))
    gamma = max(1e-3, float(params.get("gamma", 1.0)))
    rng = max(white - black, 1e-6)
    out = as_rgb(rgb).copy()
    mask = finite_mask(out)
    for c in range(3):
        chan = out[..., c]
        x = np.clip((chan[mask] - black) / rng, 0.0, 1.0)
        chan[mask] = x ** (1.0 / gamma)
    return out


def _saturation(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    amount = float(params.get("amount", 1.0))
    out = as_rgb(rgb).copy()
    lum = luminance(out)[..., None]
    sat = lum + amount * (out - lum)
    mask = finite_mask(out)
    out[mask] = np.clip(sat[mask], 0.0, 1.0)
    return out


def _white_balance(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    gains = np.array([
        float(params.get("r", 1.0)),
        float(params.get("g", 1.0)),
        float(params.get("b", 1.0)),
    ], dtype=np.float32)
    return as_rgb(rgb) * gains


def _scnr(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    """Subtractive chromatic noise reduction: clip the green channel to the
    neutral of red/blue (removes the green cast common on OSC nebulae)."""
    amount = float(params.get("amount", 0.8))
    out = as_rgb(rgb).copy()
    r, g, b = out[..., 0], out[..., 1], out[..., 2]
    neutral = np.maximum.reduce([r, b]) if str(params.get("mode", "average")) == "maximum" \
        else 0.5 * (r + b)
    capped = np.minimum(g, neutral)
    out[..., 1] = g + amount * (capped - g)
    return out


def _color_calibrate(rgb: np.ndarray, params: dict, ctx: EditContext) -> np.ndarray:
    from seestack.post.color_cal import ColorCalibrationOptions, calibrate_color

    mode = str(params.get("mode", "gray_star"))
    # gaia needs a WCS + network; on the decimated preview proxy fall back to gray_star.
    if mode == "gaia" and (ctx.is_proxy or ctx.wcs is None):
        mode = "gray_star"
    opts = ColorCalibrationOptions(enabled=True, mode=mode)
    calibrated, _ = calibrate_color(rgb, ctx.wcs, opts)
    return calibrated


register(OpSpec(
    id="tone.color_calibrate", label="Color calibration", group="tone",
    stage="linear", apply=_color_calibrate, proxy_safe=True,
    help="Photometric white balance from star colours (gray-star offline, Gaia on export).",
    params=[EditParam("mode", "Mode", "enum", default="gray_star", options=_MODE_CC)],
))

register(OpSpec(
    id="tone.white_balance", label="White balance", group="tone", stage="linear",
    apply=_white_balance, proxy_safe=True,
    help="Manual per-channel gain (applied to linear data).",
    params=[
        EditParam("r", "Red gain", "float", default=1.0, min=0.0, max=3.0, step=0.01),
        EditParam("g", "Green gain", "float", default=1.0, min=0.0, max=3.0, step=0.01),
        EditParam("b", "Blue gain", "float", default=1.0, min=0.0, max=3.0, step=0.01),
    ],
))

register(OpSpec(
    id="tone.stretch", label="Stretch", group="tone", stage="any", is_stretch=True,
    apply=_stretch, proxy_safe=True,
    help="Tone-map linear data to display. Asinh reveals faint detail naturally.",
    params=[
        EditParam("mode", "Curve", "enum", default="asinh", options=["asinh", "stf"],
                  help="Asinh: manual strength/black point. STF: auto-stretch to a target sky level."),
        EditParam("stretch", "Strength", "float", default=0.5, min=0.0, max=1.0, step=0.01,
                  help="0 ≈ linear, 1 ≈ extreme faint lift.", depends_on="mode=asinh"),
        EditParam("black", "Black point", "float", default=0.35, min=0.0, max=1.0, step=0.01,
                  help="Higher darkens/cleans the sky.", depends_on="mode=asinh"),
        EditParam("target_bg", "STF sky level", "float", default=0.20, min=0.02, max=0.6,
                  step=0.01, depends_on="mode=stf",
                  help="Target background brightness for the auto-stretch (higher = brighter sky)."),
    ],
))

register(OpSpec(
    id="tone.curves", label="Curves", group="tone", stage="nonlinear", apply=_curves,
    proxy_safe=True, help="Freeform tone curve over all channels.",
    params=[EditParam("points", "Curve", "curve", default=[[0.0, 0.0], [1.0, 1.0]])],
))

register(OpSpec(
    id="tone.levels", label="Levels", group="tone", stage="nonlinear", apply=_levels,
    proxy_safe=True, help="Black/white point + gamma.",
    params=[
        EditParam("black", "Black", "float", default=0.0, min=0.0, max=1.0, step=0.01),
        EditParam("white", "White", "float", default=1.0, min=0.0, max=1.0, step=0.01),
        EditParam("gamma", "Gamma", "float", default=1.0, min=0.1, max=5.0, step=0.05),
    ],
))

register(OpSpec(
    id="tone.saturation", label="Saturation", group="tone", stage="nonlinear",
    apply=_saturation, proxy_safe=True, help="Boost or reduce colour, preserving luminance.",
    params=[EditParam("amount", "Amount", "float", default=1.0, min=0.0, max=3.0, step=0.05)],
))

register(OpSpec(
    id="tone.scnr", label="SCNR (green removal)", group="tone", stage="any",
    apply=_scnr, proxy_safe=True, help="Remove the green colour cast on OSC nebulae.",
    params=[
        EditParam("amount", "Amount", "float", default=0.8, min=0.0, max=1.0, step=0.05),
        EditParam("mode", "Protect", "enum", default="average", options=["average", "maximum"],
                  group="advanced"),
    ],
))
