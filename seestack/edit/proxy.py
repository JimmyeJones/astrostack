"""Downsampled linear proxy for live editor preview.

Editing a 150 MP drizzled/mosaic FITS interactively would exhaust RAM, so the
live preview always runs on a cached, decimated **linear** proxy (<=1500 px,
~27 MB float32). Decimation is by striding — like ``render_stack_png`` — so NaN
(uncovered/mosaic gaps) is preserved for the NaN-aware ops. The full-res image is
read once at build time and released; the cache is an ``.npy`` re-read with
``mmap_mode`` and copied per render. Geometry ops use ``proxy_scale`` to translate
between proxy and full coordinates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

PROXY_VERSION = 1
PROXY_MAX_PX = 1500
_PROXY_DIRNAME = "edit_proxies"


def proxy_dir(project_dir: Path) -> Path:
    return Path(project_dir) / "cache" / _PROXY_DIRNAME


def _proxy_paths(project_dir: Path, run_id: int) -> tuple[Path, Path]:
    d = proxy_dir(project_dir)
    return d / f"run_{run_id}.npy", d / f"run_{run_id}.json"


def _load_fits_rgb(fits_path: str | Path) -> np.ndarray:
    """Read a stack FITS into float32 ``(H, W, 3)`` (same logic as render_stack_png)."""
    from astropy.io import fits as _fits

    arr = np.asarray(_fits.getdata(fits_path), dtype=np.float32)
    if arr.ndim == 3:
        rgb = np.transpose(arr, (1, 2, 0))
        if rgb.shape[2] == 1:
            rgb = np.repeat(rgb, 3, axis=2)
        elif rgb.shape[2] > 3:
            rgb = rgb[..., :3]
    else:
        rgb = np.stack([arr, arr, arr], axis=-1)
    return rgb


def source_shape(fits_path: str | Path) -> tuple[int, int] | None:
    """``(height, width)`` of a stack FITS, from its header alone.

    Header-only, so asking "how big is the picture?" costs no pixels — the point
    of the exercise being a window read on a canvas too big to hold. ``None`` when
    the file is unreadable or carries no image.
    """
    from astropy.io import fits as _fits

    try:
        with _fits.open(fits_path, memmap=False) as hdul:
            hdr = hdul[0].header
            naxis = int(hdr.get("NAXIS", 0))
            if naxis < 2:
                return None
            return int(hdr["NAXIS2"]), int(hdr["NAXIS1"])
    except (OSError, KeyError, ValueError, TypeError):
        return None


def read_window_rgb(fits_path: str | Path, y0: int, x0: int,
                    height: int, width: int) -> np.ndarray:
    """One rectangle of a stack FITS as float32 ``(h, w, 3)``, read *as a window*.

    The whole point is that the file is never loaded: a 150 MP mosaic is
    gigabytes, and the loupe wants a few hundred pixels of it. ``hdu.section``
    reads only the requested slice off disk, so the cost is the window, not the
    canvas. Channel handling matches :func:`_load_fits_rgb` exactly, so a window
    holds the same numbers the proxy would have at those pixels.

    The rectangle must already be inside the canvas — :func:`source_shape` is how
    a caller clamps it.
    """
    from astropy.io import fits as _fits

    with _fits.open(fits_path, memmap=False) as hdul:
        hdu = hdul[0]
        ndim = int(hdu.header.get("NAXIS", 0))
        if ndim == 3:
            arr = np.asarray(hdu.section[:, y0:y0 + height, x0:x0 + width],
                             dtype=np.float32)
            rgb = np.transpose(arr, (1, 2, 0))
            if rgb.shape[2] == 1:
                rgb = np.repeat(rgb, 3, axis=2)
            elif rgb.shape[2] > 3:
                rgb = rgb[..., :3]
        else:
            plane = np.asarray(hdu.section[y0:y0 + height, x0:x0 + width],
                               dtype=np.float32)
            rgb = np.stack([plane, plane, plane], axis=-1)
    return np.ascontiguousarray(rgb, dtype=np.float32)


def build_proxy(fits_path: str | Path, max_px: int = PROXY_MAX_PX) -> tuple[np.ndarray, float]:
    """Return ``(proxy_rgb, proxy_scale)`` where ``proxy_scale = full_w / proxy_w``."""
    rgb = _load_fits_rgb(fits_path)
    h, w = rgb.shape[:2]
    longest = max(h, w)
    if longest > max_px:
        step = int(np.ceil(longest / max_px))
        rgb = rgb[::step, ::step]
        scale = float(step)
    else:
        scale = 1.0
    return np.ascontiguousarray(rgb, dtype=np.float32), scale


#: Side of the un-strided square :func:`source_grain_ratio` measures the noise
#: correlation on. Big enough that the two MADs are precise to ~0.1 % (a 512²
#: window gives ~0.5 M difference samples per lag), small enough that reading
#: five of them off a 150 MP mosaic through ``hdu.section`` costs a few MB and
#: milliseconds rather than the canvas.
_GRAIN_WINDOW_PX = 512

#: Key the per-run grain ratio is memoized under in the proxy's JSON sidecar.
#: Additive: a sidecar written before this existed simply lacks it and is filled
#: in on first use, so no ``PROXY_VERSION`` bump and no cached proxy is thrown
#: away on upgrade. ``null`` is a *cached decline* — a master that could not be
#: measured must not be re-read on every click either.
_GRAIN_RATIO_KEY = "grain_ratio"

#: Where the windows are taken from, as (row, column) fractions of the canvas.
#: Spread out on purpose: the median of the five is what makes one window that
#: happens to land on the target harmless.
_GRAIN_WINDOW_SPOTS = ((0.5, 0.5), (0.27, 0.27), (0.27, 0.73),
                       (0.73, 0.27), (0.73, 0.73))


def source_grain_ratio(fits_path: str | Path, step: int) -> float | None:
    """How much smaller the lag-1 noise estimator reads on this master's *own*
    grid than on a proxy decimated by ``step`` — i.e. the factor that puts a
    proxy-measured σ back on the full-resolution grid (see
    :func:`seestack.edit.noise.grain_lag_ratio`).

    Why it has to come from the file. ``build_proxy`` keeps no full-resolution
    pixels, and the quantity being measured *is* the noise's correlation over the
    first few full-resolution pixels — the thing striding throws away. So the
    honest measurement reads a few small **un-strided** windows straight out of
    the master through :func:`read_window_rgb` (a window read, never the canvas)
    and asks each one for its own lag-1-vs-lag-``step`` ratio. The ratio is
    dimensionless and each window answers in its own normalization, so the
    windows are directly comparable and the **median** of the measurable ones is
    the answer: a window that landed on the galaxy instead of the sky is outvoted
    rather than averaged in.

    ``step <= 1`` returns ``1.0`` without touching the file — a proxy that was
    not decimated is already on the full-resolution grid, which is what keeps an
    ordinary single-field stack's measurement byte-for-byte what it was.
    ``None`` when the file can't be read or no window could be measured, and then
    the caller simply applies no correction (today's number).
    """
    step = int(step)
    if step <= 1:
        return 1.0
    shape = source_shape(fits_path)
    if shape is None:
        return None
    h, w = shape
    side = min(_GRAIN_WINDOW_PX, h, w)
    # A window has to be several correlation lengths wider than the separation
    # being asked about, or the far-lag difference is measured on a handful of
    # rows; below that there is nothing to say and no correction is better than a
    # noisy one.
    if side < max(64, 4 * step):
        return None

    from seestack.edit.noise import grain_lag_ratio

    ratios: list[float] = []
    for fy, fx in _GRAIN_WINDOW_SPOTS:
        y0 = int(np.clip(round(fy * h - side / 2), 0, h - side))
        x0 = int(np.clip(round(fx * w - side / 2), 0, w - side))
        try:
            win = read_window_rgb(fits_path, y0, x0, side, side)
        except (OSError, KeyError, ValueError, TypeError, IndexError):
            return None
        # Mosaic gaps are NaN. A window that is mostly gap has too few difference
        # pairs to trust; skip it and let the others answer.
        if float(np.isfinite(win[..., 0]).mean()) < 0.5:
            continue
        r = grain_lag_ratio(win, step)
        if r is not None and np.isfinite(r) and r > 0:
            ratios.append(float(r))
    if not ratios:
        return None
    return float(np.median(ratios))


def cached_source_grain_ratio(project_dir: Path, run_id: int,
                              fits_path: str | Path, step: int) -> float | None:
    """:func:`source_grain_ratio` for a run, memoized in the proxy's own JSON
    sidecar — which is where it belongs: it is a property of the master file, as
    fixed for the run's lifetime as ``proxy_scale`` is, and both Auto endpoints
    ask for it on every click.

    Measured: the windowed reads are ~0.4 s on a canvas the owner's size
    (flat in the canvas — it is the windows, not the picture), against ~0.4 s for
    the ``build_proxy`` the same request pays once and then never again. Asking
    the file twice per click for an answer that cannot change would have put that
    back on the editor's main button; this pays it once per run, beside the proxy
    build, and reads a few bytes of JSON afterwards.

    Keyed on the master's mtime exactly as the proxy is, so a re-stack
    re-measures. A sidecar that can't be read or written is not an error — the
    value is simply measured again next time."""
    _npy_path, meta_path = _proxy_paths(project_dir, run_id)
    try:
        src_mtime = Path(fits_path).stat().st_mtime
    except OSError:
        src_mtime = 0.0
    meta: dict | None = None
    try:
        loaded = json.loads(meta_path.read_text())
        if isinstance(loaded, dict):
            meta = loaded
    except (OSError, ValueError):
        meta = None
    fresh = (meta is not None
             and abs(float(meta.get("src_mtime", -1)) - src_mtime) < 1e-6)
    if fresh and _GRAIN_RATIO_KEY in meta:
        cached = meta[_GRAIN_RATIO_KEY]
        return None if cached is None else float(cached)

    ratio = source_grain_ratio(fits_path, step)
    if fresh:
        try:
            meta[_GRAIN_RATIO_KEY] = ratio
            meta_path.write_text(json.dumps(meta))
        except (OSError, TypeError, ValueError):
            pass  # a cache that can't be written just gets measured again
    return ratio


def get_proxy(project_dir: Path, run_id: int, fits_path: str | Path) -> tuple[np.ndarray, float]:
    """Return a cached proxy (building/refreshing it as needed) as a writable copy."""
    npy_path, meta_path = _proxy_paths(project_dir, run_id)
    fits_path = Path(fits_path)
    try:
        src_mtime = fits_path.stat().st_mtime
    except OSError:
        src_mtime = 0.0

    if npy_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            if (meta.get("version") == PROXY_VERSION
                    and abs(float(meta.get("src_mtime", -1)) - src_mtime) < 1e-6):
                arr = np.load(npy_path, mmap_mode="r")
                return np.array(arr, dtype=np.float32), float(meta.get("proxy_scale", 1.0))
        except (OSError, ValueError):
            pass

    rgb, scale = build_proxy(fits_path)
    npy_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(npy_path, rgb)
    meta_path.write_text(json.dumps(
        {"version": PROXY_VERSION, "src_mtime": src_mtime, "proxy_scale": scale,
         "shape": list(rgb.shape)}
    ))
    return rgb, scale


def cached_proxy_shape(project_dir: Path, run_id: int) -> tuple[int, int] | None:
    """``(height, width)`` of the run's *cached* proxy, without loading it.

    A caller that has just rendered through :func:`get_proxy` can use this to ask
    "how big was the image the recipe rendered on?" — e.g. to check that a
    recipe's crop really did shrink the render — for the cost of one small JSON
    read. ``None`` when no proxy has been cached yet or the sidecar is unusable.
    """
    _npy_path, meta_path = _proxy_paths(project_dir, run_id)
    try:
        shape = json.loads(meta_path.read_text()).get("shape")
        return (int(shape[0]), int(shape[1]))
    except (OSError, ValueError, TypeError, IndexError, KeyError):
        return None


def coverage_path_for(fits_path: str | Path) -> Path:
    """The sibling per-pixel coverage FITS a stack run writes next to its output
    (``{basename}_coverage.fits`` — see :mod:`seestack.stack.output`)."""
    p = Path(fits_path)
    return p.with_name(f"{p.stem}_coverage.fits")


def frame_coverage_path_for(fits_path: str | Path) -> Path:
    """The sibling per-pixel **frame count** FITS a stack run writes next to its
    output (``{basename}_framecov.fits`` — see :mod:`seestack.stack.output`).

    Distinct from :func:`coverage_path_for`, whose map is a sum of per-frame
    *weights*. Runs recorded before this file existed simply don't have it.
    """
    p = Path(fits_path)
    return p.with_name(f"{p.stem}_framecov.fits")


def rejection_map_path_for(fits_path: str | Path) -> Path:
    """The sibling per-pixel **rejected-sample count** FITS a stack run writes
    next to its output (``{basename}_rejected.fits`` — see
    :mod:`seestack.stack.output`), when it was asked to record one.

    Off by default and absent on every run recorded before it existed, so a
    caller must treat "no file" as the ordinary case — it means "no overlay
    available", never an error.
    """
    p = Path(fits_path)
    return p.with_name(f"{p.stem}_rejected.fits")


def _load_map(path: Path, *, step: int) -> np.ndarray | None:
    """Load one 2-D float32 sibling map, strided like the proxy, or ``None``.

    **Read strided, never whole.** These maps are the run's *full-resolution*
    canvas — on a mosaic the size this owner shoots, a single float32 plane is
    hundreds of megabytes — and the live preview asks for two of them (coverage
    and frame coverage) on every render, twice per edit, because the preview PNG
    and the histogram are separate requests. Materialising the whole map and
    striding it afterwards (``np.asarray(fits.getdata(...), dtype=float32)``,
    which copies for the cast whatever memmap setting the read used) therefore
    cost a full-canvas allocation and a full-file read per request: measured on a
    480 MB coverage map at the proxy's own step of 8, **2.65 s cold / 0.21 s off
    the page cache, against 0.01 s** for the same values read through a memmap and
    strided in place. Slicing before the cast pages in only the rows the proxy
    grid actually samples, and the array that comes back is proxy-sized either
    way — the values are identical, which is what the parity test pins.
    """
    if not path.exists():
        return None
    from astropy.io import fits as _fits

    try:
        with _fits.open(path, memmap=True) as hdul:
            hdu = next((h for h in hdul if getattr(h, "data", None) is not None),
                       None)
            if hdu is None:
                return None
            cov = hdu.data
            # Stride first, cast last: both keep the sampled elements identical
            # (the decimation picks pixels; the cast rounds each one), and doing
            # it in this order is the whole point — the other order is a
            # full-canvas array.
            if step > 1:
                cov = cov[::step, ::step]
            if cov.ndim == 3:  # defensively collapse a stray per-channel map to 2D
                cov = cov[..., 0] if cov.shape[-1] <= 3 else cov.mean(axis=-1)
            return np.ascontiguousarray(cov, dtype=np.float32)
    except OSError:
        return None


def load_coverage(fits_path: str | Path, *, step: int = 1) -> np.ndarray | None:
    """Load a stack's per-pixel coverage map as a 2D float32 array, or ``None``
    when no coverage sibling exists (a single-field image the leveling op can't and
    shouldn't act on).

    ``step`` strides the map the same way :func:`build_proxy` decimates the image,
    so the returned coverage lines up pixel-for-pixel with a proxy built at that
    ``proxy_scale`` — essential for the live-preview coverage-leveling op to match
    the full-res export.
    """
    return _load_map(coverage_path_for(fits_path), step=step)


def load_frame_coverage(fits_path: str | Path, *, step: int = 1) -> np.ndarray | None:
    """Load a stack's honest per-pixel **frame count**, or ``None`` if absent.

    This is what the sky-leveling pass should bin a mosaic's panels by: how many
    subs cover a pixel, not the sum of their weights (which splits one real panel
    across several bins once quality weighting is on). ``None`` — every run
    recorded before the sibling existed, and any path that couldn't supply a
    count — means "fall back to the weighted map", i.e. the behaviour those runs
    have always had.
    """
    return _load_map(frame_coverage_path_for(fits_path), step=step)


def clear_proxy(project_dir: Path, run_id: int) -> None:
    """Remove a run's cached proxy (call when the run is deleted)."""
    for p in _proxy_paths(project_dir, run_id):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
