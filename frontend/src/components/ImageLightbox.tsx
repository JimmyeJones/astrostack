import { useCallback, useEffect, useRef, useState } from "react";
import { ActionIcon, Group, Menu, Modal, Text, Tooltip } from "@mantine/core";
import {
  IconArrowsMaximize, IconDatabase, IconPhotoDown, IconZoomIn, IconZoomOut,
} from "@tabler/icons-react";

interface Transform {
  scale: number;
  tx: number;
  ty: number;
}

const RESET: Transform = { scale: 1, tx: 0, ty: 0 };
const MIN_SCALE = 1;
const MAX_SCALE = 12;

const clampScale = (s: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

/**
 * Pure pinch math (extracted so it's unit-testable without DOM pointer events).
 * Scales by the ratio of current/initial finger distance and translates so the
 * image point that was under the initial pinch midpoint stays under the current
 * midpoint. All coordinates are relative to the surface centre (transform
 * origin). `imgX/imgY` are that fixed point in image space.
 */
export function computePinch(
  startScale: number, startDist: number, curDist: number,
  midX: number, midY: number, imgX: number, imgY: number,
): Transform {
  const scale = clampScale(startScale * (curDist / (startDist || 1)));
  if (scale <= MIN_SCALE) return { scale, tx: 0, ty: 0 };
  return { scale, tx: midX - imgX * scale, ty: midY - imgY * scale };
}

/**
 * Fullscreen image viewer for inspecting stacked images up close.
 *
 * Desktop: scroll to zoom (toward the cursor), drag to pan, double-click to
 * toggle. Touch: pinch to zoom, one finger to pan. Pure DOM transforms — no
 * extra dependencies.
 *
 * Implementation notes (both learned the hard way):
 *  - State updaters must be PURE: never read a mutable ref inside a setState
 *    updater. A move + release can both fire before React flushes, so a lazily
 *    run updater that dereferenced a gesture ref crashed once release had
 *    nulled it. We capture values before calling setState.
 *  - The wheel listener is bound through a CALLBACK REF, not an effect, because
 *    Mantine mounts the Modal body through a portal with a transition and an
 *    effect keyed on `src` couldn't reliably find the node.
 */
export function ImageLightbox({
  src, title, downloadHref, jpegHref, rawHref, onClose,
}: {
  src: string | null;
  title?: string;
  /** The picture being shown (a shareable PNG) — the download the viewer
   * most likely wants: what they're looking at, not a 100 MB scientific file. */
  downloadHref?: string;
  /** Optional JPEG of the same picture (smaller — best for sharing). When given
   * alongside `downloadHref`, the picture-download control becomes a small menu
   * offering PNG or JPEG; when absent it stays a single PNG download. */
  jpegHref?: string;
  /** Optional secondary download for the raw scientific data (FITS), offered
   * next to the picture download so power users keep access to it. */
  rawHref?: string;
  onClose: () => void;
}) {
  const [t, setT] = useState<Transform>(RESET);
  const [dragging, setDragging] = useState(false);
  const surfaceRef = useRef<HTMLDivElement | null>(null);
  const wheelCleanup = useRef<(() => void) | null>(null);

  // Active pointers (touch/mouse) by id, plus the in-flight gesture state.
  const pointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const pan = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const pinch = useRef<
    { startDist: number; startScale: number; imgX: number; imgY: number } | null
  >(null);

  // Reset view whenever a new image is opened (or it closes).
  useEffect(() => {
    setT(RESET);
    setDragging(false);
    pointers.current.clear();
    pan.current = null;
    pinch.current = null;
  }, [src]);

  /** Cursor position relative to the surface centre (the transform origin). */
  const toLocal = (clientX: number, clientY: number) => {
    const rect = surfaceRef.current!.getBoundingClientRect();
    return [clientX - rect.left - rect.width / 2, clientY - rect.top - rect.height / 2] as const;
  };

  const zoomAt = useCallback((clientX: number, clientY: number, factor: number) => {
    const el = surfaceRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const cx = clientX - rect.left - rect.width / 2;
    const cy = clientY - rect.top - rect.height / 2;
    setT((prev) => {
      const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev.scale * factor));
      if (scale === prev.scale) return prev;
      const k = scale / prev.scale;
      // Keep the point under the cursor fixed as we scale.
      let tx = cx - (cx - prev.tx) * k;
      let ty = cy - (cy - prev.ty) * k;
      if (scale <= MIN_SCALE) { tx = 0; ty = 0; }
      return { scale, tx, ty };
    });
  }, []);

  // Callback ref: bind a non-passive wheel listener the moment the surface
  // mounts (and unbind when it unmounts). `zoomAt` is stable so this ref is
  // stable across normal re-renders — the listener isn't churned.
  const attachSurface = useCallback((node: HTMLDivElement | null) => {
    if (wheelCleanup.current) { wheelCleanup.current(); wheelCleanup.current = null; }
    surfaceRef.current = node;
    if (node) {
      const onWheel = (e: WheelEvent) => {
        e.preventDefault();
        e.stopPropagation();
        zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.2 : 1 / 1.2);
      };
      node.addEventListener("wheel", onWheel, { passive: false });
      wheelCleanup.current = () => node.removeEventListener("wheel", onWheel);
    }
  }, [zoomAt]);

  /** Begin (or restart) a one-pointer pan from the current transform. */
  const startPan = (clientX: number, clientY: number, cur: Transform) => {
    pan.current = { x: clientX, y: clientY, tx: cur.tx, ty: cur.ty };
  };

  /** Begin a two-pointer pinch from the current transform. */
  const startPinch = (cur: Transform) => {
    const pts = [...pointers.current.values()];
    if (pts.length < 2) return;
    const [a, b] = pts;
    const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1;
    const [mx, my] = toLocal((a.x + b.x) / 2, (a.y + b.y) / 2);
    pinch.current = {
      startDist: dist,
      startScale: cur.scale,
      // Image-space point currently under the pinch midpoint — kept fixed.
      imgX: (mx - cur.tx) / cur.scale,
      imgY: (my - cur.ty) / cur.scale,
    };
    pan.current = null;
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    e.currentTarget.setPointerCapture?.(e.pointerId);
    if (pointers.current.size >= 2) {
      setDragging(true);
      startPinch(t);
    } else if (t.scale > MIN_SCALE) {
      setDragging(true);
      startPan(e.clientX, e.clientY, t);
    }
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const tracked = pointers.current.get(e.pointerId);
    if (!tracked) return;
    tracked.x = e.clientX;
    tracked.y = e.clientY;

    if (pinch.current && pointers.current.size >= 2) {
      const [a, b] = [...pointers.current.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      const [mx, my] = toLocal((a.x + b.x) / 2, (a.y + b.y) / 2);
      const pc = pinch.current;
      setT(computePinch(pc.startScale, pc.startDist, dist, mx, my, pc.imgX, pc.imgY));
      return;
    }

    const p = pan.current;
    if (!p) return;
    // Capture values OUTSIDE the updater so it stays pure (see note above).
    const tx = p.tx + (e.clientX - p.x);
    const ty = p.ty + (e.clientY - p.y);
    setT((prev) => ({ ...prev, tx, ty }));
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    pointers.current.delete(e.pointerId);
    pinch.current = null;
    if (pointers.current.size === 1 && t.scale > MIN_SCALE) {
      // Dropped from pinch to a single finger — keep panning from where it is.
      const [only] = [...pointers.current.values()];
      startPan(only.x, only.y, t);
    } else if (pointers.current.size === 0) {
      pan.current = null;
      setDragging(false);
    }
  };

  const onDoubleClick = (e: React.MouseEvent) => {
    if (t.scale > MIN_SCALE) setT(RESET);
    else zoomAt(e.clientX, e.clientY, 3);
  };

  const zoomed = t.scale > MIN_SCALE;
  const center = () => [window.innerWidth / 2, window.innerHeight / 2] as const;

  return (
    <Modal
      opened={src != null}
      onClose={onClose}
      fullScreen
      withCloseButton={false}
      padding={0}
      transitionProps={{ transition: "fade", duration: 120 }}
      styles={{ body: { height: "100dvh", background: "#000" } }}
    >
      <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}>
        {/* Toolbar */}
        <Group
          gap={4}
          wrap="nowrap"
          style={{
            position: "absolute", top: 10, right: 10, zIndex: 5,
            background: "rgba(12,14,22,0.72)", borderRadius: 8, padding: "4px 6px",
          }}
        >
          {title ? (
            <Text size="sm" c="gray.3" mr={4} maw={180} truncate visibleFrom="xs">{title}</Text>
          ) : null}
          <Text size="xs" c="dimmed" w={42} ta="right">{Math.round(t.scale * 100)}%</Text>
          <Tooltip label="Zoom in"><ActionIcon size="lg" variant="subtle" color="gray"
            onClick={() => zoomAt(...center(), 1.4)} aria-label="Zoom in">
            <IconZoomIn size={20} /></ActionIcon></Tooltip>
          <Tooltip label="Zoom out"><ActionIcon size="lg" variant="subtle" color="gray"
            onClick={() => zoomAt(...center(), 1 / 1.4)} aria-label="Zoom out">
            <IconZoomOut size={20} /></ActionIcon></Tooltip>
          <Tooltip label="Reset"><ActionIcon size="lg" variant="subtle" color="gray"
            onClick={() => setT(RESET)} aria-label="Reset zoom">
            <IconArrowsMaximize size={20} /></ActionIcon></Tooltip>
          {downloadHref && jpegHref ? (
            <Menu shadow="md" position="bottom-end" withinPortal>
              <Menu.Target>
                <Tooltip label="Download picture"><ActionIcon size="lg" variant="subtle" color="gray"
                  aria-label="Download picture"><IconPhotoDown size={20} /></ActionIcon></Tooltip>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item component="a" href={downloadHref}>PNG (best quality)</Menu.Item>
                <Menu.Item component="a" href={jpegHref}>JPEG (smaller — best for sharing)</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          ) : downloadHref ? (
            <Tooltip label="Download picture (PNG)"><ActionIcon size="lg" variant="subtle" color="gray"
              component="a" href={downloadHref} aria-label="Download picture"><IconPhotoDown size={20} /></ActionIcon></Tooltip>
          ) : null}
          {rawHref ? (
            <Tooltip label="Download raw data (FITS)"><ActionIcon size="lg" variant="subtle" color="gray"
              component="a" href={rawHref} aria-label="Download raw data"><IconDatabase size={20} /></ActionIcon></Tooltip>
          ) : null}
          <ActionIcon size="lg" variant="subtle" color="gray" onClick={onClose} aria-label="Close">✕</ActionIcon>
        </Group>

        {/* Zoom/pan surface */}
        <div
          ref={attachSurface}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onDoubleClick={onDoubleClick}
          style={{
            width: "100%", height: "100%", display: "flex",
            alignItems: "center", justifyContent: "center",
            cursor: zoomed ? (dragging ? "grabbing" : "grab") : "zoom-in",
            touchAction: "none",
          }}
        >
          {src ? (
            <img
              src={src}
              alt={title ?? "stacked image"}
              draggable={false}
              style={{
                maxWidth: "100%", maxHeight: "100%", objectFit: "contain",
                transform: `translate(${t.tx}px, ${t.ty}px) scale(${t.scale})`,
                transformOrigin: "center center",
                transition: dragging ? "none" : "transform 80ms ease-out",
                willChange: "transform", userSelect: "none",
              }}
            />
          ) : null}
        </div>

        <Text
          size="xs" c="dimmed"
          style={{ position: "absolute", bottom: 10, left: 0, right: 0, textAlign: "center" }}
        >
          Scroll or pinch to zoom · drag to pan · double-tap to reset · Esc to close
        </Text>
      </div>
    </Modal>
  );
}
