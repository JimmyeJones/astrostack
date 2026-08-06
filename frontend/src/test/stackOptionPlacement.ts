// Guard against Stack/Settings test fixtures drifting from the engine's real
// `StackOptions` descriptors — the sibling of `editorOpPlacement.ts`, on a form
// a beginner uses far more often than the editor.
//
// `Stack.tsx` and `Settings.tsx` render `StackOptionField[]` through the same
// descriptor-driven `StackOptionControl`, with the same `group: "simple" |
// "advanced"` accordion split and the same `depends_on` greying. Their tests
// build those fixtures by hand, so a fixture can put a control somewhere the
// running app never does and the test still passes — which is exactly how
// v0.240.0 shipped an editor button no beginner could see.
//
// Only the fields that decide what a user can **reach** are pinned — `type`
// (which control renders), `group` (behind the Advanced accordion or not) and
// `depends_on` (greyed until another field is set). Labels, defaults, bounds,
// options and help stay free on purpose: a fixture is allowed to be a
// simplified stand-in rather than a second copy of the schema.
//
// `stackOptionPlacement.json` is generated from `webapp.schemas
// .stack_option_fields`; `tests/webapp/test_stack_option_placement.py` fails if
// it falls out of date and prints the command to regenerate it.
import type { StackOptionField } from "../api/client";
import placement from "./stackOptionPlacement.json";

export interface StackFieldPlacement {
  type: string;
  group: string;
  depends_on: string | null;
}

/** The engine's placement for every stack option, keyed by field key. */
export const ENGINE_STACK_PLACEMENT =
  placement as Record<string, StackFieldPlacement>;

/** The key a `depends_on` expression is gated on ("mode=asinh" → "mode"), or the
 * whole expression when it is a bare truthiness test. `null` for no dependency. */
function dependencyKey(dependsOn: string | null): string | null {
  if (!dependsOn) return null;
  const eq = dependsOn.indexOf("=");
  return eq >= 0 ? dependsOn.slice(0, eq) : dependsOn;
}

/**
 * Every way this set of fixtures places a field differently from the engine, as
 * plain sentences. An empty array means the fixtures are faithful. Pure — no
 * assertions, so it can be unit-tested directly and used from any test file.
 *
 * A key the engine doesn't have is ignored: fixtures for hypothetical fields are
 * a legitimate way to test the generic rendering machinery.
 *
 * A fixture that declares **no** dependency where the engine has one is accepted
 * *only* when the set also omits the field that dependency is gated on — a
 * partial fixture that doesn't model the controlling field cannot honestly
 * express the gate, and rendering the control unconditionally is the right
 * simplification. Any other difference is drift.
 */
export function stackPlacementMismatches(fields: StackOptionField[]): string[] {
  const declared = new Set(fields.map((f) => f.key));
  const problems: string[] = [];
  for (const f of fields) {
    const want = ENGINE_STACK_PLACEMENT[f.key];
    if (!want) continue;
    if (f.type !== want.type) {
      problems.push(
        `${f.key}: fixture type "${f.type}" but the engine says "${want.type}"`);
    }
    if (f.group !== want.group) {
      problems.push(
        `${f.key}: fixture group "${f.group}" but the engine says "${want.group}"`);
    }
    const have = f.depends_on ?? null;
    if (have !== want.depends_on) {
      const gate = dependencyKey(want.depends_on);
      const simplified = have === null && gate !== null && !declared.has(gate);
      if (!simplified) {
        problems.push(
          `${f.key}: fixture depends_on ${JSON.stringify(have)} but the engine says `
          + `${JSON.stringify(want.depends_on)}`);
      }
    }
  }
  return problems;
}
