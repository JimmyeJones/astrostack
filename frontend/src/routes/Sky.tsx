import { useMemo, useState, useEffect } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import * as THREE from "three";
import { useQuery } from "@tanstack/react-query";
import { Alert, Badge, Button, Group, Loader, Paper, Text } from "@mantine/core";
import { IconStars } from "@tabler/icons-react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
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
      <OrbitControls
        makeDefault
        enablePan={false}
        rotateSpeed={-0.35}
        zoomSpeed={0.8}
        minDistance={0.05}
        maxDistance={240}
        target={[0, 0, 0]}
      />
    </>
  );
}

export function SkyView() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<SkyImage | null>(null);
  const sky = useQuery({ queryKey: ["sky"], queryFn: api.getSky });

  return (
    <div style={{ position: "relative", height: "calc(100vh - 120px)", minHeight: 480 }}>
      <Canvas camera={{ position: [0, 0, 0.1], fov: 70, near: 0.01, far: 1000 }}>
        {sky.data ? (
          <Scene stars={sky.data.stars} images={sky.data.images} onSelect={setSelected} />
        ) : null}
      </Canvas>

      {/* Overlay UI */}
      <Paper
        withBorder p="sm" radius="md"
        style={{ position: "absolute", top: 12, left: 12, maxWidth: 320, background: "rgba(12,14,22,0.82)" }}
      >
        <Group gap={8} mb={4}>
          <IconStars size={18} />
          <Text fw={600}>Sky Map</Text>
          {sky.data ? <Badge variant="light">{sky.data.images.length} images</Badge> : null}
        </Group>
        <Text size="xs" c="dimmed">
          Drag to look around · scroll to zoom. Your stacked images are placed at
          their plate-solved positions; newer images sit on top where they overlap.
        </Text>
        {sky.isLoading ? <Group mt="xs" gap={6}><Loader size="xs" /><Text size="xs">Loading…</Text></Group> : null}
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
            RA {selected.ra_deg.toFixed(3)}° · Dec {selected.dec_deg.toFixed(3)}°
            {selected.timestamp_utc ? ` · ${selected.timestamp_utc.slice(0, 10)}` : ""}
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
