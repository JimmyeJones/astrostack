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

:func:`seestack.edit.pipeline.apply_recipe` is the source of truth for ordering and
the single-stretch rule.
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
    proxy_scale: float = 1.0          # full_width / proxy_width (>=1)
    is_proxy: bool = False            # True for the live preview proxy
    use_gpu: bool | None = None
    stage: Stage = "linear"           # updated by the pipeline as it crosses stretch

    def scaled_px(self, px: float) -> float:
        """Convert a *full-resolution* pixel measure to this render's pixel scale.

        On the decimated live-preview proxy (``proxy_scale > 1``) a feature that
        spans ``px`` full-res pixels spans only ``px / proxy_scale`` proxy pixels,
        so spatial ops (sharpen radius, denoise spatial extent, …) must shrink
        their pixel radii by the same factor for the preview to match the
        full-res export. On the export (``proxy_scale == 1``) this is a no-op.
        """
        return px / max(1.0, self.proxy_scale)


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
