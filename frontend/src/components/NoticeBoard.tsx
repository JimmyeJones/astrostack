import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Anchor, Group, Stack } from "@mantine/core";
import { IconChevronDown, IconChevronUp } from "@tabler/icons-react";

/**
 * One note offered to the board. ``priority`` is what decides the inline slots:
 * lower sorts first, so a blocking problem always outranks a congratulation.
 *
 * ``node`` may render nothing at all — most of this app's notes are self-hiding
 * components that fetch their own data and return null when they have nothing to
 * say. The board copes with that (see below), so callers can hand over every
 * possible note without knowing which will speak up.
 */
export type Notice = {
  key: string;
  priority: number;
  node: ReactNode;
};

/** Severity rungs, so callers rank notes by meaning rather than by magic number.
 *  Lower = more urgent = more likely to get one of the inline slots. */
export const NOTICE_PRIORITY = {
  /** Something is broken and blocks the user's next step. */
  blocking: 10,
  /** A real problem with the data or the result — worth acting on. */
  warning: 20,
  /** An offer or a nudge: "ready to process?", "restack to fold in new subs". */
  advisory: 30,
  /** Context and reassurance — nothing is wrong. */
  info: 40,
  /** "Nice job" — a payoff or a personal record. Never outranks a warning. */
  praise: 50,
} as const;

/**
 * A single, prioritised "notes" area that replaces a wall of stacked alerts.
 *
 * The Target page had grown ~15 consecutive alert/note/badge blocks *above* its
 * own title — the owner's top complaint about the app ("there are like 30
 * different things on the top of some of the pages and I have to scroll a fair
 * bit to get to the actual info"). Nothing here is dropped: every note is still
 * rendered and still reachable in one click. The board just shows the most
 * important one or two and folds the rest behind a "N more notes" line.
 *
 * **Why it measures the DOM instead of asking the caller what to show.** Most of
 * these notes decide for themselves whether they have anything to say, from data
 * they fetch internally (`SkyBrightnessNote`, `SharpestYetBadge`,
 * `StackNoiseBadge`…). The parent genuinely cannot know how many will speak up,
 * and a wrong count ("2 more notes" that opens onto nothing) is worse than no
 * disclosure at all. So the board renders every note, then measures which ones
 * actually produced DOM and counts only those. Hidden notes stay **mounted and
 * hidden with CSS** rather than unmounted, so nothing remounts (and refetches)
 * when the board expands, and a note that arrives late is picked up by the
 * observer below.
 */
export function NoticeBoard({
  items,
  inlineCount = 2,
  "data-testid": testId,
}: {
  items: Notice[];
  /** How many of the highest-priority speaking notes stay inline. */
  inlineCount?: number;
  "data-testid"?: string;
}) {
  const ordered = [...items].sort((a, b) => a.priority - b.priority);
  const hosts = useRef(new Map<string, HTMLDivElement | null>());
  const container = useRef<HTMLDivElement | null>(null);
  const [speaking, setSpeaking] = useState<string[]>([]);
  const [open, setOpen] = useState(false);

  // The current display order, kept in a ref so `measure` can stay identity-
  // stable (it is a MutationObserver callback) while still seeing fresh keys.
  const orderRef = useRef<string[]>([]);
  orderRef.current = ordered.map((i) => i.key);

  const measure = useCallback(() => {
    const next = orderRef.current.filter(
      (k) => (hosts.current.get(k)?.childNodes.length ?? 0) > 0,
    );
    setSpeaking((prev) =>
      prev.length === next.length && prev.every((k, i) => k === next[i]) ? prev : next,
    );
  }, []);

  // Measure after every render (a note that changes its mind re-renders the
  // parent's children), and again whenever a child mutates its own DOM after an
  // async fetch — the parent does not re-render for that, so the observer is
  // what keeps the count honest.
  useEffect(measure);
  useEffect(() => {
    const root = container.current;
    if (!root || typeof MutationObserver === "undefined") return;
    const obs = new MutationObserver(() => measure());
    obs.observe(root, { childList: true, subtree: true });
    return () => obs.disconnect();
  }, [measure]);

  const inlineKeys = new Set(speaking.slice(0, inlineCount));
  const hiddenCount = Math.max(0, speaking.length - inlineKeys.size);

  return (
    <Stack gap="xs" ref={container} data-testid={testId}>
      {ordered.map((item) => {
        // Before the first measurement everything is inline, so a note is never
        // invisible on first paint (and a JS-free/observer-free environment
        // degrades to the old always-on wall rather than to a blank area).
        const hide = speaking.length > 0 && !inlineKeys.has(item.key) && !open;
        return (
          <div
            key={item.key}
            ref={(el) => {
              if (el) hosts.current.set(item.key, el);
              else hosts.current.delete(item.key);
            }}
            style={hide ? { display: "none" } : undefined}
          >
            {item.node}
          </div>
        );
      })}
      {hiddenCount > 0 ? (
        <Group gap={4}>
          <Anchor
            component="button"
            type="button"
            size="sm"
            c="dimmed"
            onClick={() => setOpen((v) => !v)}
          >
            <Group gap={4} wrap="nowrap">
              {open
                ? `Hide ${hiddenCount} note${hiddenCount === 1 ? "" : "s"}`
                : `${hiddenCount} more note${hiddenCount === 1 ? "" : "s"}`}
              {open ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
            </Group>
          </Anchor>
        </Group>
      ) : null}
    </Stack>
  );
}
