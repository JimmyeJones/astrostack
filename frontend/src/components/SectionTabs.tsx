import { useNavigate } from "react-router-dom";
import { Tabs } from "@mantine/core";
import type { ReactNode } from "react";

/** One named section of a page that is too tall to read in one go. */
export type PageSection = {
  key: string;
  label: string;
  node: ReactNode;
};

/**
 * A tab strip whose tabs are **pages**: each one lives at its own URL.
 *
 * This is the URL-addressable sibling of `InsightTabs`. That one groups
 * *self-hiding analysis cards*, so it measures the DOM to decide which tabs
 * deserve to exist. This one groups sections that always have something in them
 * (a settings form is never silent), and the thing it adds instead is an
 * address: `/settings/observing-site` is bookmarkable, shareable, survives a
 * reload, and can be linked to from the other side of the app — so "Settings →
 * Observing site" can actually *land* on the observing site rather than on a
 * page where it is one tab away and invisible.
 *
 * Panels stay **mounted** (`keepMounted`), which matters here for a reason the
 * analysis tabs didn't have: the sections share one edit buffer. A user can type
 * a folder path, switch to another section, and their unsaved edit is still
 * there when they come back — and any section's Save button still saves the lot.
 *
 * An unknown or missing section falls back to the first one rather than erroring,
 * so an old bookmark to a renamed section still lands somewhere useful.
 */
export function SectionTabs({
  sections,
  basePath,
  active,
  "data-testid": testId,
}: {
  sections: PageSection[];
  basePath: string;
  active?: string;
  "data-testid"?: string;
}) {
  const navigate = useNavigate();
  const value = sections.some((s) => s.key === active)
    ? (active as string)
    : sections[0]?.key ?? null;

  return (
    <Tabs
      value={value}
      onChange={(k) => k && navigate(`${basePath}/${k}`)}
      keepMounted
      data-testid={testId}
    >
      {/* Short labels on purpose: the owner reads this on a phone, where the
          strip wraps onto a second line rather than scrolling out of reach. */}
      <Tabs.List>
        {sections.map((s) => (
          <Tabs.Tab key={s.key} value={s.key}>{s.label}</Tabs.Tab>
        ))}
      </Tabs.List>
      {sections.map((s) => (
        <Tabs.Panel key={s.key} value={s.key} pt="md">
          {s.node}
        </Tabs.Panel>
      ))}
    </Tabs>
  );
}
