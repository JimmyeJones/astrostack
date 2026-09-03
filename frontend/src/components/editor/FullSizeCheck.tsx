import { Button, Group, Loader, Modal, Stack, Text } from "@mantine/core";
import { IconZoomScan } from "@tabler/icons-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type Recipe } from "../../api/client";
import {
  clickFraction, loupeCaption, loupeMarkerFromWindow, loupeMarkerRect,
  loupePreviewCrop, loupeWhereText,
} from "./loupe";
import { splitClipLeft, splitFraction, splitLeftPct } from "./splitCompare";

/** What the split's left half is, said plainly. It is the preview blown up, not
 *  a second render, so it *will* look soft — and that softness is the answer to
 *  "what was the shrunk view hiding?", not a defect to apologise for. */
export const LOUPE_SPLIT_CAPTION =
  "Left of the line is the preview, blown up to the same size; right is the "
  + "real thing. The left side looks soft because that is exactly what the "
  + "shrunk preview was hiding.";

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
  // The split starts **off**: the window on its own is what the modal is for,
  // and an always-on divider would be one more thing on a surface whose standing
  // complaint is that it is too busy.
  const [split, setSplit] = useState(false);
  const [frac, setFrac] = useState(0.5);
  const dragging = useRef(false);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const windowRef = useRef<HTMLDivElement | null>(null);

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
  // The rendered window's own pixel size — the box both halves of the split are
  // drawn in, so the preview blow-up lands on the same patch at the same scale.
  const winW = window_.data?.window?.width ?? size;
  const winH = window_.data?.window?.height ?? size;
  // Null on a backend that sends no rectangle, or a degenerate crop: then no
  // comparison is offered at all, because a misaligned one is worse than none.
  const crop = window_.data ? loupePreviewCrop(window_.data.window, winW, winH) : null;
  const moveDivider = (clientX: number) => {
    const r = windowRef.current?.getBoundingClientRect();
    if (r) setFrac(splitFraction(clientX, r.left, r.width));
  };

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
                  <div
                    ref={windowRef}
                    data-testid="full-size-check-window"
                    style={{ position: "relative", width: winW, height: winH,
                             cursor: split ? "ew-resize" : undefined,
                             touchAction: split ? "none" : undefined,
                             userSelect: split ? "none" : undefined }}
                    onPointerDown={split ? (e) => {
                      dragging.current = true;
                      (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
                      moveDivider(e.clientX);
                    } : undefined}
                    onPointerMove={split
                      ? (e) => { if (dragging.current) moveDivider(e.clientX); }
                      : undefined}
                    onPointerUp={split ? () => { dragging.current = false; } : undefined}
                  >
                    <img
                      data-testid="full-size-check-image"
                      src={window_.data.url}
                      alt="A piece of your picture at full size"
                      width={winW}
                      height={winH}
                      style={{ display: "block" }} />
                    {/* The same patch, taken from the preview and blown up — a
                        plain CSS transform of the navigator image beside it, not
                        a second render. Clipped to the left of the divider so the
                        real render below shows through on the right. */}
                    {split && crop ? (
                      <>
                        <div data-testid="full-size-check-split-before"
                          style={{ position: "absolute", inset: 0,
                                   overflow: "hidden", pointerEvents: "none",
                                   clipPath: splitClipLeft(frac) }}>
                          <img src={api.editPreviewUrl(safe, runId, recipe)}
                            alt="The same piece as the preview shows it"
                            style={{ position: "absolute",
                                     left: crop.left, top: crop.top,
                                     width: crop.width, height: crop.height,
                                     maxWidth: "none", display: "block" }} />
                        </div>
                        <div data-testid="full-size-check-split-divider"
                          style={{ position: "absolute", top: 0, bottom: 0,
                                   left: splitLeftPct(frac), width: 2,
                                   marginLeft: -1, pointerEvents: "none",
                                   background: "rgba(255,255,255,0.9)",
                                   boxShadow: "0 0 4px rgba(0,0,0,0.8)" }} />
                      </>
                    ) : null}
                  </div>
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
              {/* "…and how different is that from what I've been looking at?" —
                  the question a beginner asks straight after "what will I get?".
                  Offered only when the two halves can actually be lined up. */}
              {crop ? (
                <Group gap={6} wrap="nowrap" align="center">
                  <Button size="compact-xs" variant="subtle" color="grape"
                    data-testid="full-size-check-split-toggle"
                    onClick={() => setSplit((s) => !s)}>
                    {split ? "Hide the preview comparison"
                      : "Compare with the preview"}
                  </Button>
                </Group>
              ) : null}
              {split && crop ? (
                <Text size="xs" c="dimmed" data-testid="full-size-check-split-caption">
                  {LOUPE_SPLIT_CAPTION}
                </Text>
              ) : null}
            </Stack>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
