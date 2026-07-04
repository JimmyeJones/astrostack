import type { EditOp, OpInstance } from "../../api/client";

/** True when the op instance has at least one param whose value differs from the
 * op's schema default — i.e. the user (or Auto/a preset) has tuned it away from
 * stock. Mirrors the per-param `isDefault` comparison used in OpParamPanel:
 * a missing/null value counts as the default (that's what the form renders).
 * Params the schema doesn't know about (stale keys) are ignored. */
export function opModified(op: OpInstance, spec: EditOp | undefined): boolean {
  if (!spec) return false;
  const params = op.params ?? {};
  return spec.params.some((p) => {
    const current = params[p.key] ?? p.default;
    return JSON.stringify(current) !== JSON.stringify(p.default);
  });
}
