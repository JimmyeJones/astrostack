/** Descriptor-driven forms (Stack, Settings, editor ops) gate a field on another
 * field via `depends_on`. Historically this was a plain boolean toggle key
 * ("show this only while `sigma_clip` is on"); this helper additionally supports
 * an enum-value form `"key=value"` so a field can depend on a *specific* choice
 * of another param (e.g. the Asinh strength only applies while the stretch's
 * `mode` is `asinh`). A bare key stays a truthiness check, so every existing
 * boolean `depends_on` keeps working unchanged. */
export function dependencyMet(
  dependsOn: string | null | undefined,
  get: (key: string) => unknown,
): boolean {
  if (!dependsOn) return true;
  const eq = dependsOn.indexOf("=");
  if (eq >= 0) {
    const key = dependsOn.slice(0, eq);
    const want = dependsOn.slice(eq + 1);
    return String(get(key)) === want;
  }
  return !!get(dependsOn);
}
