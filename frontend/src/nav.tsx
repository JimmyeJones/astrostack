import {
  IconActivity, IconAward, IconChecklist, IconDatabase, IconFileText, IconFlask, IconGauge,
  IconLayoutGrid,
  IconGalaxy,
  IconMoon, IconPalette, IconRadar2, IconSettings, IconSparkles, IconStars, IconTelescope,
  IconVideo,
} from "@tabler/icons-react";
import type { ReactNode } from "react";

// IA slice (d) — the sidebar's shape.
//
// The sidebar used to be one flat list of 15 destinations, which is its own kind
// of busy: nothing told you that "My best pictures" and "Gallery" are the same
// sort of thing, or that "Logs" is somewhere you almost never go. The links are
// now grouped under a few plain-language headings.
//
// Two rules this list must keep (the owner's hard constraint on the whole IA
// effort — nothing may be removed or become harder to reach):
//   * every destination that was in the flat list is still here, exactly once;
//   * every link is still visible without a click — the headings *label* the
//     groups, they do not collapse them. Grouping is for scanning, not hiding.
// `nav.test.ts` pins both against a frozen copy of the original flat list.
export type NavLinkSpec = {
  to: string;
  label: string;
  icon: ReactNode;
  /** Exact-match only — the Dashboard, whose "/" is a prefix of everything. */
  end?: boolean;
};

export type NavSection = {
  /** `null` for the lead group, which sits above the first heading. */
  title: string | null;
  links: NavLinkSpec[];
};

export const NAV_SECTIONS: NavSection[] = [
  {
    // The home screen answers "what should I look at?", so it leads, unlabelled —
    // a heading over a single link is noise.
    title: null,
    links: [
      { to: "/", label: "Dashboard", icon: <IconGauge size={18} />, end: true },
    ],
  },
  {
    // What the user came for. Ordered from "all of them" to "the good ones".
    title: "Your pictures",
    links: [
      { to: "/library", label: "Library", icon: <IconStars size={18} /> },
      { to: "/gallery", label: "Gallery", icon: <IconLayoutGrid size={18} /> },
      { to: "/best", label: "My best pictures", icon: <IconAward size={18} /> },
      { to: "/sky-so-far", label: "Your sky, so far", icon: <IconSparkles size={18} /> },
      { to: "/life-list", label: "My life list", icon: <IconChecklist size={18} /> },
      { to: "/universe", label: "Your universe", icon: <IconGalaxy size={18} /> },
    ],
  },
  {
    // Deciding what to shoot, before you shoot it.
    title: "Plan a night",
    links: [
      { to: "/tonight", label: "Tonight", icon: <IconMoon size={18} /> },
      { to: "/sky", label: "Sky Map", icon: <IconRadar2 size={18} /> },
    ],
  },
  {
    // Getting frames in and turning them into a stack.
    title: "Capture & process",
    links: [
      { to: "/telescope", label: "Telescope", icon: <IconTelescope size={18} /> },
      { to: "/moon-sun", label: "Moon & Sun", icon: <IconVideo size={18} /> },
      { to: "/calibration", label: "Calibration", icon: <IconFlask size={18} /> },
      { to: "/combine", label: "Channel combine", icon: <IconPalette size={18} /> },
    ],
  },
  {
    // The housekeeping half: what the app is doing, and how it is set up.
    title: "System",
    links: [
      { to: "/jobs", label: "Jobs", icon: <IconActivity size={18} /> },
      { to: "/storage", label: "Storage", icon: <IconDatabase size={18} /> },
      { to: "/logs", label: "Logs", icon: <IconFileText size={18} /> },
      { to: "/settings", label: "Settings", icon: <IconSettings size={18} /> },
    ],
  },
];

/** Every nav destination, in render order — the flat view the tests check. */
export const NAV_LINKS: NavLinkSpec[] = NAV_SECTIONS.flatMap((s) => s.links);
