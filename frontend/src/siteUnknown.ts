/**
 * What to say when the night planner doesn't know where you are.
 *
 * "No location" has three genuinely different causes, and until now every
 * planning surface said the same thing to all of them: *"It reads your location
 * automatically from a plate-solved Seestar frame — so once you've solved some
 * subs it'll just work."* That is exactly right for an empty library, and
 * **false** for a library whose subs carry no `SITELAT` header: solving more of
 * them will never help. Reproduced 2026-09-12 by dogfooding the bundled sample —
 * which is plate-solved and carries no site header — so the app made that promise
 * with 27 solved subs on screen and a Library full of "Solved" badges.
 *
 * The backend now says which case it is (`webapp/site_location.SiteProbe`); this
 * file owns the sentence, so the surfaces that show it can't drift into three
 * claims about one fact. Pure: no React, no I/O.
 */

/** The reasons `GET /api/plan/tonight` can give for an unknown site. */
export type SiteUnknownReason = "no-frames" | "no-site-header" | "unreadable";

export interface SiteUnknownCopy {
  title: string;
  /** The explanation, minus the "set it manually under Settings" sentence —
   *  which every caller renders itself, because it carries a link. */
  body: string;
  /** The lead-in to the Settings → Observing site link, or `""` when pointing
   *  there is not the fix — which is the `"unreadable"` case, where the frames
   *  are the problem and a typed-in location would paper over a library that
   *  can't be read. Callers render the link itself. */
  settingsLead: string;
}

/** The wording for one reason — or for an older backend / an unrecognised value,
 *  which both fall back to today's sentence rather than inventing a new claim. */
export function siteUnknownCopy(
  reason: SiteUnknownReason | string | null | undefined,
): SiteUnknownCopy {
  switch (reason) {
    case "no-site-header":
      return {
        title: "Your subs don't say where you were",
        // Names the header rather than hiding it: someone whose files came out
        // of another tool can act on "it was stripped", and someone with a
        // Seestar learns that theirs normally does carry it.
        body: "AstroStack reads your observing location out of the subs "
          + "themselves — a Seestar writes it into every frame — but none of "
          + "yours carry one, so shooting or solving more of the same won't "
          + "help. Some cameras don't write it, and some processing tools strip "
          + "it out.",
        settingsLead: "Set it once and every planning screen works from then on:",
      };
    case "unreadable":
      return {
        title: "Couldn't read your frames",
        // Deliberately does NOT offer Settings as the fix: a location typed in
        // here would light up the planner while the frames themselves are still
        // unreachable, which is the more important problem.
        body: "AstroStack reads your observing location out of your subs, but it "
          + "couldn't open any of them just now. That usually means the storage "
          + "holding them is offline or the files have moved. The planner will "
          + "pick your location up on its own once they're readable again.",
        settingsLead: "",
      };
    default:
      return {
        title: "Set your observing location",
        body: "The planner needs to know where you're observing from. It reads "
          + "your location automatically from a plate-solved Seestar frame — so "
          + "once you've solved some subs it'll just work.",
        settingsLead: "You can also set it manually under",
      };
  }
}
