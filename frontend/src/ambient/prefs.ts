/** Per-device preferences for the optional ambient soundbed.
 *
 * Deliberately client-side (`localStorage`), not `webapp/config.py`: whether
 * music plays is inherently per-device — on for the box in the lounge, off for
 * the phone at 2 a.m. — and keeping it here means the feature adds no server
 * setting, no config migration, and nothing that can break an upgrade.
 *
 * Follows the `jobNotify.ts` precedent: read fresh at use time, every access
 * wrapped so a disabled or full store degrades to the default instead of
 * throwing inside the app shell.
 */

const ENABLED_KEY = "astrostack.ambient.enabled";
const VOLUME_KEY = "astrostack.ambient.volume";

/** Quiet enough to talk over, loud enough to hear. */
export const DEFAULT_VOLUME = 0.4;

/** Whether the user has opted in on *this* device. Off unless explicitly set —
 * a fresh install must be silent. */
export function isAmbientEnabled(): boolean {
  try {
    return localStorage.getItem(ENABLED_KEY) === "1";
  } catch {
    return false;
  }
}

export function setAmbientEnabled(on: boolean): void {
  try {
    if (on) localStorage.setItem(ENABLED_KEY, "1");
    else localStorage.removeItem(ENABLED_KEY);
  } catch {
    /* private-mode / disabled storage — the preference just won't persist. */
  }
}

/** Saved volume in 0–1, falling back to the default for anything unusable
 * (absent, blank, non-numeric, or out of range from a hand-edited store). */
export function ambientVolume(): number {
  try {
    const raw = localStorage.getItem(VOLUME_KEY);
    if (raw === null || raw.trim() === "") return DEFAULT_VOLUME;
    const v = Number(raw);
    if (!Number.isFinite(v) || v < 0 || v > 1) return DEFAULT_VOLUME;
    return v;
  } catch {
    return DEFAULT_VOLUME;
  }
}

export function setAmbientVolume(volume: number): void {
  const v = Number.isFinite(volume) ? Math.min(1, Math.max(0, volume)) : DEFAULT_VOLUME;
  try {
    localStorage.setItem(VOLUME_KEY, String(v));
  } catch {
    /* see above — best-effort persistence only. */
  }
}
