import { Button, Group, Modal, Stack, Text } from "@mantine/core";
import { IconZoomScan } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, type Recipe } from "../../api/client";
import { clickFraction, loupeCaption, loupeMarkerRect } from "./loupe";

/**
 * "Check it at full size" — one window of the picture rendered at 1:1.
 *
 * The live preview is a decimated proxy of what may be a 150 MP mosaic, and four
 * controls beside it carry an advisory saying so: deconvolution understates,
 * sharpening understates, star reduction differs, hot-pixel removal is skipped.
 * All four are honest, and all four leave a beginner with a slider they cannot
 * set by eye. This is the answer instead of the apology — and it is only an
 * answer because the ops that measure the *whole* picture (the stretch, the
 * colour balance, the sky model) are handed what they measured there rather than
 * re-measuring on the window, so the piece you inspect really is a piece of the
 * picture you were looking at.
 *
 * **Self-hiding.** On a stack small enough that the preview already shows every
 * pixel, or a recipe whose geometry makes "which part of the picture is this?"
 * unanswerable, it renders nothing at all — the editor's standing complaint is
 * that it is too busy, so a control that cannot act does not take a line.
 */
export function FullSizeCheck({
  safe, runId, recipe, shownSourceW, shownSourceH,
}: {
  safe: string;
  runId: number;
  recipe: Recipe;
  /** What the rendered preview covers, in source pixels (`render_width × proxy_scale`). */
  shownSourceW?: number | null;
  shownSourceH?: number | null;
}) {
  const [open, setOpen] = useState(false);
  const [spot, setSpot] = useState({ fx: 0.5, fy: 0.5 });
  const boxRef = useRef<HTMLDivElement | null>(null);

  const info = useQuery({
    queryKey: ["loupe-info", safe, runId, JSON.stringify(recipe)],
    queryFn: () => api.loupeInfo(safe, runId, recipe),
    staleTime: 30_000,
    retry: false,
  });

  if (!info.data?.available) return null;
  const size = info.data.size_px;
  const marker = loupeMarkerRect(spot.fx, spot.fy, size, shownSourceW, shownSourceH);

  return (
    <>
      <Group gap={6} wrap="nowrap" align="center" mt={4}>
        <IconZoomScan size={14} color="var(--mantine-color-dimmed)"
          style={{ flexShrink: 0 }} />
        <Button size="compact-xs" variant="subtle" color="grape"
          data-testid="full-size-check-open"
          onClick={() => setOpen(true)}>
          Check it at full size
        </Button>
      </Group>

      <Modal opened={open} onClose={() => setOpen(false)} size="auto"
        title="Your picture at full size">
        <Stack gap="sm">
          <Text size="sm" c="dimmed">{loupeCaption(size, info.data.proxy_scale)}</Text>
          <Group align="flex-start" gap="md" wrap="wrap">
            {/* The navigator: the same preview, with the window marked. Clicking
                moves the window — the only control this needs, and the picture
                itself is the label for it. */}
            <Stack gap={4}>
              <Text size="xs" c="dimmed">Tap to look somewhere else</Text>
              <div ref={boxRef}
                data-testid="full-size-check-navigator"
                role="button"
                tabIndex={0}
                aria-label="Choose which part of the picture to see at full size"
                onClick={(e) => {
                  const r = boxRef.current?.getBoundingClientRect();
                  if (r) setSpot(clickFraction(e.clientX, e.clientY, r));
                }}
                style={{ position: "relative", width: 240, background: "#000",
                         borderRadius: 6, overflow: "hidden", cursor: "crosshair" }}>
                <img src={api.editPreviewUrl(safe, runId, recipe)} alt="preview"
                  style={{ display: "block", width: "100%", height: "auto" }} />
                {marker ? (
                  <div data-testid="full-size-check-marker"
                    style={{ position: "absolute", left: `${marker.left}%`,
                             top: `${marker.top}%`, width: `${marker.width}%`,
                             height: `${marker.height}%`, pointerEvents: "none",
                             border: "2px solid rgba(255,255,255,0.9)",
                             boxShadow: "0 0 4px rgba(0,0,0,0.8)" }} />
                ) : null}
              </div>
            </Stack>
            {/* The window itself, at its natural size — scaling it would defeat
                the whole point, so it scrolls rather than shrinks on a phone. */}
            <div style={{ maxWidth: "100%", overflow: "auto", background: "#000",
                          borderRadius: 6 }}>
              <img
                data-testid="full-size-check-image"
                src={api.editLoupeUrl(safe, runId, recipe, spot.fx, spot.fy, size)}
                alt="A piece of your picture at full size"
                width={size} height={size}
                style={{ display: "block" }} />
            </div>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
