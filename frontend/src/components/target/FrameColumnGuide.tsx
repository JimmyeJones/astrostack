import { Anchor, Collapse, Stack, Text } from "@mantine/core";
import { useState } from "react";
import { FRAME_COLUMNS } from "./frameColumns";

/**
 * "What do these numbers mean?" — the frames table's column headings, explained
 * in text a phone can actually show.
 *
 * The headings are already dotted-underlined and already carry a good
 * plain-language sentence each — but only as a `Tooltip`, which opens on hover
 * or focus. A phone has no hover, and a tap on one of these headings *sorts the
 * table*, so on the device the owner reads this app on there has never been any
 * way to find out what `FWHM`, `Ecc.`, `Sky` or `Transp.` mean. That is four of
 * the table's five numeric columns explained nowhere, on the page a beginner
 * spends the most time on.
 *
 * Deliberately a **disclosure, not a legend**: the standing complaint about this
 * app is that its pages are too tall, so this costs one line until it is asked
 * for, and the tooltips are left exactly as they are for anyone with a mouse.
 * The wording is not new — it is the same `hint` strings the tooltips use, from
 * the same array, so the two can never drift.
 */
export function FrameColumnGuide() {
  const [open, setOpen] = useState(false);
  const explained = FRAME_COLUMNS.filter((c) => c.hint);

  return (
    <Stack gap={4} mb={4}>
      <Anchor
        component="button"
        type="button"
        size="xs"
        fw={500}
        data-testid="frame-column-guide-toggle"
        style={{ alignSelf: "flex-start" }}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "Hide what these numbers mean" : "What do these numbers mean? →"}
      </Anchor>
      {/* Mounted only while open, deliberately. It is static text — nothing here
          fetches, so there is nothing to lose by unmounting it — and leaving it
          in the DOM would put words like "trailed" on a page that is otherwise
          careful about when it says them. */}
      <Collapse in={open}>
        {open ? (
        <Stack gap={6} pl={4} pb={4}>
          {explained.map((c) => (
            <Text key={c.key} size="xs" c="dimmed">
              <Text span size="xs" fw={700} c="bright">{c.label}</Text>
              <Text span size="xs" c="dimmed">{" — "}</Text>
              <Text span size="xs" c="dimmed">{c.hint}</Text>
            </Text>
          ))}
          <Text size="xs" c="dimmed">
            Tap a heading to sort by it. A dimmed row is a frame that was left
            out; the tick on the right is the ones being kept.
          </Text>
        </Stack>
        ) : null}
      </Collapse>
    </Stack>
  );
}
