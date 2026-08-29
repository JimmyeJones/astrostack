import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Billboard, Html, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useQuery } from "@tanstack/react-query";
import {
  Alert, Anchor, Badge, Button, Group, Loader, Paper, ScrollArea, Text,
} from "@mantine/core";
import { IconGalaxy } from "@tabler/icons-react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { raDecToVector, type SkyImage, type SkyStar } from "../sky/projection";
import {
  radiusForDepth, scaleCaption, spanSummary, withPictures,
  type PlacedPicture, type UniverseData, type UniverseObject,
} from "../sky/universe";

/** Far enough behind everything that it reads as "the rest of the sky". */
const BACKDROP_RADIUS = 420;
/** World size of a picture in the scene. Distance is the radial axis here, so a
 *  picture's *drawn* size carries no meaning and is kept constant on purpose —
 *  scaling it by angular size would quietly imply a second, false dimension. */
const PICTURE_SIZE = 9;

/** The bright-star sky, painted far outside the scene as a backdrop. */
function Backdrop({ stars }: { stars: SkyStar[] }) {
  const geom = useMemo(() => {
    const pos = new Float32Array(stars.length * 3);
    stars.forEach((s, i) => {
      const v = raDecToVector(s.ra_deg, s.dec_deg, BACKDROP_RADIUS);
      pos.set([v.x, v.y, v.z], i * 3);
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return g;
  }, [stars]);
  return (
    <points geometry={geom}>
      <pointsMaterial size={2.2} color="#9fb0d8" sizeAttenuation={false}
        depthWrite={false} transparent opacity={0.5} />
    </points>
  );
}

/**
 * One labelled distance ring — the map's scale reference.
 *
 * Drawn as a circle in the equatorial plane rather than a wireframe sphere: a
 * sphere at every rung would fill the scene with mesh and hide the objects the
 * rings exist to measure.
 */
function DistanceRing({ radius, label }: { radius: number; label: string }) {
  const points = useMemo(() => {
    const pts: [number, number, number][] = [];
    for (let i = 0; i <= 96; i++) {
      const a = (i / 96) * Math.PI * 2;
      pts.push([radius * Math.cos(a), 0, radius * Math.sin(a)]);
    }
    return pts;
  }, [radius]);
  // Ride the label around to whichever point of the ring faces the camera. A
  // label pinned to a fixed world point drifts off the canvas as the scene turns
  // — on a phone the outermost ring's label was already clipped on arrival — and
  // an unlabelled ring is just a circle.
  const labelAt = useRef<THREE.Group>(null);
  useFrame(({ camera }) => {
    const g = labelAt.current;
    if (!g) return;
    const len = Math.hypot(camera.position.x, camera.position.z) || 1;
    g.position.set(
      (camera.position.x / len) * radius, 0, (camera.position.z / len) * radius);
  });
  return (
    <group>
      <Line points={points} color="#3b4668" lineWidth={1} transparent opacity={0.75} />
      <group ref={labelAt} position={[radius, 0, 0]}>
        <Html center style={{ pointerEvents: "none" }}>
          <span style={{
            color: "rgba(180,195,235,0.75)", fontSize: 10, whiteSpace: "nowrap",
            textShadow: "0 0 4px #000",
          }}>
            {label}
          </span>
        </Html>
      </group>
    </group>
  );
}

/** "You are here" — the origin every distance on this map is measured from. */
function Home() {
  return (
    <group>
      <mesh>
        <sphereGeometry args={[1.1, 16, 16]} />
        <meshBasicMaterial color="#8fd3ff" />
      </mesh>
      <Html position={[0, -3, 0]} center style={{ pointerEvents: "none" }}>
        <span style={{
          color: "rgba(200,225,255,0.8)", fontSize: 10, whiteSpace: "nowrap",
          textShadow: "0 0 4px #000",
        }}>
          You are here
        </span>
      </Html>
    </group>
  );
}

/**
 * One captured object at its real depth: the owner's own picture of it when
 * there is one, a plain marker when there isn't.
 *
 * The radial line back to the origin is what makes depth readable at all — on a
 * perspective camera a lone point in space is ambiguous between "small and near"
 * and "big and far", and the line resolves it.
 */
function ObjectNode({ placed, selected, onSelect }: {
  placed: PlacedPicture;
  selected: boolean;
  onSelect: (o: UniverseObject) => void;
}) {
  const { object, image } = placed;
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  useEffect(() => {
    if (!image) return;
    let alive = true;
    new THREE.TextureLoader().load(
      image.preview_url,
      (t) => { if (alive) { t.colorSpace = THREE.SRGBColorSpace; setTex(t); } },
      undefined,
      () => {}, // a picture that won't load just falls back to the marker
    );
    return () => { alive = false; };
  }, [image]);

  const position = useMemo(
    () => raDecToVector(object.ra_deg, object.dec_deg, radiusForDepth(object.depth)),
    [object.ra_deg, object.dec_deg, object.depth],
  );
  const aspect = image && image.width_deg > 0
    ? Math.max(0.25, Math.min(4, image.height_deg / image.width_deg))
    : 1;

  return (
    <group>
      <Line
        points={[[0, 0, 0], [position.x, position.y, position.z]]}
        color={selected ? "#c39bff" : "#2b3350"}
        lineWidth={1}
        transparent
        opacity={selected ? 0.9 : 0.5}
      />
      <Billboard position={position}>
        {tex ? (
          <mesh onClick={(e) => { e.stopPropagation(); onSelect(object); }}>
            <planeGeometry args={[PICTURE_SIZE, PICTURE_SIZE * aspect]} />
            <meshBasicMaterial map={tex} side={THREE.DoubleSide} transparent toneMapped={false} />
          </mesh>
        ) : (
          <mesh onClick={(e) => { e.stopPropagation(); onSelect(object); }}>
            <circleGeometry args={[1.6, 20]} />
            <meshBasicMaterial color={selected ? "#c39bff" : "#7f8db8"} side={THREE.DoubleSide} />
          </mesh>
        )}
        <Html position={[0, -(PICTURE_SIZE * aspect) / 2 - 2, 0]} center
          style={{ pointerEvents: "none" }}>
          <span style={{
            color: selected ? "#e3d5ff" : "rgba(215,225,250,0.85)",
            fontSize: 10, whiteSpace: "nowrap", textShadow: "0 0 4px #000",
          }}>
            {object.name} · {object.distance_text}
          </span>
        </Html>
      </Billboard>
    </group>
  );
}

function Scene({ data, images, stars, selected, onSelect }: {
  data: UniverseData;
  images: SkyImage[];
  stars: SkyStar[];
  selected: UniverseObject | null;
  onSelect: (o: UniverseObject | null) => void;
}) {
  const placed = useMemo(() => withPictures(data.objects, images), [data.objects, images]);
  // A gentle drift so the depth reads as depth the moment the page opens —
  // a still perspective render of points in space is ambiguous until something
  // moves. Handed to OrbitControls rather than done by moving the camera
  // ourselves, which would fight the controls' own per-frame update; and it
  // stops for good the instant the viewer takes hold, so it never wrestles them.
  const [userMoved, setUserMoved] = useState(false);
  return (
    <>
      <color attach="background" args={["#04050a"]} />
      <ambientLight intensity={1} />
      <Backdrop stars={stars} />
      <Home />
      {data.shells.map((s) => (
        <DistanceRing key={s.distance_ly} radius={radiusForDepth(s.depth)} label={s.label} />
      ))}
      {placed.map((p) => (
        <ObjectNode
          key={p.object.safe}
          placed={p}
          selected={selected?.safe === p.object.safe}
          onSelect={onSelect}
        />
      ))}
      <OrbitControls
        makeDefault enablePan={false} minDistance={20} maxDistance={360}
        autoRotate={!userMoved && selected === null} autoRotateSpeed={0.35}
        onStart={() => setUserMoved(true)}
      />
    </>
  );
}

/**
 * The explanation panel. Pure DOM (no WebGL), so the copy that keeps this map
 * honest — what the rings mean, and where the distances come from — is unit
 * testable without a canvas.
 */
export function UniverseLegend({ data }: { data: UniverseData }) {
  const [showUnplaced, setShowUnplaced] = useState(false);
  const span = spanSummary(data.objects);
  const scale = scaleCaption(data.shells);
  return (
    <Paper
      withBorder p="sm" radius="md"
      style={{ position: "absolute", top: 12, left: 12, maxWidth: 340,
        background: "rgba(12,14,22,0.85)" }}
    >
      <Group gap={8} mb={6}>
        <IconGalaxy size={18} />
        <Text fw={600}>Your universe</Text>
        <Badge variant="light">{data.objects.length} placed</Badge>
      </Group>
      {span ? <Text size="xs" mb={4}>{span}</Text> : null}
      {scale ? <Text size="xs" c="dimmed" mb={4}>{scale}</Text> : null}
      <Text size="xs" c="dimmed">{data.provenance}</Text>
      {data.unplaced.length > 0 ? (
        <>
          <Button
            size="compact-xs" variant="subtle" mt={6} px={0}
            onClick={() => setShowUnplaced((v) => !v)}
          >
            {showUnplaced ? "Hide" : `${data.unplaced.length} not placed`}
          </Button>
          {showUnplaced ? (
            <ScrollArea.Autosize mah={140} mt={4}>
              {data.unplaced.map((u) => (
                <Text key={u.safe} size="xs" c="dimmed">
                  {u.name} — {u.reason}
                </Text>
              ))}
            </ScrollArea.Autosize>
          ) : null}
        </>
      ) : null}
      <Text size="xs" c="dimmed" mt={6}>
        Same pictures as the{" "}
        <Anchor component={Link} to="/sky" size="xs">Sky Map</Anchor>, arranged by
        how far away they are instead of which way you pointed.
      </Text>
    </Paper>
  );
}

/** The read-out for a clicked object. Pure DOM, for the same reason. */
export function UniverseObjectCard({ object, onOpen, onClose }: {
  object: UniverseObject;
  onOpen: (safe: string) => void;
  onClose: () => void;
}) {
  const subtitle = [object.object_name, object.type].filter(Boolean).join(" · ");
  return (
    <Paper
      withBorder p="sm" radius="md"
      style={{ position: "absolute", bottom: 12, left: 12, maxWidth: 360,
        background: "rgba(12,14,22,0.92)" }}
    >
      <Group justify="space-between" mb={4}>
        <Text fw={600}>{object.name}</Text>
        <Text size="xs" c="dimmed">{object.object_id}</Text>
      </Group>
      {subtitle ? <Text size="xs" c="dimmed" mb={4}>{subtitle}</Text> : null}
      <Text size="sm" mb={2}>{object.distance_text} away</Text>
      <Text size="xs" c="dimmed" mb={8}>
        The light in your picture left about {object.years_text} ago.
      </Text>
      <Group gap={8}>
        <Button size="xs" onClick={() => onOpen(object.safe)}>Open target</Button>
        <Button size="xs" variant="subtle" onClick={onClose}>Close</Button>
      </Group>
    </Paper>
  );
}

export function UniverseView() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<UniverseObject | null>(null);
  const universe = useQuery({ queryKey: ["universe"], queryFn: api.getUniverse });
  // Shares the Sky Map's cache — the pictures are the same ones, so opening this
  // page after the Sky Map (or before it) costs one fetch between them.
  const sky = useQuery({ queryKey: ["sky"], queryFn: api.getSky });

  const data = universe.data;
  return (
    <div style={{ position: "relative", height: "calc(100dvh - 110px)", minHeight: 420 }}>
      {data && data.objects.length > 0 ? (
        <Canvas camera={{ position: [0, 55, 190], fov: 55, near: 0.5, far: 2000 }}>
          <Scene
            data={data}
            images={sky.data?.images ?? []}
            stars={sky.data?.stars ?? []}
            selected={selected}
            onSelect={setSelected}
          />
        </Canvas>
      ) : (
        <div style={{ position: "absolute", inset: 0, background: "#04050a" }} />
      )}

      {data ? <UniverseLegend data={data} /> : null}

      {universe.isLoading ? (
        <Paper withBorder p="sm" radius="md"
          style={{ position: "absolute", top: 12, left: 12, background: "rgba(12,14,22,0.85)" }}>
          <Group gap={6}><Loader size="xs" /><Text size="xs">Loading…</Text></Group>
        </Paper>
      ) : null}

      {universe.isError ? (
        <Alert color="red" p="xs"
          style={{ position: "absolute", top: 12, left: 12, maxWidth: 340 }}>
          <Group justify="space-between" gap="xs" wrap="nowrap">
            <Text size="xs">
              Couldn't load your universe
              {universe.error instanceof Error ? `: ${universe.error.message}` : "."}
            </Text>
            <Button size="compact-xs" variant="light" onClick={() => universe.refetch()}>
              Retry
            </Button>
          </Group>
        </Alert>
      ) : null}

      {data && data.objects.length === 0 ? (
        <Alert color="yellow" p="xs"
          style={{ position: "absolute", top: 120, left: 12, maxWidth: 340 }}>
          <Text size="xs">
            Nothing to place yet. Shoot and stack a catalogue object — a Messier
            or NGC target — and it'll appear here at its real distance.
          </Text>
        </Alert>
      ) : null}

      {selected ? (
        <UniverseObjectCard
          object={selected}
          onOpen={(safe) => navigate(`/targets/${safe}/history`)}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </div>
  );
}
