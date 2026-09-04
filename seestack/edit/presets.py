"""Built-in object-type presets + the one-click Auto-process recipe.

A preset is a recipe fragment (ordered ops). Applying a preset replaces the working
recipe. User-saved presets live in library meta; these built-ins ship with the code.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from seestack.edit.recipe import OpInstance, Recipe, validate_ops

# Gaussian FWHM → σ, and the sharpen op's radius bounds/step (kept in step with
# the EditParam in seestack/edit/ops/detail.py). A good unsharp-mask radius is on
# the scale of the star's own blur (its Gaussian σ), so the median star FWHM is
# the natural data-driven default — the same conversion the editor's
# sharpen-from-stars button uses.
_FWHM_TO_SIGMA = 1.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))  # ≈ 0.4247
_SHARPEN_RADIUS_MIN = 0.5
_SHARPEN_RADIUS_MAX = 10.0
_SHARPEN_RADIUS_STEP = 0.5


def _sharpen_radius_from_fwhm(median_fwhm: float | None) -> float:
    """Map a target's median star FWHM to an unsharp-mask radius (≈ the star's
    Gaussian σ), clamped to the op's slider range and rounded to its step.
    Falls back to the op's 2.0 default when no FWHM is available."""
    if median_fwhm is None or median_fwhm <= 0:
        return 2.0
    raw = median_fwhm * _FWHM_TO_SIGMA
    radius = max(_SHARPEN_RADIUS_MIN, min(_SHARPEN_RADIUS_MAX, raw))
    return round(round(radius / _SHARPEN_RADIUS_STEP) * _SHARPEN_RADIUS_STEP, 2)


def _ops(*pairs: tuple[str, dict]) -> list[OpInstance]:
    return validate_ops([OpInstance(id=i, params=p) for i, p in pairs])


# Each: id -> {label, group, ops}
BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "galaxy_broadband": {
        "label": "Galaxy (broadband)", "group": "Built-in",
        "ops": _ops(
            ("background.final_gradient", {"mode": "per_channel"}),
            ("tone.color_calibrate", {"mode": "gray_star"}),
            ("tone.stretch", {"mode": "stf", "target_bg": 0.18}),
            ("tone.curves", {"points": [[0, 0], [0.25, 0.2], [0.75, 0.82], [1, 1]]}),
            ("tone.saturation", {"amount": 1.25}),
            ("detail.sharpen", {"amount": 0.6, "radius": 2.0}),
        ),
    },
    "nebula_broadband": {
        "label": "Nebula (broadband)", "group": "Built-in",
        "ops": _ops(
            ("background.final_gradient", {"mode": "luminance"}),
            ("tone.color_calibrate", {"mode": "gray_star"}),
            ("tone.stretch", {"mode": "stf", "target_bg": 0.22}),
            ("tone.scnr", {"amount": 0.8}),
            ("tone.saturation", {"amount": 1.35}),
        ),
    },
    "nebula_narrowband": {
        "label": "Nebula (narrowband)", "group": "Built-in",
        "ops": _ops(
            ("background.final_gradient", {"mode": "luminance"}),
            ("tone.stretch", {"mode": "stf", "target_bg": 0.25}),
            ("tone.scnr", {"amount": 0.6}),
            ("tone.curves", {"points": [[0, 0], [0.3, 0.28], [0.8, 0.86], [1, 1]]}),
            ("tone.saturation", {"amount": 1.15}),
        ),
    },
    "globular_cluster": {
        "label": "Star cluster", "group": "Built-in",
        "ops": _ops(
            ("background.subtract", {"mode": "per_channel"}),
            ("tone.color_calibrate", {"mode": "gray_star"}),
            ("tone.stretch", {"mode": "asinh", "stretch": 0.45, "black": 0.45}),
            ("stars.reduce", {"amount": 0.3, "size": 2}),
            ("tone.saturation", {"amount": 1.2}),
        ),
    },
}


def preset_recipe(preset_id: str) -> Recipe | None:
    p = BUILTIN_PRESETS.get(preset_id)
    if p is None:
        return None
    return Recipe(ops=[OpInstance(id=o.id, params=dict(o.params)) for o in p["ops"]])


#: The old ``sky_sigma`` was ``1.4826·MAD`` of the sky *levels* — i.e. the MAD of
#: the **lower half** of the sky's value distribution, which reads ``0.593·σ`` for
#: Gaussian noise rather than ``σ``. Every constant downstream of ``sky_sigma``
#: (``_NOISE_LO``/``_NOISE_HI``, the ``> 0.02`` "noisy" verdict, the ``× 6.0``
#: saturation term) was calibrated against that scale, so the local estimator that
#: replaced it is reported on the same scale via this factor. Pinned by
#: ``test_sky_sigma_matches_the_old_level_mad_on_pure_noise``: on structure-free
#: noise the two agree to within 2 % at every σ, so an ordinary single-field
#: stack's one-click Auto is unchanged.
_SKY_HALF_MAD_SCALE = 0.593


def analyze_proxy(rgb: np.ndarray) -> dict[str, Any]:
    """Cheap content analysis of a proxy used to tailor the auto recipe:
    sky level, sky-noise fraction, and a coarse 'noisy' verdict.

    The sky *level* is the robust median of the whole-image-normalized luminance.

    The sky *noise* is measured **locally**, from the MAD of adjacent-pixel
    differences (``seestack.edit.noise.estimate_noise_sigma``), not from the
    spread of the sky's levels. That distinction is the whole point: the spread of
    levels also counts every *large-scale* structure in the frame — a residual
    light-pollution gradient, and above all a **mosaic's per-panel level/colour
    offsets** — so a deep, genuinely clean mosaic used to read as one of the
    noisiest images the app had ever seen (measured: σ 0.030 vs 0.008 for the
    identical stack laid out as a single field), which drove ``auto_recipe`` to
    fire the wide-kernel ``detail.chroma_denoise`` at full strength and smear
    colour across the panel seams — the owner's "multicolour grid". Neighbouring
    pixels differ by *noise*, whatever slow structure the frame carries, so the
    local estimator is blind to gradients and seams while agreeing with the old
    one on structure-free noise. It is also the same estimator behind the
    editor's "From your image" denoise suggestion, so the two halves of the
    crossfade now measure the same thing.

    Stars and the target can't masquerade as noise either: the MAD is robust to
    the minority of large jumps at their edges.
    """
    from seestack.edit.noise import estimate_noise_sigma

    arr = np.asarray(rgb, dtype=np.float32)
    lum = arr[..., :3].mean(axis=2) if arr.ndim == 3 else arr
    finite = lum[np.isfinite(lum)]
    if finite.size < 16:
        return {"sky": 0.1, "sky_sigma": 0.0, "noisy": False}
    lo, hi = float(np.nanpercentile(finite, 0.5)), float(np.nanpercentile(finite, 99.5))
    if hi <= lo:
        return {"sky": 0.1, "sky_sigma": 0.0, "noisy": False}
    norm = np.clip((finite - lo) / (hi - lo), 0.0, 1.0)
    med = float(np.median(norm))
    local = estimate_noise_sigma(arr)
    # Unmeasurable (too few finite pixels, no dynamic range) reads as clean —
    # the same convention the rest of the auto chain uses for "can't tell".
    sky_sigma = float(_SKY_HALF_MAD_SCALE * local) if local is not None else 0.0
    return {"sky": med, "sky_sigma": sky_sigma, "noisy": sky_sigma > 0.02}


# The noisy↔clean crossfade band (in the normalized sky-σ units analyze_proxy
# reports, centred on its 0.02 "noisy" verdict). Below _NOISE_LO the stack is
# treated as clean (sharpen only); above _NOISE_HI as noisy (denoise only); in
# between it gets *both*, crossfading, so two near-identical stacks either side
# of the old hard threshold no longer produce visibly different one-click results.
_NOISE_LO = 0.012
_NOISE_HI = 0.028

# Ceiling on the *one-click* Auto denoise strength. At the top of the crossfade a
# thin (e.g. 12-sub) S30 stack measures σ high enough that both the crossfade
# weight and the measured-noise suggestion saturate, so Auto would emit wavelet
# denoise at ~1.0 — which zeroes the fine grain (a waxy, "plastic" sky) while
# leaving the low-frequency chroma blotch untouched (measured on a realistic
# 12-sub stack). Cap the automatic value so the crossfade can't reach that
# glass-smooth end; the editor still lets the user push denoise higher by hand.
_AUTO_DENOISE_MAX = 0.6

# Ceiling on the *one-click* Auto colour-blotch smoothing (``detail.chroma_denoise``).
# That op is the other half of the cap above: what the wavelet denoise leaves on a
# thin stack is a low-frequency *colour* drift, not fine grain, so Auto now averages
# the chroma instead of waxing the luminance. It rides the same measured-noise
# crossfade as denoise — a stack Auto reads as clean gets the op *not at all*, so a
# clean stack's one-click result is byte-for-byte what it was. Measured on a
# synthetic S30 sky carrying a 25 px-scale colour drift: at this ceiling it takes
# ~20 % off the sky's colour spread while a faint (0.6σ) extended nebula keeps ~95 %
# of its own colour, and the luminance is provably untouched (see the op).
_AUTO_CHROMA_MAX = 0.5


def _noise_fraction(sky_sigma: float) -> float:
    """Map the measured background σ to a 0..1 crossfade weight: 0 at/below the
    clean end (``_NOISE_LO``), 1 at/above the noisy end (``_NOISE_HI``), linear in
    between. Denoise fades *in* and sharpen fades *out* as this rises."""
    if _NOISE_HI <= _NOISE_LO:
        return 1.0 if sky_sigma > _NOISE_LO else 0.0
    return float(np.clip((sky_sigma - _NOISE_LO) / (_NOISE_HI - _NOISE_LO), 0.0, 1.0))


# --- coarse content classification → a starting-preset *suggestion* -----------
# This is a hint only: the editor surfaces it as a one-click "this looks like a
# star cluster — try the Star-cluster preset?" chip and never changes what the
# one-click Auto recipe emits. So a mis-classification costs a wrong *suggestion*
# (a click to dismiss), not a worse *image*, and the general Auto recipe stays the
# safe fallback. It is deliberately tuned to **stay quiet unless one archetype is
# clear**: an ambiguous or low-signal field returns ``preset_id=None`` (no chip).
#
# The three coarse classes map to the OSC-relevant broadband presets; the
# narrowband nebula preset is never suggested to a one-shot-colour user.
_CLASS_PRESET: dict[str, str] = {
    "cluster": "globular_cluster",
    "nebula": "nebula_broadband",
    "galaxy": "galaxy_broadband",
}
_CLASS_REASON: dict[str, str] = {
    "cluster": "mostly point-like stars with little diffuse nebulosity",
    "nebula": "large areas of diffuse, coloured emission",
    "galaxy": "a concentrated extended object on a mostly dark sky",
}


#: Side of the box the extended region's channels are averaged over before its
#: colour is measured. Colour in a nebula is a property of the *region* — it
#: varies over tens of pixels, not between neighbours — while shot noise is
#: independent per pixel, so averaging first is what separates the two. 7 px
#: matches the opening footprint that defined the region and cuts the noise term
#: ~7×, which is enough to put a colourless thin stack well under the nebula bar
#: without measurably moving a clean image's answer (see ``_extended_chroma``).
_CHROMA_SMOOTH_PX = 7

#: Side of the box the *luminance* is averaged over before any of the geometry
#: cues are measured. Same principle as ``_CHROMA_SMOOTH_PX``, applied to the
#: other half of ``classify_target``: structure is a property of a *region*
#: (nebulosity and a galaxy's disc vary over tens of pixels, a star over a few),
#: shot noise is not, so averaging first measures the geometry rather than the
#: grain. Without it every cue below moves with how deep the stack is — measured
#: on one unchanging synthetic galaxy at 4…800 subs, ``ext_frac`` ran
#: 0.0121 → 0.0254 (a **2.1× swing**) and duly walked a scene across the
#: ``≤ 0.05`` galaxy ceiling; with it the same sweep reads 0.0217 → 0.0255
#: (±8 %) and lands on the *deep* answer at every depth. 3 px is the smallest box
#: that gets there: it cuts the noise ~3× — enough that the ``6·sky_sigma`` term
#: of the threshold below falls under its own 0.06 floor on realistic data — while
#: staying far narrower than the 7 px opening footprint that separates stars from
#: diffuse structure, so a star is still a star. (5 px was measured too and is
#: worse: it smears a dense star field into fake "extended" signal.)
_GEOM_SMOOTH_PX = 3


def _extended_chroma(arr: np.ndarray, ext_sig: np.ndarray) -> float:
    """Median chroma ``(max−min)/mean`` of the extended-signal region.
    Scale-invariant (works on the linear proxy), so a coloured emission nebula
    reads high and a neutral galaxy reads low.

    **Measured on a locally averaged copy, and that is load-bearing.** Taken
    pointwise on the raw pixels this reads a stack's *noise* as colour: R, G and
    B are independent, so ``max−min`` over three noisy samples of one grey pixel
    is ~1.7σ whatever the pixel actually is. Measured across sub counts on one
    unchanging, **completely colourless** synthetic field, the pointwise number
    ran 0.118 at 4 subs → 0.010 at 800 — i.e. a thin stack of a grey object read
    nearly twice the ``chroma >= 0.06`` nebula bar purely from grain, and
    ``classify_target`` duly called it a nebula until it was stacked deep enough.
    That is the "statistic that changes meaning with how much data went in" class
    (docs/IMPROVEMENTS.md), and the depth-invariant fix is to measure the thing
    the docstring always claimed — the colour of the *region* — rather than the
    colour of single pixels.

    The average is masked to the region itself (``uniform_filter`` over
    ``channel × mask`` divided by the same filter over ``mask``), so the sky and
    the star wings just outside it can't bleed a false cast in. ``0.0`` when the
    region is too small to say anything.
    """
    from scipy.ndimage import uniform_filter

    if int(ext_sig.sum()) < 50:
        return 0.0
    px = np.clip(np.asarray(arr[..., :3], dtype=np.float32), 0.0, None)
    mask = ext_sig.astype(np.float32)
    weight = uniform_filter(mask, size=_CHROMA_SMOOTH_PX, mode="constant")
    smooth = np.empty_like(px)
    for c in range(3):
        smooth[..., c] = uniform_filter(
            np.where(ext_sig, px[..., c], 0.0).astype(np.float32),
            size=_CHROMA_SMOOTH_PX, mode="constant")
    # ``weight`` is ≥ 1/size² wherever the mask is set, so this never divides by
    # zero on a pixel we go on to read.
    smooth /= np.maximum(weight, 1e-6)[..., None]
    sel = smooth[ext_sig]
    mx = sel.max(axis=1)
    mn = sel.min(axis=1)
    mean = sel.mean(axis=1)
    chroma = (mx - mn) / (mean + 1e-6)
    return float(np.median(chroma))


def classify_target(rgb: np.ndarray | None) -> dict[str, Any]:
    """Coarsely classify a proxy as a *star cluster*, *nebula*, or *galaxy* and
    suggest the matching built-in preset — or decline (``preset_id=None``) when the
    content isn't clearly one archetype. A pure hint used by the editor's
    preset-suggestion chip; it never changes the Auto recipe (§ AGENTS.md autonomy).

    The cues are cheap and geometry-first (colour only refines the nebula/galaxy
    margin, since the proxy is linear and OSC colour is uncalibrated here). All
    of them are measured on a **locally averaged** copy of the luminance
    (``_GEOM_SMOOTH_PX``) so that one unchanging sky gives one answer however
    many subs went into it — see that constant for the two mechanisms that made
    them depth-dependent before:

    * ``star_share`` — how much of the above-sky *signal* is compact point sources
      (from the same white-top-hat ``star_mask`` the editor uses). A field that is
      almost all stars with negligible diffuse structure is a **cluster**.
    * ``ext_frac`` — the fraction of the *frame* covered by extended (non-star)
      signal. A large diffuse spread is a **nebula**; a small concentrated object
      on a mostly dark sky is a **galaxy**.
    * ``chroma`` — median colour of the extended region. Required for the nebula
      call unless the diffuse spread is unmistakably large, so a big *neutral*
      galaxy (e.g. M31) isn't confidently mis-labelled a nebula — it falls through
      to "unsure" (no chip) instead.

    Returns ``{"cls", "preset_id", "label", "reason", "confidence", "cues"}``. When
    nothing is clear, ``cls``/``preset_id`` are ``None`` and no chip is shown.
    """
    none = {"cls": None, "preset_id": None, "label": None, "reason": None,
            "confidence": 0.0, "cues": {}}
    if rgb is None:
        return none
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return none  # need colour to tell nebula from galaxy
    lum = arr[..., :3].mean(axis=2)
    cover = np.isfinite(lum)
    n_cov = int(cover.sum())
    if n_cov < 1024:
        return none  # too little covered area to classify meaningfully

    lum_c = lum[cover]
    lo, hi = float(np.percentile(lum_c, 0.5)), float(np.percentile(lum_c, 99.5))
    if hi <= lo:
        return none
    norm = np.clip((lum - lo) / (hi - lo), 0.0, 1.0)

    # Every geometry cue below is measured on a locally averaged copy, and that
    # is load-bearing (see _GEOM_SMOOTH_PX): taken pointwise they are all
    # monotone functions of how deep the stack is, through two mechanisms that
    # both vanish once the grain is averaged out — the ``6·sky_sigma`` term of
    # the threshold, which on a thin stack sits far above its own 0.06 floor and
    # hides faint structure; and the opening's erosion, whose min-over-49-samples
    # is biased ~2.5σ low, so on a thin stack it depresses the *diffuse* image
    # and the object's own skirt gets counted as point sources.
    from scipy.ndimage import grey_opening, uniform_filter

    # Fill the uncovered gaps with a provisional sky before averaging so the
    # canvas edge can't drag the measurement down (the opening already did this).
    filled = np.where(cover, norm, float(np.median(norm[cover]))).astype(np.float32, copy=False)
    meas = uniform_filter(filled, size=_GEOM_SMOOTH_PX, mode="nearest")

    meas_c = meas[cover]
    sky = float(np.median(meas_c))
    sky_pop = meas_c[meas_c <= sky]
    sky_sigma = (float(1.4826 * np.median(np.abs(sky_pop - np.median(sky_pop))))
                 if sky_pop.size else 0.0)

    # "Signal" = clearly above the sky floor (robust, noise-aware threshold).
    thr = sky + max(0.06, 6.0 * sky_sigma)
    signal = (meas > thr) & cover
    n_sig = int(signal.sum())
    sig_frac = n_sig / n_cov
    if sig_frac < 0.0015:
        return none  # essentially blank — no structured target to classify

    # Separate *diffuse* structure from *compact* point sources with a grey-scale
    # morphological opening: a footprint a few px wide erases stars (and their
    # Gaussian wings) but leaves anything larger — nebulosity, a galaxy — intact.
    # So the opened image, thresholded above sky, is the extended signal; whatever
    # is bright in the raw image but *not* in the opened image is a point source.
    opened = grey_opening(meas, footprint=np.ones((7, 7), dtype=bool))
    ext_sig = (opened > thr) & cover
    point_sig = signal & ~ext_sig
    n_pt = int(point_sig.sum())
    n_ext = int(ext_sig.sum())
    pt_frac = n_pt / n_cov
    ext_frac = n_ext / n_cov
    star_share = n_pt / max(n_sig, 1)
    chroma = _extended_chroma(arr, ext_sig) if n_ext else 0.0

    cues = {
        "sig_frac": round(sig_frac, 4), "ext_frac": round(ext_frac, 4),
        "pt_frac": round(pt_frac, 4), "star_share": round(star_share, 3),
        "chroma": round(chroma, 3),
    }

    cls: str | None = None
    confidence = 0.0
    if star_share >= 0.75 and ext_frac <= 0.012 and pt_frac >= 0.0025:
        # Signal is overwhelmingly point sources with negligible diffuse structure.
        cls, confidence = "cluster", min(1.0, star_share)
    elif star_share <= 0.6 and ext_frac >= 0.06 and chroma >= 0.06:
        # Large diffuse *coloured* emission → nebula. The colour floor keeps a big
        # neutral galaxy (e.g. M31) from a confident nebula mis-label — it falls
        # through to "unsure" (no chip) instead.
        cls, confidence = "nebula", min(1.0, ext_frac / 0.06)
    elif (star_share <= 0.65 and 0.004 <= ext_frac <= 0.05
          and sig_frac <= 0.10 and chroma < 0.08):
        # A small, concentrated, neutral extended object on a dark sky → galaxy.
        cls, confidence = "galaxy", min(1.0, 0.05 / max(ext_frac, 1e-3))

    if cls is None:
        return {**none, "cues": cues}
    preset_id = _CLASS_PRESET[cls]
    return {
        "cls": cls,
        "preset_id": preset_id,
        "label": BUILTIN_PRESETS[preset_id]["label"],
        "reason": _CLASS_REASON[cls],
        "confidence": round(float(confidence), 3),
        "cues": cues,
    }


def auto_recipe(rgb: np.ndarray | None = None,
                median_fwhm: float | None = None,
                is_mosaic: bool = False,
                trim_crop: tuple[float, float, float, float] | None = None,
                prefs: dict[str, Any] | None = None,
                auto_crop: bool = True) -> Recipe:
    """One-click auto-process built from the image, not hardcoded.

    Always: background/gradient removal → photometric colour balance → a proper
    per-channel STF stretch (``tone.stretch`` mode ``stf``, the same algorithm as
    the proven ``autostretch``) → a gentle green-cast removal (SCNR) — the single
    most common OSC defect, which every built-in nebula preset also fixes. Then,
    only when warranted by the analysis: denoise (on linear data, before the
    stretch) at a *data-driven* strength scaled to the measured background noise,
    and a gentle sharpen sized to the target's *own* stars (median FWHM → radius,
    the same conversion the editor's sharpen-from-stars button uses). Rather than a
    hard noisy/clean switch (which made two near-identical stacks either side of the
    threshold produce visibly different results), the two *crossfade* across a band
    around the old threshold: a clean stack gets sharpen only, a very noisy one
    denoise only, and a mildly-noisy one a light touch of *both* — the denoise
    fading in and the sharpen fading out as the measured σ rises (see
    ``_noise_fraction``). Saturation lifts colour a touch at the end (after the
    green cast is gone, so it doesn't amplify it) — *scaled to the measured noise*
    so a noisy stack gets a gentler boost (less amplified chroma speckle) and a
    clean one the full lift. Finally a gentle **contrast curve** (``tone.curves``
    with ``auto=True``) is appended: like the built-in galaxy/nebula presets — but
    unlike the previously-flat general Auto recipe — it shapes the midtones, deriving
    a *data-driven* lift from its own stretched input at apply time (sky floor and
    highlight shoulder pinned on the identity, so it only gently lifts faint midtone
    structure without brightening the sky or blowing star cores).

    When ``is_mosaic`` is set (the stacker's authoritative union-canvas verdict,
    resolved by the caller), a ``background.level_coverage`` pass is prepended (on
    linear data, before the gradient fit) so uneven-overlap panel steps are
    equalised before anything else — the Seestar mosaic case, fixed without the
    user discovering the op. On a single-field stack it's skipped entirely, where
    it would be a no-op anyway.

    When ``trim_crop`` (fractional ``(x0, y0, x1, y1)`` bounds) is supplied — the
    largest well-covered rectangle of a mosaic's coverage map, from the same
    ``largest_covered_rect`` machinery the "Trim border" button uses — a
    ``geometry.crop`` to that rectangle is appended at the *end*, so the one-click
    result is cleanly framed instead of leaving the ragged, noisy low-coverage
    fringe of the union canvas. The caller passes it only for a mosaic where the
    trim is meaningful (``largest_covered_rect`` returns ``None`` on a full-frame
    result), so a single-field stack is never cropped. The crop runs last (after
    all tone/detail ops), which is safe and keeps the coverage-leveling op — which
    needs the native-geometry coverage map — operating on the uncropped frame.

    ``auto_crop`` (default ``True`` — today's behaviour) is the owner's preference
    for that last step: some would rather keep the *whole* frame, ragged edges and
    all, than have Auto quietly reframe their picture. With it off the
    ``geometry.crop`` op is simply not emitted and nothing else about the recipe
    changes ("Trim border" is still there to crop by hand). The caller still
    *measures* the trim rectangle either way, so ``analyze_auto_inputs`` can report
    what Auto would have trimmed.
    """
    target_bg = 0.20
    saturation = 1.2          # neutral fallback when the image can't be measured
    # Crossfade weights: an unmeasurable image is treated as clean (sharpen full,
    # no denoise) — matching the old boolean fallback.
    denoise_strength = 0.0
    chroma_strength = 0.0
    sharpen_amount = 0.5
    if rgb is not None:
        a = analyze_proxy(rgb)
        sky_sigma = float(a["sky_sigma"])
        noise_frac = _noise_fraction(sky_sigma)
        # Darker sky → lift a little more (higher target grey), brighter → less.
        target_bg = float(np.clip(0.24 - a["sky"] * 0.4, 0.14, 0.24))
        # Chroma noise scales with the saturation boost, so ease off on a noisy
        # stack (where a strong boost just amplifies colour speckle) and give a
        # clean one the full lift — rather than the same fixed 1.2 for both.
        saturation = float(np.clip(1.25 - sky_sigma * 6.0, 1.05, 1.25))
        # Sharpen fades out as noise rises; denoise fades in. So a clean stack
        # (noise_frac 0) gets full sharpen and no denoise, a very noisy one
        # (noise_frac 1) full denoise and no sharpen — matching the old ends — and
        # a mildly-noisy one a light touch of both instead of an abrupt switch.
        sharpen_amount = round(0.5 * (1.0 - noise_frac), 3)
        if noise_frac > 0.0:
            # Match the denoise strength to the actual measured noise (the same
            # estimator behind the editor's "From your image" one-click), scaled by
            # the crossfade weight so it eases in across the band.
            from seestack.edit.noise import suggest_denoise_strength

            _, suggested = suggest_denoise_strength(rgb)
            base = suggested if suggested is not None else 0.5
            denoise_strength = round(base * noise_frac, 3)
            # The *colour* half of the same problem, on the same crossfade: what a
            # noisy stack's sky shows after the wavelet pass is a low-frequency
            # green/magenta drift the wavelet can't reach (it only shrinks fine
            # scales). Ease it in with the noise, capped at _AUTO_CHROMA_MAX. A
            # clean stack (noise_frac == 0) never gets the op at all.
            chroma_strength = round(_AUTO_CHROMA_MAX * noise_frac, 3)

    # SCNR before the saturation boost caps the green channel to the R/B neutral
    # so the boost lifts real colour, not the residual OSC green cast. Gentle
    # (0.7) and monotone — it can only *reduce* excess green, never invent colour.
    scnr_amount = 0.7
    # "Hold back highlights" starts *off*: the stretch's existing shoulder already
    # rescues an ordinary core, and deciding from the image whether a core is
    # clipping needs real-data threshold tuning (filed in docs/IMPROVEMENTS.md).
    # It moves only when the owner says the core looks blown out.
    highlight_protect = 0.0
    # Adaptive Auto: shift these data-driven values toward the owner's stored
    # taste, each re-clamped to a safe range. An empty/absent profile returns them
    # unchanged, so a never-configured library's Auto is byte-for-byte identical.
    if prefs is not None:
        from seestack.edit import auto_prefs

        # Per-object-type taste: classify this image (galaxy/nebula/cluster) so a
        # bias learned on one archetype only shifts that archetype. An unclassified
        # image (cls None) falls back to the global taste — see auto_prefs.
        object_type = classify_target(rgb).get("cls") if rgb is not None else None
        adj = auto_prefs.apply_profile(
            prefs,
            target_bg=target_bg,
            saturation=saturation,
            sharpen_amount=sharpen_amount,
            denoise_strength=denoise_strength,
            scnr_amount=scnr_amount,
            highlight_protect=highlight_protect,
            object_type=object_type,
        )
        target_bg = adj["target_bg"]
        saturation = adj["saturation"]
        sharpen_amount = adj["sharpen_amount"]
        denoise_strength = adj["denoise_strength"]
        scnr_amount = adj["scnr_amount"]
        highlight_protect = adj["highlight_protect"]

    # Never let the automatic denoise reach the glass-smooth end of the wavelet
    # op (see _AUTO_DENOISE_MAX). Applied after the taste profile so a learned
    # "too noisy" bias can't push the one-click result back to a waxy sky either.
    denoise_strength = min(denoise_strength, _AUTO_DENOISE_MAX)

    ops: list[tuple[str, dict]] = []
    if is_mosaic:
        # Equalise per-panel sky steps before the gradient fit — the coverage map
        # is loaded into the render context downstream, so on a single-field
        # export (no coverage) this op is a harmless no-op even if it slips in.
        ops.append(("background.level_coverage", {}))
    ops += [
        ("background.final_gradient", {"mode": "luminance"}),
        ("tone.color_calibrate", {"mode": "gray_star"}),
    ]
    # Denoise (linear, before the stretch) once the crossfade calls for a
    # meaningful amount; skip a sub-step sliver so a near-clean stack carries no
    # no-op op.
    if denoise_strength >= 0.05:
        ops.append(("detail.denoise", {"method": "wavelet", "strength": denoise_strength}))
    stretch_params: dict = {"mode": "stf", "target_bg": target_bg}
    if highlight_protect >= 0.01:
        # Only carried when a taste bias actually asked for it, so the default
        # recipe's op list — which saved recipes and tests compare against — is
        # unchanged rather than gaining a param pinned at its own default.
        stretch_params["highlights"] = round(highlight_protect, 3)
    ops.append(("tone.stretch", stretch_params))
    if scnr_amount >= 0.05:  # a bias can dial the green removal down to nothing
        ops.append(("tone.scnr", {"amount": round(scnr_amount, 3)}))
    ops.append(("tone.saturation", {"amount": round(saturation, 3)}))
    # A gentle contrast curve — the built-in galaxy/nebula presets ship an S-curve,
    # but the general Auto recipe was the flat exception (denoise → stretch → SCNR →
    # saturation → sharpen, no contrast shaping). `auto=True` + the identity default
    # points make tone.curves derive a *data-driven* midtone lift from its own
    # (stretched) input at apply time — so it adapts to the actual stack rather than
    # a fixed shape — and fall back to a *sky-anchored* gentle S-curve when the data
    # offers no useful lift. Both branches keep the background and the highlight
    # shoulder on the identity (no sky brightening, no blown star cores), so it only
    # ever *gently* lifts faint structure above the noise. Scout-vetted on realistic
    # dim OSC stacks (2026-07-04); the "no sky brightening" half was only true of the
    # design, not the code, until v0.326.1 (see `seestack/edit/curve.py`).
    ops.append(("tone.curves", {"auto": True}))
    if sharpen_amount >= 0.05:  # sharpening clean data helps; noisy data hurts
        radius = _sharpen_radius_from_fwhm(median_fwhm)
        ops.append(("detail.sharpen", {"amount": sharpen_amount, "radius": radius}))
    # Colour-blotch smoothing goes *last* among the tone/detail ops, deliberately.
    # It only ever rewrites colour (the luminance it returns is bit-identical to
    # its input), so running it after the saturation boost and the auto-contrast
    # curve means (a) it flattens the patchiness those two have already amplified
    # rather than a version of it that's about to be scaled up, and (b) it cannot
    # perturb the *data-driven* anchors ``tone.curves``/``detail.sharpen`` derive
    # at apply time — so every other part of Auto behaves exactly as it did.
    if chroma_strength >= 0.05:
        ops.append(("detail.chroma_denoise", {"strength": chroma_strength}))
    # Trim the ragged, low-coverage mosaic border last (after tone/detail ops), so
    # the auto result is cleanly framed. Only supplied when the trim is meaningful,
    # and only when the owner wants Auto to reframe at all (`auto_crop`).
    if trim_crop is not None and auto_crop:
        x0, y0, x1, y1 = trim_crop
        ops.append(("geometry.crop", {"x0": x0, "y0": y0, "x1": x1, "y1": y1}))
    return Recipe(ops=_ops(*ops))


def analyze_auto_inputs(
    rgb: np.ndarray | None = None,
    median_fwhm: float | None = None,
    is_mosaic: bool = False,
    trim_crop: tuple[float, float, float, float] | None = None,
    auto_crop: bool = True,
) -> dict[str, Any]:
    """The *measured cues* that drove the Auto recipe — the causal inputs behind
    each op, surfaced so the user sees Auto tuned itself to *their* data (not a
    fixed op list). Pure; reuses the exact same analysis ``auto_recipe`` consumes
    (``analyze_proxy`` + ``_noise_fraction`` + the FWHM→radius map + the trim
    rect), so the numbers reported here match the recipe it actually built.

    Every field is optional/nullable so it degrades gracefully: ``sky``/noise are
    ``None`` when the proxy can't be measured, ``median_fwhm`` is ``None`` when no
    solved stars gave a FWHM, and ``trim_fraction`` is ``None`` on a single-field
    (non-trimmed) stack. Values are rounded to the precision a UI would show.

    ``trim_fraction`` reports what the recipe *actually* trimmed, so with
    ``auto_crop`` off it is ``None`` even on a mosaic — matching the recipe, which
    is the whole point of this function. ``trim_fraction_available`` reports what
    the trim *would* have removed, so the UI can offer "Auto could trim 12% of
    ragged edge" without lying about what happened.
    """
    out: dict[str, Any] = {
        "sky": None,
        "sky_sigma": None,
        "noisy": None,
        "noise_fraction": None,
        "median_fwhm": (round(float(median_fwhm), 2)
                        if median_fwhm is not None and median_fwhm > 0 else None),
        "sharpen_radius": None,
        "is_mosaic": bool(is_mosaic),
        "trim_fraction": None,
        "trim_fraction_available": None,
        "auto_crop": bool(auto_crop),
    }
    if rgb is not None:
        a = analyze_proxy(rgb)
        sky_sigma = float(a["sky_sigma"])
        out["sky"] = round(float(a["sky"]), 3)
        out["sky_sigma"] = round(sky_sigma, 4)
        out["noisy"] = bool(a["noisy"])
        out["noise_fraction"] = round(_noise_fraction(sky_sigma), 3)
    if median_fwhm is not None and median_fwhm > 0:
        # Only meaningful when a sharpen actually runs (clean/mildly-noisy data);
        # reported unconditionally here since it's the star size Auto *would* use.
        out["sharpen_radius"] = _sharpen_radius_from_fwhm(median_fwhm)
    if trim_crop is not None:
        x0, y0, x1, y1 = trim_crop
        kept = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        frac = round(max(0.0, 1.0 - kept), 3)
        out["trim_fraction_available"] = frac
        if auto_crop:
            out["trim_fraction"] = frac
    return out


# Plain-language phrase for each editor op the Auto recipe can emit — the Python
# mirror of the frontend's OP_PHRASES (autoSummary.ts), so an auto-edit applied by
# an *unattended* job (Process-target / reprocess-everything / watcher auto-stack)
# can stamp the same "what Auto did" note the interactive editor shows a user who
# clicks Auto. Keyed by op id; an unlisted op falls back to its raw id so it
# degrades gracefully as the op set changes.
_AUTO_OP_PHRASES: dict[str, str] = {
    "background.level_coverage": "evened out the mosaic panel brightness",
    "background.final_gradient": "flattened the background",
    "background.subtract": "removed the background gradient",
    "tone.color_calibrate": "balanced the colour",
    "detail.denoise": "reduced noise",
    "detail.chroma_denoise": "evened out the patchy sky colour",
    "tone.stretch": "applied a natural stretch",
    "tone.curves": "added a gentle contrast curve",
    "tone.scnr": "removed the green cast",
    "tone.saturation": "boosted colour saturation",
    "detail.sharpen": "sharpened detail",
    "detail.deconvolve": "deconvolved to recover sharpness",
    "geometry.crop": "trimmed the ragged mosaic border",
}


def _auto_num(n: float) -> str:
    """Compact number for the note: up to 2 decimals, no trailing-zero padding
    (0.101 → "0.1", 4.7 → "4.7", 1.05 → "1.05").

    The frontend's `fmt` (``components/editor/autoSummary.ts``) writes the same
    numbers into the same clause for the same picture — the editor's "what Auto
    did" note and the one an unattended job stamps on the History Info panel — so
    the pair is pinned from both sides against
    ``frontend/src/components/editor/autoNum.cases.json``
    (``tests/test_auto_summary_mirror.py``).

    **``floor(x + 0.5)``, not ``round()``**: Python rounds a half to *even* and
    JavaScript's ``Math.round`` rounds it *up*, so a measured 0.125 sky read
    "a ~0.12 sky" here and "a ~0.13 sky" in the editor — the same defect
    :func:`seestack.stackhealth._factor_label` was fixed for in v0.332.1, in a
    function whose docstring already claimed to mirror this one.

    **A positive value never renders as "0".** Two decimals is the right
    precision for a stretch target or a star size, but a *linear* stack's sky
    sits well below 0.01, so the bundled sample's measured 0.001 sky read
    "measured a ~0 sky" in the running app — which says the app measured
    nothing, one line above "sky level 0.24". When two decimals round a positive
    number away, it falls back to three, which is exactly the precision
    ``analyze_auto_inputs`` carries (it rounds ``sky`` to 3 dp), so nothing below
    what was actually measured is ever invented."""
    value = float(n)
    r = math.floor(value * 100 + 0.5) / 100
    if r == 0 and value > 0:
        r = math.floor(value * 1000 + 0.5) / 1000
    return str(int(r)) if r == int(r) else str(r)


def _auto_cause_clause(analysis: dict[str, Any] | None) -> str | None:
    """The measured cues that drove the recipe, as a clause (no leading verb) —
    the Python mirror of the frontend's `autoCauseSentence`. Reads the nullable
    ``analyze_auto_inputs`` payload and lists only cues that were actually measured,
    returning ``None`` when none were (e.g. an unmeasurable proxy, no solved stars,
    a single-field stack)."""
    if not analysis:
        return None
    parts: list[str] = []
    sky = analysis.get("sky")
    if isinstance(sky, (int, float)):
        parts.append(f"a ~{_auto_num(sky)} sky")
    fwhm = analysis.get("median_fwhm")
    if isinstance(fwhm, (int, float)):
        parts.append(f"{_auto_num(fwhm)} px stars")
    noise = analysis.get("noise_fraction")
    if isinstance(noise, (int, float)) and noise > 0:
        parts.append("a noisy background" if noise >= 0.75 else "some background noise")
    trim = analysis.get("trim_fraction")
    if isinstance(trim, (int, float)) and trim >= 0.005:
        # `floor(x + 0.5)` is `Math.round`, which is what the frontend clause
        # uses — see :func:`_auto_num`. `round()` here made a 0.125 trim read
        # "12%" beside the editor's "13%" for one picture.
        parts.append(f"{math.floor(trim * 100 + 0.5)}% of ragged mosaic edge to trim")
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])}, {parts[-1]}"


def auto_edit_summary(recipe: Recipe, analysis: dict[str, Any] | None = None) -> str | None:
    """A single plain-language note describing what the Auto recipe did (and, when
    measured, the data that drove it) — so an auto-edit applied silently by an
    unattended job can be shown on the History Info panel, matching the reasoning
    the interactive editor surfaces when a user clicks Auto themselves.

    Pure. Returns ``None`` when the recipe has no enabled ops (nothing to explain),
    so the caller simply stores nothing. e.g. "Auto-edited: flattened the
    background, balanced the colour, then sharpened detail · measured a ~0.1 sky,
    4.7 px stars, 12% of ragged mosaic edge to trim."
    """
    seen: set[str] = set()
    phrases: list[str] = []
    for op in recipe.ops:
        if not op.enabled:
            continue
        phrase = _AUTO_OP_PHRASES.get(op.id, op.id)
        if phrase in seen:
            continue
        seen.add(phrase)
        phrases.append(phrase)
    if not phrases:
        return None
    if len(phrases) == 1:
        did = phrases[0]
    elif len(phrases) == 2:
        did = f"{phrases[0]}, then {phrases[1]}"
    else:
        did = f"{', '.join(phrases[:-1])}, then {phrases[-1]}"
    note = f"Auto-edited: {did}"
    cause = _auto_cause_clause(analysis)
    if cause:
        note += f" · measured {cause}"
    return note + "."
