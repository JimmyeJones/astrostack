import { Button, Group, Loader, Modal, Stack, Text } from "@mantine/core";
import { IconZoomScan } from "@tabler/icons-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type Recipe } from "../../api/client";
import {
  clickFraction, loupeCaption, loupeMarkerFromWindow, loupeMarkerRect, loupeWhereText,
} from "./loupe";

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
 *
 * **Why the window is fetched rather than hung off an `<img src>`.** The server
 * answers "which part of the picture did I actually cut?" in the response's
 * `X-Loupe-Window` header, and that answer is the only authoritative one: the
 * browser reports a fraction of the *preview*, which the recipe's crop maps
 * somewhere it cannot compute. Reading a header means reading the response, so
 * this uses the same blob-URL query shape the live preview does — including its
 * `gcTime: 0`, without which an undo/redo back to a prior recipe could re-serve
 * an already-revoked URL and blank the window.
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

  const size = info.data?.size_px ?? 0;
  const window_ = useQuery({
    queryKey: ["loupe-png", safe, runId, JSON.stringify(recipe), spot.fx, spot.fy, size],
    // Only once the modal is open: this is a real full-resolution render, never
    // something to fire off behind a button nobody pressed.
    enabled: open && size > 0,
    gcTime: 0,
    placeholderData: keepPreviousData,
    retry: false,
    queryFn: ({ signal }) =>
      api.fetchLoupe(safe, runId, recipe, spot.fx, spot.fy, size, signal),
  });
  useEffect(() => {
    const url = window_.data?.url;
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [window_.data?.url]);

  if (!info.data?.available) return null;
  // The server's own rectangle when it has answered; the client-side guide while
  // the render is in flight, and on a backend that doesn't send one.
  const marker = loupeMarkerFromWindow(window_.data?.window)
    ?? loupeMarkerRect(spot.fx, spot.fy, size, shownSourceW, shownSourceH);
  const where = loupeWhereText(window_.data?.window);

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
            <Stack gap={4}>
              <div style={{ maxWidth: "100%", overflow: "auto", background: "#000",
                            borderRadius: 6, minWidth: 120, minHeight: 40 }}>
                {window_.data ? (
                  <img
                    data-testid="full-size-check-image"
                    src={window_.data.url}
                    alt="A piece of your picture at full size"
                    width={window_.data.window?.width ?? size}
                    height={window_.data.window?.height ?? size}
                    style={{ display: "block" }} />
                ) : window_.isError ? (
                  <Text size="sm" c="red" p="sm" data-testid="full-size-check-error">
                    That window couldn&rsquo;t be rendered:{" "}
                    {(window_.error as Error)?.message ?? "unknown error"}
                  </Text>
                ) : (
                  <Group justify="center" p="lg"><Loader size="sm" /></Group>
                )}
              </div>
              {/* Where it is, named against the whole canvas — the frame the
                  reader thinks in, and the one the marker beside it is not. */}
              {where ? (
                <Text size="xs" c="dimmed" data-testid="full-size-check-where">
                  {where}
                </Text>
              ) : null}
            </Stack>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
