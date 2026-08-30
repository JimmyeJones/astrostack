import { useMemo, useState, useEffect } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import * as THREE from "three";
import { useQuery } from "@tanstack/react-query";
import { Alert, Badge, Button, Group, Loader, Paper, SegmentedControl, Text } from "@mantine/core";
import { IconDownload, IconStars } from "@tabler/icons-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { describeSkyCoverage } from "../components/skyCoverage";
import { formatStampDate } from "../format";
import { AladinSky } from "./AladinSky";
import {
  angularToWorld,
  orientationFor,
  raDecToVector,
  sortOldestFirst,
  type SkyImage,
  type SkyStar,
} from "../sky/projection";

const STAR_RADIUS = 100;
const IMAGE_RADIUS = 98; // just inside the stars so images sit in front

/**
 * The "where and when" line under a selected footprint's name.
 *
 * The date is the app-wide picture stamp (`formatStampDate`, a *named* month) so
 * this footprint is dated exactly as the same run is on the Gallery, History and
 * the Target hero. It used to be a raw `timestamp_utc.slice(0, 10)`, which not
 * only reads back-to-front to half the world but is the **UTC** calendar day —
 * a different day from every other surface for an evening stack west of UTC.
 * A missing or unreadable stamp drops the clause and its separator rather than
 * printing "Invalid Date" or a bare trailing " · ".
 */
export function skyFootprintLine(
  image: Pick<SkyImage, "ra_deg" | "dec_deg" | "timestamp_utc">,
): string {
  const where = `RA ${image.ra_deg.toFixed(3)}° · Dec ${image.dec_deg.toFixed(3)}°`;
  const when = formatStampDate(image.timestamp_utc);
  return when ? `${where} · ${when}` : where;
}

/** Bright-star background, split into two size buckets for a bit of depth. */
function Stars({ stars }: { stars: SkyStar[] }) {
  const { brightGeom, faintGeom } = useMemo(() => {
    const build = (subset: SkyStar[]) => {
      const pos = new Float32Array(subset.length * 3);
      const col = new Float32Array(subset.length * 3);
      subset.forEach((s, i) => {
        const v = raDecToVector(s.ra_deg, s.dec_deg, STAR_RADIUS);
        pos.set([v.x, v.y, v.z], i * 3);
        // Brighter (lower mag) → whiter; fainter → dimmer blue-white.
        const b = Math.max(0.35, Math.min(1, 1.15 - 0.18 * s.mag));
        col.set([b, b, Math.min(1, b + 0.08)], i * 3);
      });
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      g.setAttribute("color", new THREE.BufferAttribute(col, 3));
      return g;
    };
    return {
      brightGeom: build(stars.filter((s) => s.mag < 1.5)),
      faintGeom: build(stars.filter((s) => s.mag >= 1.5)),
    };
  }, [stars]);

  return (
    <group>
      <points geometry={brightGeom}>
        <pointsMaterial size={1.6} sizeAttenuation vertexColors depthWrite={false} />
      </points>
      <points geometry={faintGeom}>
        <pointsMaterial size={0.9} sizeAttenuation vertexColors depthWrite={false} />
      </points>
    </group>
  );
}

/** Labels for the most recognisable stars (kept small to avoid clutter). */
function StarLabels({ stars }: { stars: SkyStar[] }) {
  const named = useMemo(
    () => [...stars].sort((a, b) => a.mag - b.mag).slice(0, 12),
    [stars],
  );
  return (
    <>
      {named.map((s) => {
        const v = raDecToVector(s.ra_deg, s.dec_deg, STAR_RADIUS - 1);
        return (
          <Html key={s.name} position={[v.x, v.y, v.z]} center style={{ pointerEvents: "none" }}>
            <span style={{
              color: "rgba(220,228,255,0.7)", fontSize: 10, whiteSpace: "nowrap",
              textShadow: "0 0 4px #000",
            }}>
              {s.name}
            </span>
          </Html>
        );
      })}
    </>
  );
}

/** One stacked image painted on the sphere at its plate-solved position. */
function ImagePlane({
  img, renderOrder, onSelect,
}: { img: SkyImage; renderOrder: number; onSelect: (i: SkyImage) => void }) {
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  useEffect(() => {
    let alive = true;
    new THREE.TextureLoader().load(
      img.preview_url,
      (t) => { if (alive) { t.colorSpace = THREE.SRGBColorSpace; setTex(t); } },
      undefined,
      () => {}, // ignore load errors — just don't draw this one
    );
    return () => { alive = false; };
  }, [img.preview_url]);

  const { position, quaternion, w, h } = useMemo(() => {
    const v = raDecToVector(img.ra_deg, img.dec_deg, IMAGE_RADIUS);
    return {
      position: v,
      quaternion: orientationFor(img.ra_deg, img.dec_deg, img.rotation_deg),
      w: Math.max(angularToWorld(img.width_deg, IMAGE_RADIUS), 0.3),
      h: Math.max(angularToWorld(img.height_deg, IMAGE_RADIUS), 0.3),
    };
  }, [img]);

  if (!tex) return null;
  return (
    <mesh
      position={position}
      quaternion={quaternion}
      renderOrder={renderOrder}
      onClick={(e) => { e.stopPropagation(); onSelect(img); }}
    >
      <planeGeometry args={[w, h]} />
      <meshBasicMaterial
        map={tex} side={THREE.DoubleSide} transparent
        depthTest={false} depthWrite={false} toneMapped={false}
      />
    </mesh>
  );
}

/**
 * Zoom by camera field-of-view. The camera lives at the centre of the sphere,
 * so OrbitControls' dolly-zoom has nowhere useful to travel — narrowing /
 * widening the FOV gives a natural "zoom in on the sky" instead. Handles both
 * the desktop scroll-wheel and two-finger pinch on touch devices (OrbitControls
 * has zoom disabled, so two fingers are free for us). preventDefault stops the
 * page from scrolling/pinch-zooming underneath.
 */
function FovZoom({ min = 12, max = 85, step = 0.06 }: { min?: number; max?: number; step?: number }) {
  const { camera, gl } = useThree();
  useEffect(() => {
    const el = gl.domElement;
    const cam = camera as THREE.PerspectiveCamera;
    const setFov = (fov: number) => {
      cam.fov = THREE.MathUtils.clamp(fov, min, max);
      cam.updateProjectionMatrix();
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setFov(cam.fov + e.deltaY * step);
    };
    const dist = (touches: TouchList) =>
      Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);
    let lastDist = 0;
    const onTouchStart = (e: TouchEvent) => { if (e.touches.length === 2) lastDist = dist(e.touches); };
    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length !== 2) return;
      e.preventDefault();
      const d = dist(e.touches);
      if (lastDist > 0 && d > 0) setFov(cam.fov * (lastDist / d)); // pinch out → narrower FOV → zoom in
      lastDist = d;
    };
    const onTouchEnd = (e: TouchEvent) => { if (e.touches.length < 2) lastDist = 0; };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("touchstart", onTouchStart, { passive: false });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
    };
  }, [camera, gl, min, max, step]);
  return null;
}

function Scene({ stars, images, onSelect }: {
  stars: SkyStar[]; images: SkyImage[]; onSelect: (i: SkyImage) => void;
}) {
  // Oldest first → increasing renderOrder → newest drawn on top of overlaps.
  const ordered = useMemo(() => sortOldestFirst(images), [images]);
  return (
    <>
      <color attach="background" args={["#05060a"]} />
      <ambientLight intensity={1} />
      <Stars stars={stars} />
      <StarLabels stars={stars} />
      {ordered.map((img, i) => (
        <ImagePlane key={`${img.safe}-${img.run_id}`} img={img} renderOrder={i + 1} onSelect={onSelect} />
      ))}
      <FovZoom />
      <OrbitControls
        makeDefault
        enablePan={false}
        enableZoom={false}   // zoom handled by FovZoom (camera is at the centre)
        rotateSpeed={-0.35}
        target={[0, 0, 0]}
      />
    </>
  );
}

/** Self-contained Three.js viewer (bright-star backdrop, no internet). */
function OfflineSky({ stars, images, onSelect }: {
  stars: SkyStar[]; images: SkyImage[]; onSelect: (i: SkyImage) => void;
}) {
  return (
    <Canvas camera={{ position: [0, 0, 0.1], fov: 70, near: 0.01, far: 1000 }}>
      <Scene stars={stars} images={images} onSelect={onSelect} />
    </Canvas>
  );
}

/**
 * "My map" — the whole sky drawn only from the owner's own finished pictures.
 *
 * Rendered server-side (an Aitoff all-sky PNG, star background and all) because
 * the compositing needs each run's per-pixel frame-coverage map to mask a mosaic's
 * ragged fringe away, which lives beside the FITS on the server. It's a still
 * picture on purpose — "rough", in the owner's words — so this is just an <img>
 * that fills the stage; the interactive views above are what you pan and zoom.
 */
export function MyMap() {
  // "How much of the sky is that?" — the question the map itself can't answer,
  // because it's an Aitoff projection drawing every picture larger than life.
  // Measured server-side off each run's own WCS instead, so the stat can't
  // quietly disagree with the picture it sits under. Read-only and cached
  // server-side against the same "did a picture change?" fingerprint the map
  // uses, so it costs a page view nothing after the first.
  const coverage = useQuery({
    queryKey: ["sky-coverage"],
    queryFn: () => api.skyCoverage(),
    staleTime: 60_000,
  });
  const coverageLine = coverage.data
    ? describeSkyCoverage(coverage.data.deg2, coverage.data.sky_fraction,
                          coverage.data.n_pictures)
    : "";
  return (
    <div
      style={{
        position: "absolute", inset: 0, display: "flex",
        alignItems: "center", justifyContent: "center",
        background: "#0a0e1a", overflow: "auto",
      }}
    >
      <img
        src={api.myMapUrl()}
        alt="An all-sky map built from your own pictures"
        style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
      />
      {/* A map of everywhere you've been is a pride picture, and pride pictures
          get posted. A right-click or a long-press already saved it, but neither
          *invites* it and neither gives the file a name worth keeping — this is
          the same bytes the <img> is already showing, under a name that says
          what it is and when it was true. */}
      <Button
        size="compact-xs" variant="light"
        leftSection={<IconDownload size={14} />}
        component="a"
        href={api.myMapUrl()}
        download={myMapFilename()}
        style={{ position: "absolute", top: 12, right: 12 }}
      >
        Save this map
      </Button>
      {coverageLine ? (
        <Text
          size="xs" c="dimmed" ta="center"
          style={{
            position: "absolute", left: 12, right: 12, bottom: 10,
            textShadow: "0 1px 3px rgba(0,0,0,0.9)",
          }}
        >
          {coverageLine}
        </Text>
      ) : null}
    </div>
  );
}

/**
 * The filename a saved "My map" arrives under, e.g.
 * `astrostack-my-map-2026-08-29.png`.
 *
 * Dated because the map changes every time a picture does, so a folder of them
 * is a record of the sky filling up. The date is the viewer's **local** day (not
 * the UTC slice) for the same reason every other picture surface uses
 * `formatStampDate`: an evening west of UTC would otherwise be filed under
 * tomorrow.
 */
export function myMapFilename(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const day = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  return `astrostack-my-map-${day}.png`;
}

type SkyMode = "online" | "offline" | "mine";
const MODE_KEY = "astrostack.skyMode";
const SKY_MODES: readonly SkyMode[] = ["online", "offline", "mine"];

/**
 * Which map this page opens on: an explicit `?view=` wins, then the mode the
 * viewer last chose, then the real-sky atlas.
 *
 * The query parameter exists so something elsewhere can link *to* a particular
 * map — the Dashboard's sky-coverage line points at "My map", which is
 * otherwise a nav click plus a mode switch away. It is read once, as the
 * *initial* mode only, and deliberately doesn't write `MODE_KEY`: following a
 * link should show you that map without quietly rewriting the default you come
 * back to. An unknown or absent value falls through, so an old bookmark and a
 * hand-typed URL both behave.
 */
export function initialSkyMode(
  asked: string | null, stored: string | null,
): SkyMode {
  if (asked && SKY_MODES.includes(asked as SkyMode)) return asked as SkyMode;
  if (stored && SKY_MODES.includes(stored as SkyMode)) return stored as SkyMode;
  return "online";
}

export function SkyView() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<SkyImage | null>(null);
  const [params] = useSearchParams();
  const [mode, setMode] = useState<SkyMode>(
    () => initialSkyMode(params.get("view"), localStorage.getItem(MODE_KEY)),
  );
  const sky = useQuery({ queryKey: ["sky"], queryFn: api.getSky });

  const setSkyMode = (m: SkyMode) => {
    localStorage.setItem(MODE_KEY, m);
    setSelected(null);
    setMode(m);
  };

  return (
    <div style={{ position: "relative", height: "calc(100dvh - 110px)", minHeight: 420 }}>
      {mode === "mine" ? (
        <MyMap />
      ) : mode === "online" ? (
        <AladinSky images={sky.data?.images ?? []} />
      ) : sky.data ? (
        <OfflineSky stars={sky.data.stars} images={sky.data.images} onSelect={setSelected} />
      ) : null}

      {/* Overlay UI */}
      <Paper
        withBorder p="sm" radius="md"
        style={{ position: "absolute", top: 12, left: 12, maxWidth: 340, background: "rgba(12,14,22,0.82)" }}
      >
        <Group gap={8} mb={6}>
          <IconStars size={18} />
          <Text fw={600}>Sky Map</Text>
          {sky.data ? <Badge variant="light">{sky.data.images.length} images</Badge> : null}
        </Group>
        <SegmentedControl
          fullWidth size="xs" value={mode}
          onChange={(v) => setSkyMode(v as SkyMode)}
          data={[
            { label: "Real sky (online)", value: "online" },
            { label: "Stars (offline)", value: "offline" },
            { label: "My map", value: "mine" },
          ]}
        />
        <Text size="xs" c="dimmed" mt={6}>
          {mode === "mine"
            ? "The whole sky drawn from your pictures alone — nothing borrowed, no internet. Each one is masked down to the part enough frames actually reached, and shown larger than life so you can see it."
            : mode === "online"
            ? "Real-sky atlas (needs internet). Drag to pan, scroll to zoom."
            : "Built-in star map (offline). Drag to look around, scroll to zoom."}
          {mode === "mine"
            ? null
            : " Your images sit at their plate-solved positions; newest on top where they overlap."}
        </Text>
        {sky.isLoading ? <Group mt="xs" gap={6}><Loader size="xs" /><Text size="xs">Loading…</Text></Group> : null}
        {sky.isError ? (
          <Alert mt="xs" color="red" p="xs">
            <Group justify="space-between" gap="xs" wrap="nowrap">
              <Text size="xs">
                Couldn't load sky data{sky.error instanceof Error ? `: ${sky.error.message}` : "."}
              </Text>
              <Button size="compact-xs" variant="light" onClick={() => sky.refetch()}>Retry</Button>
            </Group>
          </Alert>
        ) : null}
        {sky.data && sky.data.images.length === 0 ? (
          <Alert mt="xs" color="yellow" p="xs">
            <Text size="xs">
              No stacked images yet. Stack a plate-solved target and it’ll appear here.
            </Text>
          </Alert>
        ) : null}
      </Paper>

      {selected ? (
        <Paper
          withBorder p="sm" radius="md"
          style={{ position: "absolute", bottom: 12, left: 12, maxWidth: 360, background: "rgba(12,14,22,0.9)" }}
        >
          <Group justify="space-between" mb={6}>
            <Text fw={600}>{selected.name}</Text>
            <Text size="xs" c="dimmed">
              {selected.width_deg.toFixed(2)}° × {selected.height_deg.toFixed(2)}°
            </Text>
          </Group>
          <Text size="xs" c="dimmed" mb={8}>
            {skyFootprintLine(selected)}
          </Text>
          <Group gap={8}>
            <Button size="xs" onClick={() => navigate(`/targets/${selected.safe}/history`)}>
              Open target
            </Button>
            <Button size="xs" variant="subtle" onClick={() => setSelected(null)}>Close</Button>
          </Group>
        </Paper>
      ) : null}
    </div>
  );
}
