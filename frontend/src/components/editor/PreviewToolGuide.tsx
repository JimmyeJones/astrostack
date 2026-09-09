import { Anchor, Collapse, Stack, Text } from "@mantine/core";
import { useState } from "react";
import type { PreviewTool } from "./previewTools";

/**
 * "What do these buttons do?" — the preview toolbar, explained in text a phone
 * can actually show.
 *
 * The row directly under the picture is where the editor is *used*: it is how
 * you look at the coverage map, the star mask, the crop handles and the
 * before/after split. Four of those buttons carried a good plain-language
 * sentence each — but only as a `Tooltip`, which opens on hover or focus. A
 * phone has no hover, and a tap on one of these buttons runs it, so on the
 * device the owner reads this app on there was no way to ask what any of them
 * meant: the one gesture available spends the question on the answer.
 *
 * Deliberately a **disclosure, not a legend** (the `FrameColumnGuide` shape):
 * the standing complaint about this app is that its pages are too tall, so this
 * costs one line until it is asked for, and the tooltips are left exactly as
 * they are for anyone with a mouse. The wording is not new — it is the same
 * `hint` strings the tooltips use, from the same array, so the two cannot drift.
 */
export function PreviewToolGuide({ tools }: { tools: PreviewTool[] }) {
  const [open, setOpen] = useState(false);
  if (!tools.length) return null;

  return (
    <Stack gap={4} mt={4}>
      <Anchor
        component="button"
        type="button"
        size="xs"
        fw={500}
        data-testid="preview-tool-guide-toggle"
        style={{ alignSelf: "flex-end" }}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "Hide what these buttons do" : "What do these buttons do? →"}
      </Anchor>
      {/* Mounted only while open, deliberately: it is static text with nothing
          to fetch, and the words it puts on the page ("mask", "heatmap") are
          ones the editor is otherwise careful about saying unprompted. */}
      <Collapse in={open}>
        {open ? (
          <Stack gap={6} pl={4} pb={4}>
            {tools.map((t) => (
              <Text key={t.key} size="xs" c="dimmed">
                <Text span size="xs" fw={700} c="bright">{t.label}</Text>
                <Text span size="xs" c="dimmed">{" — "}</Text>
                <Text span size="xs" c="dimmed">{t.hint}</Text>
              </Text>
            ))}
          </Stack>
        ) : null}
      </Collapse>
    </Stack>
  );
}
