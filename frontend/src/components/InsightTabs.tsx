import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Tabs } from "@mantine/core";

/**
 * One group of analysis cards offered to the tab strip.
 *
 * ``node`` may render nothing at all — most of this app's analysis cards are
 * self-hiding components that fetch their own data and return null when they
 * have nothing to say (no nights yet, no location set, only one stack to
 * compare). The strip copes with that, so callers can hand over every group
 * without knowing which will have content.
 */
export type InsightGroup = {
  key: string;
  label: string;
  node: ReactNode;
};

/**
 * A tabbed home for the page's analysis cards, replacing a tall stack of them.
 *
 * The Target page rendered **nine** full analysis cards one below another
 * between the picture and the frames table — the second half of the owner's top
 * complaint about the app ("there are like 30 different things on the top of
 * some of the pages and I have to scroll a fair bit to get to the actual
 * info"). Nothing here is dropped: every card is still rendered and still one
 * click away. The strip just shows one group at a time.
 *
 * **Why it measures the DOM instead of trusting the group list.** Most of these
 * cards decide for themselves whether they have anything to say, from data they
 * fetch internally. A tab that opens onto an empty panel is worse than no tab,
 * and the parent genuinely cannot know which cards will speak up — so the strip
 * renders every group, measures which ones actually produced DOM, and shows a
 * tab only for those. Panels stay **mounted** (Mantine's ``keepMounted``), so
 * switching tabs never remounts or refetches a card, and a card that arrives
 * late — or changes its mind — is picked up by the observer below.
 *
 * Degrades safely: before the first measurement every group gets a tab, so a
 * JS-poor environment sees the old always-on behaviour rather than a blank area.
 * With nothing to say at all it renders nothing.
 */
export function InsightTabs({
  groups,
  "data-testid": testId,
}: {
  groups: InsightGroup[];
  "data-testid"?: string;
}) {
  const hosts = useRef(new Map<string, HTMLDivElement | null>());
  const container = useRef<HTMLDivElement | null>(null);
  const [speaking, setSpeaking] = useState<string[] | null>(null);
  const [active, setActive] = useState<string | null>(null);

  // The current group order, kept in a ref so `measure` can stay identity-stable
  // (it is a MutationObserver callback) while still seeing fresh keys.
  const orderRef = useRef<string[]>([]);
  orderRef.current = groups.map((g) => g.key);

  const measure = useCallback(() => {
    const next = orderRef.current.filter(
      (k) => (hosts.current.get(k)?.childNodes.length ?? 0) > 0,
    );
    setSpeaking((prev) =>
      prev !== null && prev.length === next.length && prev.every((k, i) => k === next[i])
        ? prev
        : next,
    );
  }, []);

  // Measure after every render, and again whenever a card mutates its own DOM
  // after an async fetch — the parent does not re-render for that, so the
  // observer is what keeps the tab strip honest.
  useEffect(measure);
  useEffect(() => {
    const root = container.current;
    if (!root || typeof MutationObserver === "undefined") return;
    const obs = new MutationObserver(() => measure());
    obs.observe(root, { childList: true, subtree: true });
    return () => obs.disconnect();
  }, [measure]);

  // Before the first measurement, offer every group a tab (see "degrades safely").
  const shown = speaking === null ? groups : groups.filter((g) => speaking.includes(g.key));
  // Keep the user's chosen tab while it still has something in it; otherwise fall
  // back to the first group that does, so the panel on screen is never empty.
  const value = active && shown.some((g) => g.key === active) ? active : shown[0]?.key ?? null;

  return (
    <div ref={container} data-testid={testId}
      style={speaking !== null && speaking.length === 0 ? { display: "none" } : undefined}>
      <Tabs value={value} onChange={setActive} keepMounted mt="xs">
        {shown.length > 1 ? (
          // Short labels on purpose: the owner reads these pages on a phone, and a
          // tab strip that overflows is its own kind of busy.
          <Tabs.List>
            {shown.map((g) => (
              <Tabs.Tab key={g.key} value={g.key}>{g.label}</Tabs.Tab>
            ))}
          </Tabs.List>
        ) : null}
        {/* Every group gets a panel, including ones with no tab: they stay mounted
            so their cards keep their data and can start speaking later. */}
        {groups.map((g) => (
          <Tabs.Panel key={g.key} value={g.key} pt="xs">
            <div
              ref={(el) => {
                if (el) hosts.current.set(g.key, el);
                else hosts.current.delete(g.key);
              }}
            >
              {g.node}
            </div>
          </Tabs.Panel>
        ))}
      </Tabs>
    </div>
  );
}
