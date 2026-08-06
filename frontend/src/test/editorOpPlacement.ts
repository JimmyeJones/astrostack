// Guard against editor test fixtures drifting from the engine's real op spec.
//
// v0.240.0 shipped a correct, well-tested "from your image" button that no
// beginner could see: its hand-written `EditOp` fixture declared the
// `highlights` param as `group: "simple"` while the engine says `advanced`, and
// `OpParamPanel` renders advanced params inside a *collapsed* accordion. The
// tests passed because they were asserting against a fixture that placed the
// control somewhere the app never does.
//
// Only the fields that decide what a user can **reach** are pinned — `type`
// (which control gets rendered), `group` (behind the Advanced accordion or not)
// and `depends_on` (greyed out until another param has a particular value).
// Everything else (labels, defaults, bounds, help) is left free on purpose: a
// fixture is allowed to be a simplified stand-in, and mirroring the whole schema
// would just be a second copy to keep in step.
//
// `editorOpPlacement.json` is generated from `webapp.schemas.editor_ops_schema`;
// `tests/webapp/test_editor_op_placement.py` fails if it falls out of date and
// prints the command to regenerate it.
import type { EditOp } from "../api/client";
import placement from "./editorOpPlacement.json";

export interface ParamPlacement {
  type: string;
  group: string;
  depends_on: string | null;
}

/** The engine's placement for every editor op param, keyed op id → param key. */
export const ENGINE_PLACEMENT = placement as Record<string, Record<string, ParamPlacement>>;

/** The key a `depends_on` expression is gated on ("mode=asinh" → "mode"), or the
 * whole expression when it is a bare truthiness test. `null` for no dependency. */
function dependencyKey(dependsOn: string | null): string | null {
  if (!dependsOn) return null;
  const eq = dependsOn.indexOf("=");
  return eq >= 0 ? dependsOn.slice(0, eq) : dependsOn;
}

/**
 * Every way `op` places a param differently from the engine, as plain sentences.
 * An empty array means the fixture is faithful. Pure — no assertions, so it can
 * be unit-tested directly and used from any test file.
 *
 * An op id the engine doesn't have, or a param key the engine's op doesn't
 * carry, is ignored: fixtures for hypothetical ops are a legitimate way to test
 * the generic rendering machinery.
 *
 * A fixture that declares **no** dependency where the engine has one is accepted
 * *only* when it also omits the param that dependency is gated on — a partial
 * fixture that doesn't model the controlling param cannot honestly express the
 * gate, and showing the control unconditionally is the right simplification.
 * Any other difference is drift.
 */
export function placementMismatches(op: EditOp): string[] {
  const spec = ENGINE_PLACEMENT[op.id];
  if (!spec) return [];
  const declared = new Set(op.params.map((p) => p.key));
  const problems: string[] = [];
  for (const p of op.params) {
    const want = spec[p.key];
    if (!want) continue;
    const where = `${op.id}.${p.key}`;
    if (p.type !== want.type) {
      problems.push(`${where}: fixture type "${p.type}" but the engine says "${want.type}"`);
    }
    if (p.group !== want.group) {
      problems.push(`${where}: fixture group "${p.group}" but the engine says "${want.group}"`);
    }
    const have = p.depends_on ?? null;
    if (have !== want.depends_on) {
      const gate = dependencyKey(want.depends_on);
      const simplified = have === null && gate !== null && !declared.has(gate);
      if (!simplified) {
        problems.push(
          `${where}: fixture depends_on ${JSON.stringify(have)} but the engine says `
          + `${JSON.stringify(want.depends_on)}`);
      }
    }
  }
  return problems;
}

/** Convenience for a test that checks a whole set of fixtures at once. */
export function allPlacementMismatches(ops: EditOp[]): string[] {
  return ops.flatMap(placementMismatches);
}
