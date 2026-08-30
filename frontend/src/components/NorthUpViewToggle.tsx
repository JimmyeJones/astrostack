import { ActionIcon, Tooltip } from "@mantine/core";
import { IconCompass } from "@tabler/icons-react";

/**
 * "North up" as a way to *look* at a picture, not a way to overwrite it.
 *
 * Until now the only way to see one of your pictures oriented the way every
 * reference photo of the object is — North at the top — was History → Adjust →
 * tick → **Save**, which rewrites the stored preview on disk. That is a
 * destructive answer to a purely visual question, and before v0.305.0 it could
 * cost a processed run its look outright.
 *
 * The server already turns the *saved bytes* on the way out
 * (`…/preview?north_up=true`, and the same flag on the JPEG and the full-res
 * PNG), changing nothing on disk — so a surface that shows a picture can offer
 * the turn as a view. Nothing here writes anything.
 *
 * Deliberately **off by default**: the saved orientation is the one the owner
 * chose, and a picture that silently turned itself would read as a bug. The
 * choice is remembered per *viewer* in `localStorage` rather than on the run,
 * because it is a viewing preference, not a fact about the picture.
 */
export const NORTH_UP_VIEW_KEY = "astrostack.northUpView";

/** The viewer's remembered preference. Defaults to off, including when storage
 *  is unavailable (a private window, or a browser blocking site data) — the
 *  toggle still works for the session, it just isn't remembered. */
export function loadNorthUpView(): boolean {
  try {
    return window.localStorage.getItem(NORTH_UP_VIEW_KEY) === "1";
  } catch {
    return false;
  }
}

/** Remember the preference. Best-effort: a storage write that throws must never
 *  break the view the user just asked for. */
export function saveNorthUpView(on: boolean): void {
  try {
    window.localStorage.setItem(NORTH_UP_VIEW_KEY, on ? "1" : "0");
  } catch {
    /* storage unavailable — the toggle still works, it just won't be remembered */
  }
}

/**
 * The toolbar control. Only render it where the turn would actually *do*
 * something (the run reports a `north_up_deg`) — a toggle that visibly changes
 * nothing is worse than no toggle.
 */
export function NorthUpViewToggle(
  { on, onChange }: { on: boolean; onChange: (on: boolean) => void },
) {
  return (
    <Tooltip label={on ? "Showing North up — back to as saved" : "Turn so North is up"}>
      <ActionIcon
        size="lg" variant={on ? "light" : "subtle"} color={on ? "violet" : "gray"}
        data-testid="north-up-view"
        aria-label={on ? "Show the picture as saved" : "Turn the picture so North is up"}
        aria-pressed={on}
        onClick={() => onChange(!on)}
      >
        <IconCompass size={20} />
      </ActionIcon>
    </Tooltip>
  );
}
