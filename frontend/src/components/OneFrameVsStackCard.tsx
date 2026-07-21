import { useRef, useState } from "react";
import { Box, Button, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconArrowsHorizontal, IconPhoto } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { splitClipLeft, splitFraction, splitLeftPct } from "./editor/splitCompare";
import { oneFrameCaption } from "./oneFrameVsStack";

/**
 * "One frame vs your stack" — a read-only reveal that puts a single noisy raw
 * sub next to the finished stack under a draggable split divider, so a beginner
 * *sees* (and can share) exactly what stacking bought them: the noise floor
 * drops and faint detail appears out of the grain.
 *
 * The single sub is auto-picked (the sharpest accepted frame) and stretched with
 * the *same* export autostretch as the stack preview, so the only visible
 * difference is noise/detail, not brightness — an honest before/after.
 *
 * Renders **nothing** unless the run has a stored preview to compare against and
 * a frame to render (`available: false`, not an error), so it never nags an
 * older/edited run. Starts collapsed (one button) so History's list of runs
 * doesn't fetch every sub up front; the images load only once the user reveals.
 */
export function OneFrameVsStackCard({
  safe,
  runId,
}: {
  safe: string;
  runId: number;
}) {
  const [revealed, setRevealed] = useState(false);
  const [frac, setFrac] = useState(0.5);
  const dragging = useRef(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  const info = useQuery({
    queryKey: ["one-sub-vs-stack", safe, runId],
    queryFn: () => api.oneSubVsStack(safe, runId),
    enabled: !!safe,
  });
  if (!info.data?.available) return null;

  const subSrc = api.stackReferenceSubUrl(safe, runId);
  const stackSrc = api.stackArtifactUrl(safe, runId, "preview");
  const caption = oneFrameCaption(info.data.sub_exposure_s, info.data.n_frames);

  const moveTo = (clientX: number) => {
    const rect = boxRef.current?.getBoundingClientRect();
    if (!rect) return;
    setFrac(splitFraction(clientX, rect.left, rect.width));
  };

  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="teal"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconArrowsHorizontal size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>One frame vs your stack</Text>
          <Text size="xs" c="dimmed">{caption}</Text>
          {revealed ? (
            <Box
              ref={boxRef}
              onPointerDown={(e) => {
                dragging.current = true;
                (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
                moveTo(e.clientX);
              }}
              onPointerMove={(e) => { if (dragging.current) moveTo(e.clientX); }}
              onPointerUp={() => { dragging.current = false; }}
              style={{
                position: "relative", width: "100%", maxHeight: 420,
                overflow: "hidden", borderRadius: 6, cursor: "ew-resize",
                touchAction: "none", userSelect: "none",
              }}
            >
              {/* Base (right of divider): the finished stack. */}
              <img src={stackSrc} alt="Your finished stack"
                draggable={false}
                style={{ display: "block", width: "100%", maxHeight: 420,
                  objectFit: "contain" }} />
              {/* Overlay (left of divider): the single raw sub, clipped. */}
              <img src={subSrc} alt="A single raw sub"
                draggable={false}
                style={{
                  position: "absolute", inset: 0, width: "100%", height: "100%",
                  objectFit: "contain", clipPath: splitClipLeft(frac),
                }} />
              {/* Divider. */}
              <Box style={{
                position: "absolute", top: 0, bottom: 0, left: splitLeftPct(frac),
                width: 2, background: "var(--mantine-color-teal-4)",
                transform: "translateX(-1px)", pointerEvents: "none",
              }} />
              <Text size="xs" fw={600} style={{
                position: "absolute", top: 6, left: 8, color: "white",
                textShadow: "0 1px 3px rgba(0,0,0,0.9)", pointerEvents: "none",
              }}>One sub</Text>
              <Text size="xs" fw={600} style={{
                position: "absolute", top: 6, right: 8, color: "white",
                textShadow: "0 1px 3px rgba(0,0,0,0.9)", pointerEvents: "none",
              }}>Your stack</Text>
            </Box>
          ) : (
            <Group gap="xs">
              <Button size="xs" variant="light" color="teal"
                leftSection={<IconPhoto size={14} />}
                onClick={() => setRevealed(true)}>
                See the difference
              </Button>
            </Group>
          )}
        </Stack>
      </Group>
    </Paper>
  );
}
