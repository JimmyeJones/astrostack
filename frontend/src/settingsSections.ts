/**
 * The Settings page's sections, as addresses the rest of the app can link to.
 *
 * Settings is the app's tallest page by a factor of two, so it is split into
 * named sections at `/settings/<section>` (see `SectionTabs`). Several screens
 * send the user there to fix one specific thing — "Fix in Settings" on the
 * Dashboard's setup warnings, "Settings → Observing site" on the Tonight
 * planner, the star-database hint on a stack's health card — and landing them on
 * a section that doesn't contain the control they were sent for is worse than
 * the long page was.
 *
 * Keeping the section names here, typed, is what stops that: the page builds its
 * tabs from these literals and every inbound link asks for one by name, so a
 * renamed section is a compile error rather than a link that quietly lands on
 * the wrong tab.
 */
export const SETTINGS_SECTIONS = [
  "folders",
  "automation",
  "plate-solving",
  "observing-site",
  "stacking",
  "telescope",
  "maintenance",
] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

/** The URL of one Settings section, e.g. `/settings/observing-site`. */
export function settingsLink(section: SettingsSection): string {
  return `/settings/${section}`;
}
