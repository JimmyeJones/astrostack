"""Operation registry for the non-destructive editor.

Each editor operation is a pure function on a float32 RGB ``(H, W, 3)`` array
(the same convention every engine op already uses), described by an :class:`OpSpec`
that also carries a parameter schema. The schema is a plain dataclass here so the
engine stays free of any ``webapp`` import; ``webapp/schemas.py`` adapts it to the
existing ``StackOptionField`` the frontend already knows how to render.

Operations declare a ``stage``:

* ``linear``    — must run on linear data, before the stretch (background/gradient,
  colour calibration, white balance, denoise, deconvolution).
* ``nonlinear`` — runs after the stretch, in display space ``[0, 1]`` (curves,
  levels, saturation, SCNR, sharpen, star reduction, geometry).
* ``any``       — valid either side of the stretch.

:func:`seestack.edit.pipeline.apply_recipe` executes ops in **recipe order** (it
does not reorder by stage — the UI flags and offers to fix a mis-placed op) and is
the source of truth for the single-stretch rule (it auto-inserts a default stretch
when the recipe has none).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import numpy as np

ParamType = Literal["bool", "int", "float", "str", "enum", "curve"]
Stage = Literal["linear", "nonlinear", "any"]


@dataclass
class EditParam:
    """One tunable parameter of an operation. Mirrors ``StackOptionField`` so the
    web layer can adapt it 1:1 and the frontend renders it generically."""

    key: str
    label: str
    type: ParamType
    default: Any = None
    group: Literal["simple", "advanced"] = "simple"
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None
    # Optional friendly display names for enum ``options`` (value -> label); the
    # form falls back to the raw value for any option without a mapping.
    option_labels: dict[str, str] | None = None
    help: str | None = None
    depends_on: str | None = None


@dataclass
class EditContext:
    """Carried through a recipe so ops can adapt to preview vs full-res."""

    wcs: Any | None = None
    coverage: np.ndarray | None = None
    # The honest per-pixel *frame count* for the same canvas, when the run wrote
    # one. `coverage` above is a sum of per-frame weights, which splits one real
    # mosaic panel across several sky-leveling bins once quality weighting is on;
    # binning on the frame count follows the panel geometry instead. ``None`` —
    # every run recorded before the sibling file existed — falls back to
    # `coverage`, which is exactly what those runs have always been leveled by.
    frame_coverage: np.ndarray | None = None
    proxy_scale: float = 1.0          # full_width / proxy_width (>=1)
    is_proxy: bool = False            # True for the live preview proxy
    use_gpu: bool | None = None
    stage: Stage = "linear"           # updated by the pipeline as it crosses stretch
    already_display: bool = False     # input is a tone-mapped display-space image
    #   (an editor export re-opened for editing): suppress the pipeline's default
    #   autostretch fallback so an empty recipe doesn't double-stretch it.
    op_notes: dict[str, Any] = field(default_factory=dict)
    #   A best-effort channel for an op to record a small, JSON-safe outcome the
    #   caller may want to surface (e.g. which colour-calibration path actually ran
    #   and on how many stars). Keyed by op id. Ops write it; nothing reads it in the
    #   pipeline itself, so leaving it unread is harmless.
    fitted: dict[str, Any] = field(default_factory=dict)
    #   What each op *measured from the image* this render — see :meth:`fit`.
    #   Written by the ops, keyed by the recipe op's ``uid``; nothing in the
    #   pipeline reads it, exactly like ``op_notes``.
    frozen_fits: dict[str, Any] | None = None
    #   Fits measured by an *earlier* render of the same recipe, to be reused
    #   instead of measured. See :meth:`fit`.
    op_uid: str | None = None
    #   The ``uid`` of the op currently being applied; set by the pipeline so
    #   :meth:`fit` can key a fit to one op instance rather than to an op *id*
    #   (a recipe may legitimately carry the same op twice with different params).

    def scaled_px(self, px: float) -> float:
        """Convert a *full-resolution* pixel measure to this render's pixel scale.

        On the decimated live-preview proxy (``proxy_scale > 1``) a feature that
        spans ``px`` full-res pixels spans only ``px / proxy_scale`` proxy pixels,
        so spatial ops (sharpen radius, denoise spatial extent, …) must shrink
        their pixel radii by the same factor for the preview to match the
        full-res export. On the export (``proxy_scale == 1``) this is a no-op.
        """
        return px / max(1.0, self.proxy_scale)

    # --- fitted values: measuring on one array, rendering another -------------
    #
    # Several ops don't just transform pixels — they first *measure the whole
    # image* and derive a number from it: the stretch takes each channel's robust
    # median and σ, auto-contrast reads the sky mode, colour calibration solves a
    # white balance from the star field, "Neutralize background" takes the sky's
    # per-channel medians. Handed a *window* of the picture those all fit the
    # window, so a 512×512 crop comes back stretched and colour-balanced
    # differently from the picture it was cut out of — which is why a render of a
    # region can't simply re-run the recipe at ``proxy_scale = 1``.
    #
    # ``fit`` is the channel that fixes it: an op asks for its fitted value by
    # name and gets either the value a previous whole-image render measured (when
    # the caller supplied one) or its own fresh measurement, which is recorded so
    # the caller *can* supply it next time. Every default leaves behaviour exactly
    # as it was: with no ``frozen_fits``, every op measures for itself as always,
    # and ``fitted`` is simply written and ignored.

    def _fit_key(self, name: str) -> str:
        return f"{self.op_uid}:{name}" if self.op_uid else name

    def frozen_fit(self, name: str, default: Any = None) -> Any:
        """The value frozen for this op's ``name``, or ``default`` when the caller
        supplied no fits (the ordinary render) or none for this op."""
        if not self.frozen_fits:
            return default
        return self.frozen_fits.get(self._fit_key(name), default)

    def record_fit(self, name: str, value: Any) -> Any:
        """Record ``value`` as what this op fitted, and return it unchanged."""
        self.fitted[self._fit_key(name)] = value
        return value

    def fit(self, name: str, compute: Callable[[], Any]) -> Any:
        """This op's fitted ``name``: the frozen one if one was supplied for it,
        otherwise ``compute()``. Either way it lands in :attr:`fitted`, so the
        result of a whole-image render can be fed straight back as
        ``frozen_fits`` for a render of one region of the same picture.

        ``compute`` is not called when a frozen value is present — measuring a
        window would be the very thing this exists to avoid — so it is also the
        place to keep an expensive measurement (a star solve, a mesh fit).
        """
        frozen = self.frozen_fit(name, _UNSET)
        return self.record_fit(name, compute() if frozen is _UNSET else frozen)


#: Distinguishes "no fit was frozen for this op" from a fit whose value is
#: legitimately ``None`` (a measurement that gave up — a degenerate image the
#: stretch can't anchor, a sky whose medians can't be taken). A frozen ``None``
#: must stay ``None`` rather than silently re-measuring on the window.
_UNSET: Any = object()


ApplyFn = Callable[[np.ndarray, dict[str, Any], EditContext], np.ndarray]


@dataclass
class OpSpec:
    id: str                                   # e.g. "tone.curves"
    label: str
    group: str                                # "tone" | "background" | "detail" | "stars_geometry"
    stage: Stage
    apply: ApplyFn
    params: list[EditParam] = field(default_factory=list)
    proxy_safe: bool = True                   # if False: skipped in live preview unless forced
    help: str | None = None
    is_stretch: bool = False                  # the single tone-mapping boundary op
    heavy: bool = False                       # expensive on the proxy (iterative/restoration);
                                              # the UI settles its preview debounce longer for these

    def defaults(self) -> dict[str, Any]:
        return {p.key: p.default for p in self.params}


_REGISTRY: dict[str, OpSpec] = {}


def register(spec: OpSpec) -> OpSpec:
    if spec.id in _REGISTRY:
        raise ValueError(f"duplicate edit op id: {spec.id}")
    _REGISTRY[spec.id] = spec
    return spec


def get_op(op_id: str) -> OpSpec | None:
    _ensure_loaded()
    return _REGISTRY.get(op_id)


def all_specs() -> list[OpSpec]:
    _ensure_loaded()
    return list(_REGISTRY.values())


_loaded = False


def _ensure_loaded() -> None:
    """Import the ops subpackage once so every ``register`` call has run."""
    global _loaded
    if not _loaded:
        _loaded = True
        from seestack.edit import ops  # noqa: F401  (import side effects register ops)


# ---- shared numeric helpers (NaN-aware) ------------------------------------

def as_rgb(rgb: np.ndarray) -> np.ndarray:
    """Coerce to a float32 (H, W, 3) array without copying when possible."""
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    if arr.shape[-1] > 3:
        arr = arr[..., :3]
    return arr


def finite_mask(rgb: np.ndarray) -> np.ndarray:
    """2-D mask of pixels covered in every channel (uncovered = NaN)."""
    return np.isfinite(rgb).all(axis=2)


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec.709 luma of an RGB image."""
    return (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])
