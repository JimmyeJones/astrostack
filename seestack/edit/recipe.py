"""Recipe model: an ordered list of editor operations + JSON (de)serialization.

A recipe is the non-destructive document. It is validated against the live op
registry on load — unknown ops are dropped and params are clamped/filtered to each
op's schema, exactly like ``coerce_stack_options`` does for stacking.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from seestack.edit.registry import EditParam, get_op

RECIPE_VERSION = 1


@dataclass
class OpInstance:
    id: str
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict[str, Any]:
        return {"uid": self.uid, "id": self.id, "enabled": self.enabled, "params": self.params}


@dataclass
class Recipe:
    ops: list[OpInstance] = field(default_factory=list)
    version: int = RECIPE_VERSION
    base_run_id: int | None = None
    updated_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "base_run_id": self.base_run_id,
            "updated_utc": self.updated_utc,
            "ops": [op.to_dict() for op in self.ops],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def _coerce_param(p: EditParam, value: Any) -> Any:
    """Clamp/coerce one parameter value to its declared type and range."""
    if value is None:
        return p.default
    try:
        if p.type == "bool":
            return bool(value)
        if p.type == "int":
            v = int(round(float(value)))
        elif p.type == "float":
            v = float(value)
        elif p.type == "enum":
            return value if (not p.options or value in p.options) else p.default
        elif p.type == "curve":
            # list of [x, y] control points in [0,1]; keep finite pairs, sorted by x.
            pts = [[float(a), float(b)] for a, b in value
                   if a is not None and b is not None]
            pts = [[min(1.0, max(0.0, a)), min(1.0, max(0.0, b))] for a, b in pts]
            return sorted(pts, key=lambda ab: ab[0]) or p.default
        else:  # str
            return str(value)
    except (TypeError, ValueError):
        return p.default
    if p.min is not None:
        v = max(p.min if p.type == "float" else int(p.min), v)
    if p.max is not None:
        v = min(p.max if p.type == "float" else int(p.max), v)
    return v


def validate_ops(ops: list[OpInstance]) -> list[OpInstance]:
    """Drop ops with unknown ids; clamp params to each op's schema."""
    out: list[OpInstance] = []
    for op in ops:
        spec = get_op(op.id)
        if spec is None:
            continue
        clean: dict[str, Any] = {}
        for p in spec.params:
            clean[p.key] = _coerce_param(p, op.params.get(p.key, p.default))
        out.append(OpInstance(id=op.id, params=clean, enabled=bool(op.enabled), uid=op.uid))
    return out


def recipe_from_dict(data: dict[str, Any]) -> Recipe:
    if not isinstance(data, dict):
        return Recipe()
    raw_ops = data.get("ops") or []
    ops: list[OpInstance] = []
    for o in raw_ops:
        if not isinstance(o, dict) or "id" not in o:
            continue
        # ``params`` must be a mapping; a malformed client body (or hand-built
        # recipe) can send a list/string/number here, which ``dict()`` would
        # raise on — an unhandled 500 in ``put_recipe``/``create_preset`` and a
        # failed export/PNG/batch job. Treat any non-mapping as empty params so
        # ``validate_ops`` fills each key from the op's defaults instead.
        raw_params = o.get("params")
        params = dict(raw_params) if isinstance(raw_params, dict) else {}
        ops.append(OpInstance(
            id=str(o["id"]),
            params=params,
            enabled=bool(o.get("enabled", True)),
            uid=str(o.get("uid") or uuid.uuid4().hex[:8]),
        ))
    return Recipe(
        ops=validate_ops(ops),
        version=int(data.get("version", RECIPE_VERSION)),
        base_run_id=data.get("base_run_id"),
        updated_utc=data.get("updated_utc"),
    )


def recipe_from_json(text: str | None) -> Recipe:
    if not text:
        return Recipe()
    try:
        return recipe_from_dict(json.loads(text))
    except (ValueError, TypeError):
        return Recipe()
