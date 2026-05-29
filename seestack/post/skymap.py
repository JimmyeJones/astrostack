"""
All-sky Aitoff map rendering for a Library campaign.

Given a Library, build a single image showing the whole celestial sphere
in Aitoff projection, with:

  * A bright-star background (we ship a tiny catalog so this works offline;
    the GUI can swap in a fuller one if you have astroquery installed).
  * A coordinate grid (RA every 2 hours, Dec every 30°).
  * The Galactic equator overplotted as a faint curve, so the user can see
    where the Milky Way runs through their imaged targets.
  * Every target with a known RA/Dec drawn as a labelled dot, optionally
    with the latest preview image dropped on top of it at real angular size.

The rendered figure is a Matplotlib Figure object — the caller decides
whether to embed it in a Qt widget or save to disk. ``render_to_png`` is a
helper for the latter.

The all-sky view is decorative *and* functional. It immediately answers
"where in the sky have I been imaging?" and "what's left to fill in?" —
the questions you actually have during a multi-week campaign.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from seestack.io.library import Library, TargetEntry

log = logging.getLogger(__name__)


# Small built-in bright-star list. (HR name, RA deg, Dec deg, V mag).
# Carefully chosen so the resulting plot looks like a sky even with no
# external star catalog. About 60 of the brightest stars + a handful of
# distinctive deep-sky markers — enough to orient by, not enough to be
# noisy on a small figure.
_BRIGHT_STARS: list[tuple[str, float, float, float]] = [
    ("Sirius", 101.287, -16.716, -1.46),
    ("Canopus", 95.988, -52.696, -0.74),
    ("Arcturus", 213.915, 19.182, -0.05),
    ("Vega", 279.234, 38.784, 0.03),
    ("Capella", 79.172, 45.998, 0.08),
    ("Rigel", 78.634, -8.202, 0.13),
    ("Procyon", 114.826, 5.225, 0.34),
    ("Achernar", 24.429, -57.237, 0.45),
    ("Betelgeuse", 88.793, 7.407, 0.50),
    ("Hadar", 210.956, -60.373, 0.61),
    ("Altair", 297.696, 8.868, 0.77),
    ("Aldebaran", 68.980, 16.509, 0.85),
    ("Antares", 247.352, -26.432, 1.09),
    ("Spica", 201.298, -11.161, 1.04),
    ("Pollux", 116.329, 28.026, 1.14),
    ("Fomalhaut", 344.413, -29.622, 1.16),
    ("Deneb", 310.358, 45.280, 1.25),
    ("Mimosa", 191.930, -59.689, 1.25),
    ("Regulus", 152.093, 11.967, 1.36),
    ("Adhara", 104.656, -28.972, 1.50),
    ("Castor", 113.650, 31.888, 1.58),
    ("Gacrux", 187.791, -57.113, 1.59),
    ("Shaula", 263.402, -37.104, 1.62),
    ("Bellatrix", 81.283, 6.350, 1.64),
    ("Elnath", 81.573, 28.608, 1.65),
    ("Miaplacidus", 138.300, -69.717, 1.67),
    ("Alnilam", 84.053, -1.202, 1.69),
    ("Alnair", 332.058, -46.961, 1.74),
    ("Alnitak", 85.190, -1.943, 1.74),
    ("Alioth", 193.507, 55.960, 1.76),
    ("Dubhe", 165.932, 61.751, 1.81),
    ("Mirfak", 51.081, 49.861, 1.82),
    ("Wezen", 107.098, -26.393, 1.83),
    ("Kaus Australis", 276.043, -34.385, 1.85),
    ("Avior", 125.628, -59.510, 1.86),
    ("Alkaid", 206.885, 49.313, 1.86),
    ("Sargas", 264.330, -42.998, 1.87),
    ("Menkalinan", 89.882, 44.948, 1.90),
    ("Atria", 252.166, -69.028, 1.91),
    ("Alhena", 99.428, 16.399, 1.93),
    ("Peacock", 306.412, -56.735, 1.94),
    ("Polaris", 37.954, 89.264, 1.98),
    ("Mirzam", 95.675, -17.956, 1.98),
    ("Alphard", 141.897, -8.659, 1.99),
    ("Algieba", 154.993, 19.842, 2.01),
    ("Hamal", 31.793, 23.462, 2.00),
    ("Diphda", 10.897, -17.987, 2.04),
    ("Mizar", 200.981, 54.926, 2.05),
    ("Nunki", 283.816, -26.297, 2.05),
    ("Menkent", 211.671, -36.370, 2.06),
    ("Mirach", 17.433, 35.621, 2.05),
    ("Alpheratz", 2.097, 29.090, 2.06),
    ("Rasalhague", 263.734, 12.560, 2.08),
    ("Kochab", 222.676, 74.156, 2.08),
    ("Saiph", 86.939, -9.670, 2.09),
    ("Denebola", 177.265, 14.572, 2.14),
    ("Algol", 47.042, 40.956, 2.12),
    ("Tiaki", 340.667, -46.885, 2.07),
    ("Almach", 30.975, 42.330, 2.10),
    ("Caph", 2.295, 59.150, 2.27),
]


def bright_star_catalog() -> list[dict[str, float | str]]:
    """The built-in bright-star list as plain dicts (name, ra_deg, dec_deg, mag).

    Used by the all-sky map and by the web app's interactive sky viewer so both
    share a single offline catalog (no external survey/catalog server needed).
    """
    return [
        {"name": name, "ra_deg": ra, "dec_deg": dec, "mag": mag}
        for (name, ra, dec, mag) in _BRIGHT_STARS
    ]


@dataclass
class SkyMapOptions:
    """Knobs for ``render_skymap``."""

    figure_size: tuple[float, float] = (12.0, 6.5)
    dpi: int = 110
    title: str | None = "Seestack campaign"
    show_galactic_plane: bool = True
    show_bright_stars: bool = True
    show_grid: bool = True
    thumbnail_size_deg: float = 5.0
    """Half-side of the thumbnail square placed at each target, in degrees.
    Set to 0 to disable thumbnails and only draw dots/labels."""
    label_targets: bool = True
    style: str = "dark"   # 'dark' or 'light'


def render_skymap(library: Library, options: SkyMapOptions | None = None):
    """
    Build a matplotlib ``Figure`` showing the library's targets on an
    Aitoff projection. The figure is **not** shown or saved — the caller
    chooses (``fig.savefig(...)`` or embed in Qt).
    """
    if options is None:
        options = SkyMapOptions()

    # Import matplotlib lazily so this module is importable without it.
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    targets = [t for t in library.list_targets()
               if t.ra_deg is not None and t.dec_deg is not None]

    fg, bg, accent, faint = _style_colors(options.style)
    fig = plt.figure(figsize=options.figure_size, dpi=options.dpi,
                     facecolor=bg)
    ax = fig.add_subplot(111, projection="aitoff")
    ax.set_facecolor(bg)

    if options.show_grid:
        ax.grid(True, color=faint, alpha=0.6, linewidth=0.5)

    if options.show_bright_stars:
        _plot_bright_stars(ax, color=fg)
    if options.show_galactic_plane:
        _plot_galactic_plane(ax, color=accent)

    _plot_targets(ax, library, targets, options=options, fg=fg, accent=accent)

    # Astronomers want RA increasing to the *left*. matplotlib's geographic
    # projections forbid set_xlim / invert_xaxis, so the flip is baked into
    # _ra_to_aitoff_rad instead (it returns the negated longitude). Here we
    # only need to label the ticks: a tick drawn at screen-x ``xt`` radians
    # corresponds to RA = -xt.
    tick_deg = np.arange(-150, 151, 30)
    tick_positions = np.deg2rad(tick_deg)
    tick_labels = [f"{((-d) % 360) / 15:.0f}h" for d in tick_deg]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, color=fg, fontsize=8)
    ax.tick_params(axis="y", colors=fg, labelsize=8)

    if options.title:
        stats = library.campaign_stats()
        subtitle = (
            f"{stats['n_targets']} targets · "
            f"{stats['n_frames_accepted']} accepted frames · "
            f"{_format_duration(stats['total_exposure_s'])}"
        )
        fig.suptitle(options.title, color=fg, fontsize=14)
        ax.set_title(subtitle, color=fg, fontsize=9, pad=18)

    fig.tight_layout()
    return fig


def render_to_png(library: Library, path: str | Path,
                   options: SkyMapOptions | None = None) -> Path:
    """Render and save to PNG. Returns the path on success."""
    import matplotlib.pyplot as plt

    fig = render_skymap(library, options)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=fig.dpi, facecolor=fig.get_facecolor(),
                bbox_inches="tight")
    plt.close(fig)
    return path


# ---- internals --------------------------------------------------------

def _style_colors(style: str) -> tuple[str, str, str, str]:
    """(foreground, background, accent, faint-grid) for the chosen style."""
    if style == "light":
        return "#202024", "#fdfdff", "#a04000", "#888888"
    # dark (default)
    return "#e6e6e6", "#0a0e1a", "#ff9a44", "#3a3f55"


def _ra_to_aitoff_rad(ra_deg: float) -> float:
    """
    Convert an RA in degrees to the Aitoff projection's x coordinate
    (radians, -pi..+pi).

    The value is **negated** so that RA increases to the left — the
    conventional sky-map orientation. matplotlib's geographic projections
    don't allow flipping the axis via set_xlim, so the flip lives here:
    every caller that places something at an RA gets the mirrored
    coordinate for free.
    """
    ra = ra_deg
    while ra > 180.0:
        ra -= 360.0
    while ra < -180.0:
        ra += 360.0
    return -math.radians(ra)


def _plot_bright_stars(ax, *, color: str) -> None:
    """Scatter the built-in bright-star list at sizes scaled by magnitude."""
    xs = np.array([_ra_to_aitoff_rad(r) for _, r, _, _ in _BRIGHT_STARS])
    ys = np.array([math.radians(d) for _, _, d, _ in _BRIGHT_STARS])
    mags = np.array([m for _, _, _, m in _BRIGHT_STARS], dtype=np.float32)
    # Magnitude → marker size: brighter = bigger. Clamp so nothing vanishes.
    sizes = np.clip(4 + (2.2 - mags) * 14, 4, 70)
    ax.scatter(xs, ys, s=sizes, c=color, alpha=0.9, edgecolors="none",
               zorder=2, marker=".")


def _plot_galactic_plane(ax, *, color: str) -> None:
    """Draw the Galactic equator as a faint curve."""
    # Galactic-equator (l = 0..360, b = 0) sampled in equatorial coords.
    # We compute it lazily from astropy if available; otherwise use a
    # pre-baked approximation that's good enough for an orientation cue.
    try:
        from astropy.coordinates import Galactic, SkyCoord
        import astropy.units as u
        l = np.linspace(0, 360, 720) * u.deg
        b = np.zeros_like(l.value) * u.deg
        eq = SkyCoord(l=l, b=b, frame=Galactic).icrs
        ra = eq.ra.degree
        dec = eq.dec.degree
    except Exception:  # noqa: BLE001
        # Approximation: a sinusoidal great-circle on the celestial sphere
        # tilted ~62.9° relative to the equator and passing through (266°,
        # -29°). Drawn dashed so the user knows it's approximate.
        l = np.linspace(0, 360, 720)
        ra = (l - 96.337) % 360.0
        dec = 62.872 * np.sin(np.radians(l))
        # Connect across the RA wrap for matplotlib by inserting NaNs.
    # Convert to aitoff coords, splitting at the RA wrap so we don't draw
    # a long horizontal line across the projection.
    x = np.array([_ra_to_aitoff_rad(r) for r in ra])
    y = np.radians(dec)
    # Insert NaNs where x jumps by more than pi (i.e. wraps).
    dx = np.abs(np.diff(x))
    breaks = np.where(dx > math.pi)[0]
    for b in reversed(breaks):
        x = np.insert(x, b + 1, np.nan)
        y = np.insert(y, b + 1, np.nan)
    ax.plot(x, y, color=color, linewidth=0.9, alpha=0.55, zorder=1,
            linestyle="--")


def _plot_targets(ax, library: Library, targets: list[TargetEntry], *,
                   options: SkyMapOptions, fg: str, accent: str) -> None:
    """Drop each target on the map (preview thumb if available, else dot)."""
    for t in targets:
        ra, dec = float(t.ra_deg), float(t.dec_deg)  # type: ignore[arg-type]
        x = _ra_to_aitoff_rad(ra)
        y = math.radians(dec)

        # Try to drop the latest stack preview as a small image on the map.
        drew_thumb = False
        if (options.thumbnail_size_deg > 0
                and t.last_stack_preview
                and Path(t.last_stack_preview).exists()):
            try:
                _draw_thumbnail_on_aitoff(
                    ax, t.last_stack_preview, ra, dec,
                    half_size_deg=options.thumbnail_size_deg,
                )
                drew_thumb = True
            except Exception as exc:  # noqa: BLE001
                log.debug("could not render thumb for %s: %s", t.name, exc)

        # Always also draw a marker so empty-RA targets are still visible.
        ax.plot(x, y, marker="o", color=accent if not drew_thumb else fg,
                markersize=6 if not drew_thumb else 3,
                markeredgecolor=accent if drew_thumb else "none",
                markerfacecolor="none" if drew_thumb else accent,
                zorder=4)

        if options.label_targets:
            ax.annotate(
                t.name, xy=(x, y),
                xytext=(6, 6), textcoords="offset points",
                color=fg, fontsize=8, zorder=5,
            )


def _draw_thumbnail_on_aitoff(ax, image_path: str, ra_deg: float, dec_deg: float,
                              *, half_size_deg: float) -> None:
    """Place a small image centred at (RA, Dec) on the aitoff axis."""
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    from PIL import Image

    img = Image.open(image_path)
    img.thumbnail((64, 64))
    arr = np.asarray(img)
    # `zoom` controls pixel scale; tune so the thumb is roughly the
    # requested angular size on the projection. Aitoff is non-linear, so
    # this is approximate near the poles — exact placement isn't critical.
    zoom = max(0.20, min(0.8, half_size_deg / 6.0))
    im = OffsetImage(arr, zoom=zoom)
    ab = AnnotationBbox(
        im, (_ra_to_aitoff_rad(ra_deg), math.radians(dec_deg)),
        frameon=False, pad=0.0, zorder=3,
    )
    ax.add_artist(ab)


def _format_duration(seconds: float) -> str:
    """Friendly duration string. e.g. 12345 -> '3h 25m 45s'."""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"
