/** The night sky behind the app: a deep-navy page and a gentle parallax
 * starfield, both of which the route or the device can refuse.
 *
 * **It draws nothing per frame.** The three star layers are CSS animations on
 * three elements, so the compositor moves them and React is not involved once
 * they are mounted; this component's whole job is to decide *which* of the four
 * states the page is in and write them onto `<html>` as two attributes, which
 * `nightsky/nightsky.css` then styles. The decisions themselves are pure
 * functions in `nightsky/surround.ts`, so they are asserted without a DOM.
 *
 * The attributes go on `<html>` rather than on a wrapper because the deep-navy
 * *page* is a `body` background and a handful of Mantine colour variables — the
 * sky has to reach past this component's own subtree, including modals and
 * popovers, which render into portals.
 */
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { STARFIELD_PREF_EVENT, isStarfieldEnabled } from "../nightsky/prefs";
import { skyMotion, starfieldShown, surroundForPath } from "../nightsky/surround";
import "../nightsky/nightsky.css";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/** Read the media query defensively: `matchMedia` is absent on some older
 * surfaces and stubbed in the test DOM, and "no opinion" means "animate". */
function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia?.(REDUCED_MOTION_QUERY).matches === true;
  } catch {
    return false;
  }
}

function documentHidden(): boolean {
  try {
    return document.visibilityState === "hidden";
  } catch {
    return false;
  }
}

export function NightSky() {
  const { pathname } = useLocation();
  const [reducedMotion, setReducedMotion] = useState(prefersReducedMotion);
  const [hidden, setHidden] = useState(documentHidden);
  // Read once per mount rather than subscribing: the Settings switch reloads
  // nothing, it flips this component's own state through `starfieldPrefChanged`
  // below, and any other tab is a different document.
  const [enabled, setEnabled] = useState(isStarfieldEnabled);

  useEffect(() => {
    const onVisibility = () => setHidden(documentHidden());
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    let mql: MediaQueryList | undefined;
    try {
      mql = window.matchMedia?.(REDUCED_MOTION_QUERY);
    } catch {
      mql = undefined;
    }
    if (!mql?.addEventListener) return undefined;
    const onChange = () => setReducedMotion(prefersReducedMotion());
    mql.addEventListener("change", onChange);
    return () => mql?.removeEventListener("change", onChange);
  }, []);

  // The Settings switch writes `localStorage` and fires this, so the sky appears
  // or clears while you are looking at the switch — no reload, no shared store.
  useEffect(() => {
    const onPref = () => setEnabled(isStarfieldEnabled());
    window.addEventListener(STARFIELD_PREF_EVENT, onPref);
    return () => window.removeEventListener(STARFIELD_PREF_EVENT, onPref);
  }, []);

  const surround = surroundForPath(pathname);
  const motion = skyMotion(reducedMotion, hidden);
  const stars = starfieldShown(surround, enabled);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.astroSurround = surround;
    root.dataset.astroMotion = motion;
    return () => {
      // Leave the page as we found it if the shell ever unmounts (tests do).
      delete root.dataset.astroSurround;
      delete root.dataset.astroMotion;
    };
  }, [surround, motion]);

  if (!stars) return null;
  return (
    <div className="astro-nightsky" aria-hidden data-testid="night-sky">
      <div className="astro-nightsky__haze" />
      <div className="astro-nightsky__layer astro-nightsky__layer--far" />
      <div className="astro-nightsky__layer astro-nightsky__layer--mid" />
      <div className="astro-nightsky__layer astro-nightsky__layer--near" />
    </div>
  );
}