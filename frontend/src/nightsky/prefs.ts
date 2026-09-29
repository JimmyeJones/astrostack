/** Per-device preference for the night-sky starfield.
 *
 * Deliberately client-side (`localStorage`), not `webapp/config.py` — exactly the
 * `ambient/prefs.ts` bargain: whether stars drift behind the pages is a property
 * of the screen you are looking at (the lounge PC vs. a phone on a slow night),
 * so the feature adds no server setting, no config migration, and nothing that
 * can break an in-place upgrade.
 *
 * **Default ON**, which is the one way this differs from the soundbed: the owner
 * asked the app to *look* like this, so the starfield is what a fresh install
 * shows and the switch is how you turn it off. That means the stored value has to
 * record the *opt-out* — "0" is off, and absent/unreadable is on — rather than
 * the opt-in.
 */

const STARFIELD_KEY = "astrostack.nightsky.starfield";

/** Fired on `window` whenever the preference changes, so a mounted `NightSky`
 * picks the new value up immediately — the sky clears while you are still
 * looking at the switch, with no reload and no shared React state. */
export const STARFIELD_PREF_EVENT = "astrostack:starfield-pref";

/** Whether the drifting starfield is shown on *this* device. On unless someone
 * turned it off here. A disabled or throwing store reads as the default, so the
 * app shell never sees an exception from a preference. */
export function isStarfieldEnabled(): boolean {
  try {
    return localStorage.getItem(STARFIELD_KEY) !== "0";
  } catch {
    return true;
  }
}

export function setStarfieldEnabled(on: boolean): void {
  try {
    if (on) localStorage.removeItem(STARFIELD_KEY);
    else localStorage.setItem(STARFIELD_KEY, "0");
  } catch {
    /* private-mode / disabled storage — the preference just won't persist. */
  }
  // Announced even when the write failed: the switch should still do something
  // visible on a device whose store is disabled, for as long as the page lives.
  try {
    window.dispatchEvent(new Event(STARFIELD_PREF_EVENT));
  } catch {
    /* no window (SSR-shaped import) — nothing is mounted to tell. */
  }
}
