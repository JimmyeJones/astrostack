import { useCallback, useEffect, useRef, useState } from "react";
import { ActionIcon, Group, Modal, Text, Tooltip } from "@mantine/core";
import {
  IconArrowsMaximize, IconDownload, IconZoomIn, IconZoomOut,
} from "@tabler/icons-react";

interface Transform {
  scale: number;
  tx: number;
  ty: number;
}

const RESET: Transform = { scale: 1, tx: 0, ty: 0 };
const MIN_SCALE = 1;
const MAX_SCALE = 12;

/**
 * Fullscreen image viewer with scroll-to-zoom (toward the cursor) and
 * drag-to-pan. Used to inspect stacked images up close. Pure DOM transforms —
 * no extra dependencies. Double-click toggles fit ⇄ zoomed at the cursor.
 *
 * Implementation notes (both learned the hard way):
 *  - State updaters must be PURE: never read a mutable ref inside a setState
 *    updater. A pointermove + pointerup can both fire before React flushes, so
 *    a lazily-run updater that dereferenced `drag.current` crashed once the
 *    pointerup had nulled it. We capture values before calling setState.
 *  - The wheel listener is bound through a CALLBACK REF, not an effect. Mantine
 *    mounts the Modal body through a portal with a transition, so an effect
 *    keyed on `src` couldn't reliably find the node; a callback ref binds the
 *    non-passive listener exactly when the surface element mounts.
 */
export function ImageLightbox({
  src, title, downloadHref, onClose,
}: {
  src: string | null;
  title?: string;
  downloadHref?: string;
  onClose: () => void;
}) {
  const [t, setT] = useState<Transform>(RESET);
  const [dragging, setDragging] = useState(false);
  const surfaceRef = useRef<HTMLDivElement | null>(null);
  const wheelCleanup = useRef<(() => void) | null>(null);
  const drag = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);

  // Reset view whenever a new image is opened (or it closes).
  useEffect(() => {
    setT(RESET);
    setDragging(false);
    drag.current = null;
  }, [src]);

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

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (t.scale <= MIN_SCALE) return;
    drag.current = { x: e.clientX, y: e.clientY, tx: t.tx, ty: t.ty };
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    // Capture values OUTSIDE the updater so it stays pure (see note above).
    const tx = d.tx + (e.clientX - d.x);
    const ty = d.ty + (e.clientY - d.y);
    setT((prev) => ({ ...prev, tx, ty }));
  };
  const onPointerUp = () => {
    drag.current = null;
    setDragging(false);
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
      styles={{ body: { height: "100vh", background: "#000" } }}
    >
      <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden" }}>
        {/* Toolbar */}
        <Group
          gap="xs"
          style={{
            position: "absolute", top: 12, right: 12, zIndex: 5,
            background: "rgba(12,14,22,0.7)", borderRadius: 8, padding: "4px 8px",
          }}
        >
          {title ? <Text size="sm" c="gray.3" mr={4} maw={360} truncate>{title}</Text> : null}
          <Text size="xs" c="dimmed" w={42} ta="right">{Math.round(t.scale * 100)}%</Text>
          <Tooltip label="Zoom in"><ActionIcon variant="subtle" color="gray"
            onClick={() => zoomAt(...center(), 1.4)}>
            <IconZoomIn size={18} /></ActionIcon></Tooltip>
          <Tooltip label="Zoom out"><ActionIcon variant="subtle" color="gray"
            onClick={() => zoomAt(...center(), 1 / 1.4)}>
            <IconZoomOut size={18} /></ActionIcon></Tooltip>
          <Tooltip label="Reset"><ActionIcon variant="subtle" color="gray" onClick={() => setT(RESET)}>
            <IconArrowsMaximize size={18} /></ActionIcon></Tooltip>
          {downloadHref ? (
            <Tooltip label="Download"><ActionIcon variant="subtle" color="gray"
              component="a" href={downloadHref}><IconDownload size={18} /></ActionIcon></Tooltip>
          ) : null}
          <ActionIcon variant="subtle" color="gray" onClick={onClose} aria-label="Close">✕</ActionIcon>
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
          Scroll to zoom · drag to pan · double-click to toggle · Esc to close
        </Text>
      </div>
    </Modal>
  );
}
