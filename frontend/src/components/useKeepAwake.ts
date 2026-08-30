import { useEffect } from "react";

/**
 * Hold the screen awake while `active` is true.
 *
 * Two pages in this app are designed to be *left open*: the "Show and tell"
 * slideshow (point a screen at it in a room full of people) and "Tonight, live"
 * (propped on a phone, outdoors, for hours). On both, the screen going black is
 * the one failure that makes the feature feel broken — you walk over to check
 * and there's nothing there. This is the single implementation both use; it
 * lived inside `ShowAndTell` first.
 *
 * Every call is guarded. The Screen Wake Lock API is absent on some browsers
 * (and in the test DOM), and it *rejects* when the page isn't visible — a
 * slideshow that throws on the way to the TV is worse than one that lets the
 * screen dim. Browsers also drop the lock whenever the tab is hidden, so it is
 * re-requested on `visibilitychange`. Nothing is persisted and nothing is
 * configurable; passing `false` releases it.
 */
export function useKeepAwake(active: boolean) {
  useEffect(() => {
    if (!active) return undefined;
    const wl = (navigator as Navigator & {
      wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> };
    }).wakeLock;
    if (!wl || typeof wl.request !== "function") return undefined;

    let released = false;
    let sentinel: { release: () => Promise<void> } | null = null;

    const acquire = async () => {
      if (released || document.visibilityState !== "visible") return;
      try {
        sentinel = await wl.request("screen");
      } catch {
        // Denied, unsupported on this surface, or the page went hidden between
        // the check and the call. Nothing to do — the screen just dims.
      }
    };
    const onVisible = () => { if (document.visibilityState === "visible") void acquire(); };

    void acquire();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      released = true;
      document.removeEventListener("visibilitychange", onVisible);
      try {
        void sentinel?.release();
      } catch {
        // A lock the browser already dropped throws on release; harmless.
      }
    };
  }, [active]);
}
