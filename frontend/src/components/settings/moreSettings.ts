/**
 * "More settings" — the plain-words home for the settings a beginner is most
 * likely to be scared of, and the first slice of the owner-approved Settings
 * redesign (`docs/design/settings-redesign.md`).
 *
 * His words were *"most of those terms are very confusing and can seem scary to
 * mess with to the average person"* and then *"I want the expert settings dumbed
 * down so that an average user can adjust all settings as needed. They should be
 * warned of any unexpected consequences of editing things."* So every card here
 * is a title in plain words, one sentence on what it does, a control, and — the
 * moment its value differs from the default — an amber *Heads up* note saying
 * what that costs, with a one-click way back.
 *
 * This module is the **data and the arithmetic**, deliberately free of React, so
 * every warning's show/hide and every "Back to default" patch can be tested as a
 * value rather than through a render. `MoreSettings.tsx` draws it.
 *
 * Two rules the spec makes non-negotiable and this file keeps:
 *
 * - **Nothing is removed.** Every control here *also* still lives where it
 *   always did, on its own section of the page, until the later slices rebuild
 *   those sections. Each card therefore carries `was`, the old label(s), both as
 *   a visible line and as something the search box matches — so somebody who
 *   knows the old name can still find the setting by it.
 * - **A card may offer fewer choices than its field allows** (cores are All /
 *   Half / One, not a number box), but it must still *display* whatever is
 *   stored faithfully and keep it until the owner changes it. That is what the
 *   `custom` option on each choice card is for: it is never offered as something
 *   to pick, only shown, selected, when the stored value is not one of ours.
 *
 * Every warning sentence below was checked against the code it describes before
 * it shipped — the spec requires it, and the field-of-view one changed as a
 * result (see `astap_fov_deg`).
 */

export type SettingsForm = Record<string, unknown>;
export type SettingsPatch = Record<string, unknown>;

/**
 * How much care a change needs. Shape *and* text, never colour alone: the badge
 * is a word, and the dot beside it differs in lightness as well as hue.
 */
export type MoreBadge = "safe" | "pictures" | "side-effects";

export const BADGE_LABEL: Record<MoreBadge, string> = {
  safe: "Safe to change",
  pictures: "Changes future pictures",
  "side-effects": "Has side effects — read the note",
};

export const BADGE_COLOR: Record<MoreBadge, string> = {
  safe: "teal",
  pictures: "orange",
  "side-effects": "grape",
};

/** What the page knows about this box that a descriptor might need. */
export interface MoreCtx {
  /** Cores the NAS reports (`/api/system`), for the "Half" choice. */
  cpuCount: number | null;
}

/** One option on a choice card. `patch` is what picking it writes. */
export interface MoreChoice {
  id: string;
  label: string;
  patch: SettingsPatch;
  /**
   * True for the synthetic "whatever is stored" option. It is rendered
   * selected and disabled rather than offered, so a value we have no button
   * for is still visible and is never silently overwritten.
   */
  readOnly?: boolean;
}

interface MoreCommon {
  id: string;
  title: string;
  /** One sentence: what this does, in words the owner uses. */
  desc: string;
  /** The old label(s), shown as `Was: …` and matched by the search box. */
  was: string;
  badge: MoreBadge;
  /** Every `Settings` field this card can write. Drift-tested against the model. */
  keys: string[];
}

export interface MoreSwitch extends MoreCommon {
  kind: "switch";
  field: string;
  dflt: boolean;
  /** The consequence of the value being what it now is. */
  warn: (on: boolean) => string;
}

export interface MoreChoiceSetting extends MoreCommon {
  kind: "choice";
  /** The id of the option that is the default. */
  dflt: string;
  choices: (form: SettingsForm, ctx: MoreCtx) => MoreChoice[];
  selected: (form: SettingsForm, ctx: MoreCtx) => string;
  warn: (id: string, form: SettingsForm) => string;
}

export interface MoreSlider extends MoreCommon {
  kind: "slider";
  min: number;
  max: number;
  step: number;
  /** The slider position that is the default (not necessarily the stored value). */
  dflt: number;
  /** The slider position for what is stored. */
  value: (form: SettingsForm) => number;
  /** What a slider position writes. */
  patch: (v: number) => SettingsPatch;
  /** The position as a sentence fragment, e.g. "Wait 30 seconds". */
  format: (v: number) => string;
  minLabel: string;
  maxLabel: string;
  warn: (v: number) => string;
}

export type MoreSetting = MoreSwitch | MoreChoiceSetting | MoreSlider;

export interface MoreGroup {
  title: string;
  items: MoreSetting[];
}

/** The id of the synthetic "a value we have no button for" choice. */
export const CUSTOM_CHOICE = "custom";

const str = (form: SettingsForm, k: string): string =>
  (typeof form[k] === "string" ? (form[k] as string) : "");

const numOr = (form: SettingsForm, k: string, fallback: number): number =>
  (typeof form[k] === "number" && Number.isFinite(form[k] as number)
    ? (form[k] as number)
    : fallback);

/**
 * Settings the page hasn't loaded yet read as *unchanged*, never as changed.
 *
 * The form is empty on first paint and a test fixture may carry only the fields
 * it cares about; treating an absent key as "differs from the default" would
 * open a Heads up note about a value nobody has.
 */
const has = (form: SettingsForm, k: string): boolean =>
  Object.prototype.hasOwnProperty.call(form, k) && form[k] !== undefined;

// ---------------------------------------------------------------------------
// The cards
// ---------------------------------------------------------------------------

export const MORE_SETTINGS_GROUPS: MoreGroup[] = [
  {
    title: "Your folders and files",
    items: [
      {
        kind: "choice",
        id: "folders",
        title: "Where your photos and library live",
        desc:
          "AstroStack reads new subs from your drop folder and keeps stacks and "
          + "pictures in its library folder.",
        was: "Data root, Incoming dir, Library root",
        badge: "side-effects",
        keys: ["data_root", "incoming_dir", "library_root"],
        dflt: "standard",
        choices: () => [
          { id: "standard", label: "Standard (set when installed)", patch: { incoming_dir: "", library_root: "" } },
          // Picking this only *reveals* the three boxes; it writes nothing, so
          // choosing it and changing your mind costs nothing.
          { id: "custom", label: "Choose other folders", patch: {} },
        ],
        selected: (form) =>
          (str(form, "incoming_dir") || str(form, "library_root") ? "custom" : "standard"),
        warn: () =>
          "Nothing is moved for you. AstroStack will look in the new folders, so your "
          + "library will look empty until you move the files there yourself. Your raw "
          + "subs are never touched.",
      },
      {
        kind: "switch",
        id: "copy_to_cache",
        field: "copy_to_cache",
        title: "Make a working copy of each photo first",
        desc:
          "Off: AstroStack reads your subs right where they are. On: it copies each "
          + "one into its library before using it.",
        was: "Copy frames into local cache",
        badge: "side-effects",
        keys: ["copy_to_cache"],
        dflt: false,
        warn: () =>
          "Every sub is copied, so you need about as much free space again as your drop "
          + "folder holds, and importing a big night takes longer. Only worth it if your "
          + "drop folder is on a slow or unreliable network share.",
      },
      {
        kind: "slider",
        id: "job_history_limit",
        title: "How much job history to remember",
        desc: "The Jobs page keeps a record of finished imports and stacks.",
        was: "Job history to keep",
        badge: "safe",
        keys: ["job_history_limit"],
        min: 50,
        max: 2000,
        step: 50,
        dflt: 200,
        value: (form) => numOr(form, "job_history_limit", 200),
        patch: (v) => ({ job_history_limit: v }),
        format: (v) => `Last ${v.toLocaleString("en-GB")} jobs`,
        minLabel: "50",
        maxLabel: "2,000",
        warn: (v) =>
          (v > 200
            ? "Uses a little more disk, and the Jobs page can take a moment longer to open. "
              + "Your pictures aren't affected."
            : "Older job records are forgotten sooner. Your pictures aren't affected."),
      },
    ],
  },
  {
    title: "Noticing new photos",
    items: [
      {
        kind: "slider",
        id: "watch_quiet_period_s",
        title: "Wait after copying stops",
        desc:
          "AstroStack waits until a file has stopped changing before reading it, so it "
          + "never reads one that's half copied.",
        was: "Quiet period (s)",
        badge: "side-effects",
        keys: ["watch_quiet_period_s"],
        min: 10,
        max: 300,
        step: 10,
        dflt: 30,
        value: (form) => numOr(form, "watch_quiet_period_s", 30),
        patch: (v) => ({ watch_quiet_period_s: v }),
        format: (v) => `Wait ${v} seconds`,
        minLabel: "10 s",
        maxLabel: "5 min",
        warn: (v) =>
          (v < 30
            ? "A photo still being copied over Wi-Fi might be read half-finished and marked "
              + "as bad. You can re-check it later from the target's Frames tab."
            : "New subs will show up a little later after you copy them in."),
      },
      {
        kind: "slider",
        id: "watch_poll_interval_s",
        title: "Back-up check for new files",
        desc:
          "AstroStack normally notices new files instantly. This is a safety-net check in "
          + "case a network share doesn't report them.",
        was: "Poll interval (s)",
        badge: "safe",
        keys: ["watch_poll_interval_s"],
        min: 60,
        max: 1800,
        step: 60,
        dflt: 300,
        value: (form) => numOr(form, "watch_poll_interval_s", 300),
        patch: (v) => ({ watch_poll_interval_s: v }),
        format: (v) => `Every ${Math.round(v / 60)} min`,
        minLabel: "1 min",
        maxLabel: "30 min",
        warn: (v) =>
          (v < 300
            ? "Checks more often — a little more disk activity on your NAS, especially with "
              + "a large drop folder."
            : "If your share doesn't report new files, they could take up to "
              + `${Math.round(v / 60)} minutes to show up.`),
      },
    ],
  },
  {
    title: "Finding where each photo points",
    items: [
      {
        kind: "choice",
        id: "astap_fov_deg",
        title: "Telescope field of view",
        // The spec offered "Read from my photos" as a third choice and asked the
        // Builder to check first. It isn't one: `solve/runner._fov_deg_for_frame`
        // derives the field from every frame's own FOCALLEN/XPIXSZ and only ever
        // falls back to this number, so reading from the photos is not something
        // you can switch off. The help line says so instead, and the warning below
        // was rewritten to be true of that.
        desc:
          "How much sky one photo covers. AstroStack works this out from each photo "
          + "itself, so this is only used for a photo that doesn't say.",
        was: "ASTAP FOV (deg)",
        badge: "pictures",
        keys: ["astap_fov_deg"],
        dflt: "s50",
        choices: (form) => {
          const out: MoreChoice[] = [
            { id: "s30", label: "Seestar S30 (2.1°)", patch: { astap_fov_deg: 2.1 } },
            { id: "s50", label: "Seestar S50 (1.3°)", patch: { astap_fov_deg: 1.3 } },
          ];
          const v = numOr(form, "astap_fov_deg", 1.3);
          if (v !== 2.1 && v !== 1.3) {
            out.push({ id: CUSTOM_CHOICE, label: `Currently ${v}°`, patch: {}, readOnly: true });
          }
          return out;
        },
        selected: (form) => {
          const v = numOr(form, "astap_fov_deg", 1.3);
          if (v === 2.1) return "s30";
          if (v === 1.3) return "s50";
          return CUSTOM_CHOICE;
        },
        warn: () =>
          "A Seestar's photos say what telescope took them, so nothing normally uses this. "
          + "For a photo that doesn't say, a field of view that doesn't match the telescope "
          + "means that photo won't be placed — and a photo that isn't placed isn't stacked.",
      },
      {
        kind: "slider",
        id: "astap_timeout_s",
        title: "Time allowed per photo",
        desc:
          "How long to keep trying to place a hard photo (faint, cloudy or few stars) "
          + "before giving up on it.",
        was: "ASTAP timeout (s)",
        badge: "pictures",
        keys: ["astap_timeout_s"],
        min: 20,
        max: 300,
        step: 10,
        dflt: 60,
        value: (form) => numOr(form, "astap_timeout_s", 60),
        patch: (v) => ({ astap_timeout_s: v }),
        format: (v) => `${v} seconds`,
        minLabel: "20 s",
        maxLabel: "5 min",
        warn: (v) =>
          (v > 60
            ? "More faint frames get placed, but a cloudy night can take much longer to "
              + "process — AstroStack tries up to three times per photo, so a photo that "
              + `never places can take about ${v * 3} seconds.`
            : "Processing is quicker, but more faint frames end up unplaced and left out of "
              + "your stacks."),
      },
      {
        kind: "switch",
        id: "astap_use_solve_hints",
        field: "astap_use_solve_hints",
        title: "Use the telescope's own target as a starting point",
        desc:
          "The Seestar records where it was pointing; starting the search there is much "
          + "faster.",
        was: "Use telescope target as solve hint",
        badge: "pictures",
        keys: ["astap_use_solve_hints"],
        dflt: true,
        warn: () =>
          "Each photo is searched for across the whole sky, so placing them takes a lot "
          + "longer. Worth turning off only if your photos record the wrong coordinates.",
      },
      {
        kind: "switch",
        id: "astap_bootstrap_solve",
        field: "astap_bootstrap_solve",
        title: "Rescue faint fields",
        desc:
          "When single photos have too few stars to place, combine the un-placed ones "
          + "into a deeper image, place that, and copy the position back.",
        was: "Rescue faint fields with a deep-image solve",
        badge: "pictures",
        keys: ["astap_bootstrap_solve"],
        dflt: false,
        warn: () =>
          "More of a faint target's photos get used, but importing it takes noticeably "
          + "longer.",
      },
    ],
  },
  {
    title: "How hard your NAS works",
    items: [
      {
        kind: "choice",
        id: "cpu_workers",
        title: "Processor cores to use",
        desc: "More cores finish imports and stacks sooner.",
        was: "CPU workers",
        badge: "safe",
        keys: ["cpu_workers"],
        dflt: "all",
        choices: (form, ctx) => {
          const half = ctx.cpuCount && ctx.cpuCount > 2 ? Math.floor(ctx.cpuCount / 2) : null;
          const out: MoreChoice[] = [{ id: "all", label: "All (fastest)", patch: { cpu_workers: null } }];
          if (half) out.push({ id: "half", label: `Half (${half})`, patch: { cpu_workers: half } });
          out.push({ id: "one", label: "One", patch: { cpu_workers: 1 } });
          const v = form.cpu_workers;
          if (typeof v === "number" && v !== 1 && v !== half) {
            out.push({ id: CUSTOM_CHOICE, label: `Currently ${v}`, patch: {}, readOnly: true });
          }
          return out;
        },
        selected: (form, ctx) => {
          const v = form.cpu_workers;
          if (v === null || v === undefined || v === "") return "all";
          if (v === 1) return "one";
          const half = ctx.cpuCount && ctx.cpuCount > 2 ? Math.floor(ctx.cpuCount / 2) : null;
          if (half && v === half) return "half";
          return CUSTOM_CHOICE;
        },
        warn: () =>
          "Imports and stacks will take longer; in exchange your NAS stays more responsive "
          + "for other apps and file copies.",
      },
      {
        kind: "slider",
        id: "max_stack_memory_gb",
        title: "Memory limit for stacking",
        desc:
          "Big mosaics need a lot of memory. Automatic measures what's free before each "
          + "stack.",
        was: "Stack memory budget (GB)",
        badge: "side-effects",
        keys: ["max_stack_memory_gb"],
        min: 0,
        max: 64,
        step: 2,
        dflt: 0,
        // 0 is the "Automatic" end of the slider, and it is stored as `null`
        // rather than as a number — the field's own floor is 0.5 GB.
        value: (form) =>
          (typeof form.max_stack_memory_gb === "number" ? form.max_stack_memory_gb : 0),
        patch: (v) => ({ max_stack_memory_gb: v === 0 ? null : v }),
        format: (v) => (v === 0 ? "Automatic (recommended)" : `At most ${v} GB`),
        minLabel: "Automatic",
        maxLabel: "64 GB",
        warn: () =>
          "Set too low, big mosaics may be refused or drizzled at a smaller size. Set higher "
          + "than your NAS really has free, and it can run out of memory — other apps (or "
          + "AstroStack) may be stopped mid-job.",
      },
      {
        kind: "switch",
        id: "auto_reject_on_unattended",
        field: "auto_reject_on_unattended",
        title: "Let AstroStack choose satellite-trail removal on hands-off stacks",
        desc:
          "On a stack you didn't set up yourself, decide automatically how to drop "
          + "satellite trails and hot pixels.",
        was: "Let AstroStack pick outlier removal on hands-off stacks",
        badge: "pictures",
        keys: ["auto_reject_on_unattended"],
        dflt: false,
        warn: () =>
          "Hands-off stacks may take longer (an extra pass over the frames), but trails and "
          + "hot pixels are cleaned without you asking. A stack you set up by hand always "
          + "uses exactly what you picked.",
      },
    ],
  },
  {
    title: "Connecting to your Seestar",
    items: [
      {
        kind: "switch",
        id: "seestar_enabled",
        field: "seestar_enabled",
        title: "Show my Seestar's live status",
        desc:
          "Find the telescope on your home network and show what it's doing on the "
          + "Telescope page.",
        was: "Enable Seestar integration, Poll interval (s)",
        badge: "safe",
        keys: ["seestar_enabled", "seestar_poll_interval_s"],
        dflt: false,
        warn: () =>
          "AstroStack will look for the telescope on your home network every few minutes, "
          + "and check on it every few seconds while it's on.",
      },
      {
        kind: "switch",
        id: "seestar_control_enabled",
        field: "seestar_control_enabled",
        title: "Let AstroStack control the Seestar",
        desc: "Allow the Telescope page's buttons to send commands to the telescope.",
        was: "Allow control commands",
        badge: "side-effects",
        keys: ["seestar_control_enabled"],
        dflt: false,
        warn: () =>
          "AstroStack can then start, stop and move the telescope. Leave this off unless you "
          + "use those buttons — the Seestar app keeps working either way.",
      },
      {
        kind: "choice",
        id: "seestar_find",
        title: "How to find the Seestar",
        desc:
          "Searching works on most home networks. Typing the address is for unusual setups.",
        was: "Scan subnet (CIDR), Known device IPs, Scan interval (s)",
        badge: "safe",
        keys: ["seestar_scan_subnet", "seestar_known_ips", "seestar_scan_interval_s"],
        dflt: "search",
        choices: () => [
          { id: "search", label: "Search my network", patch: { seestar_known_ips: [] } },
          // Reveals the address box; nothing is written until an address is typed.
          { id: "typed", label: "I'll type its address", patch: {} },
        ],
        selected: (form) =>
          (Array.isArray(form.seestar_known_ips) && (form.seestar_known_ips as string[]).length > 0
            ? "typed"
            : "search"),
        warn: () =>
          "If the telescope's address changes (for example after your router restarts), "
          + "AstroStack won't find it until you update the address here.",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// The arithmetic every card needs
// ---------------------------------------------------------------------------

/** Does this card's value differ from its default? (Absent ⇒ no.) */
export function moreSettingChanged(
  d: MoreSetting, form: SettingsForm, ctx: MoreCtx,
): boolean {
  if (d.kind === "switch") {
    return has(form, d.field) && Boolean(form[d.field]) !== d.dflt;
  }
  if (d.kind === "slider") {
    return d.keys.some((k) => has(form, k)) && d.value(form) !== d.dflt;
  }
  return d.keys.some((k) => has(form, k)) && d.selected(form, ctx) !== d.dflt;
}

/** The Heads-up sentence, or `""` while the card sits at its default. */
export function moreSettingWarning(
  d: MoreSetting, form: SettingsForm, ctx: MoreCtx,
): string {
  if (!moreSettingChanged(d, form, ctx)) return "";
  if (d.kind === "switch") return d.warn(Boolean(form[d.field]));
  if (d.kind === "slider") return d.warn(d.value(form));
  return d.warn(d.selected(form, ctx), form);
}

/** What "Back to default (…)" writes. */
export function moreSettingResetPatch(d: MoreSetting, ctx: MoreCtx): SettingsPatch {
  if (d.kind === "switch") return { [d.field]: d.dflt };
  if (d.kind === "slider") return d.patch(d.dflt);
  const choice = d.choices({}, ctx).find((c) => c.id === d.dflt);
  return choice ? choice.patch : {};
}

/** What "Back to default (…)" promises, e.g. "Off", "Wait 30 seconds", "Standard". */
export function moreSettingDefaultLabel(d: MoreSetting, ctx: MoreCtx): string {
  if (d.kind === "switch") return d.dflt ? "On" : "Off";
  if (d.kind === "slider") return d.format(d.dflt);
  const choice = d.choices({}, ctx).find((c) => c.id === d.dflt);
  return choice ? choice.label : d.dflt;
}

/**
 * Does this card answer what was typed into "Find a setting"?
 *
 * Matches the new title, the plain-words sentence, the **old** label(s) and the
 * field names themselves, so somebody who remembers "CIDR", `astap_timeout_s`
 * or "Quiet period" finds the card that now holds it.
 */
export function moreSettingMatches(d: MoreSetting, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [d.title, d.desc, d.was, ...d.keys].join(" ").toLowerCase();
  return q.split(/\s+/).every((word) => hay.includes(word));
}

/** The groups with their non-matching cards dropped, and empty groups with them. */
export function filterMoreGroups(groups: MoreGroup[], query: string): MoreGroup[] {
  return groups
    .map((g) => ({ title: g.title, items: g.items.filter((d) => moreSettingMatches(d, query)) }))
    .filter((g) => g.items.length > 0);
}

/** Every `Settings` field "More settings" can write, for the drift test. */
export function moreSettingKeys(): string[] {
  const out = new Set<string>();
  for (const g of MORE_SETTINGS_GROUPS) for (const d of g.items) for (const k of d.keys) out.add(k);
  return [...out].sort();
}
