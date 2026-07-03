import { useEffect, useRef, useState } from "react";
import {
  Alert, Badge, Button, Center, Group, Image, Loader, Paper, SegmentedControl,
  SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import { IconArrowLeft, IconGitCompare } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, type GalleryItem } from "../api/client";
import { formatIntegration } from "../format";
import { NoiseReadout, hasNoise } from "../components/NoiseBadge";
import { HazyNightBadge } from "../components/HazyNightBadge";
import { CalibrationBadge } from "../components/CalibrationBadge";
import { RejectionBadge } from "../components/RejectionBadge";
import { QueryError } from "../components/QueryError";

// A compare target is referenced in the URL as "<safe>:<run_id>" (safe target
// keys never contain a colon), so a bookmarkable /compare?a=M_42:3&b=M_42:7 URL
// fully describes a comparison.
export function parseRef(raw: string | null): { safe: string; run_id: number } | null {
  if (!raw) return null;
  const idx = raw.lastIndexOf(":");
  if (idx <= 0) return null;
  const safe = raw.slice(0, idx);
  const run_id = Number(raw.slice(idx + 1));
  if (!safe || !Number.isInteger(run_id)) return null;
  return { safe, run_id };
}

/** Build the /compare URL for two gallery items. */
export function compareHref(a: GalleryItem, b: GalleryItem): string {
  return `/compare?a=${a.safe}:${a.run_id}&b=${b.safe}:${b.run_id}`;
}

// Compare the two stacks' background-noise σ into a plain-language verdict. Both
// must carry a measured σ; returns null otherwise (nothing to say). The σ is
// normalized to each image's own signal range so it's comparable across
// gain/exposure. `pct` is how much lower the cleaner one's noise is (0–100).
export function noiseComparison(
  a: GalleryItem, b: GalleryItem,
): { winner: "A" | "B"; pct: number } | null {
  if (!hasNoise(a.noise_sigma) || !hasNoise(b.noise_sigma)) return null;
  const sa = a.noise_sigma as number;
  const sb = b.noise_sigma as number;
  if (sa <= 0 || sb <= 0 || sa === sb) return null;
  const [winner, hi, lo] = sa < sb ? ["A", sb, sa] as const : ["B", sa, sb] as const;
  return { winner, pct: Math.round((1 - lo / hi) * 100) };
}

type CompareMode = "side" | "blink";

function CardMeta({ item }: { item: GalleryItem }) {
  return (
    <Stack gap={2}>
      <Group justify="space-between" wrap="nowrap">
        <Text fw={600} truncate component={Link} to={`/targets/${item.safe}/history`}>
          {item.target_name}
        </Text>
        <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
          <RejectionBadge options={item.options} />
          <HazyNightBadge ratio={item.transparency_ratio} />
          <CalibrationBadge calstat={item.calstat} />
          <Badge variant="light">{item.n_frames_used} frames</Badge>
        </Group>
      </Group>
      <Text size="xs" c="dimmed" truncate>
        {item.output_basename} · {item.canvas_w}×{item.canvas_h}
        {item.total_exposure_s ? ` · ${formatIntegration(item.total_exposure_s)}` : ""}
        {hasNoise(item.noise_sigma) ? <> · <NoiseReadout sigma={item.noise_sigma} /></> : null}
      </Text>
    </Stack>
  );
}

/** Blink comparator: alternates the two images in one frame on a timer so a
 * subtle difference (noise, a cleaned trail, sharper stars) pops out. */
function Blink({ a, b }: { a: GalleryItem; b: GalleryItem }) {
  const [showA, setShowA] = useState(true);
  const [running, setRunning] = useState(true);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!running) return;
    timer.current = window.setInterval(() => setShowA((s) => !s), 700);
    return () => window.clearInterval(timer.current);
  }, [running]);

  const current = showA ? a : b;
  return (
    <Stack gap="xs" align="center">
      <div style={{ position: "relative", width: "100%", maxWidth: 640 }}>
        <Image src={current.preview_url} fit="contain" bg="#000" h={420} radius="sm" />
        <Badge
          style={{ position: "absolute", top: 8, left: 8 }}
          color={showA ? "blue" : "grape"} variant="filled"
        >
          {showA ? "A" : "B"}
        </Badge>
      </div>
      <Group>
        <Button size="xs" variant="light" onClick={() => setRunning((r) => !r)}>
          {running ? "Pause" : "Play"}
        </Button>
        {!running ? (
          <Button size="xs" variant="subtle" onClick={() => setShowA((s) => !s)}>
            Flip to {showA ? "B" : "A"}
          </Button>
        ) : null}
      </Group>
      <Text size="xs" c="dimmed">
        Showing {showA ? "A" : "B"}: {current.target_name} · {current.output_basename}
      </Text>
    </Stack>
  );
}

export function CompareView() {
  const [params] = useSearchParams();
  const [mode, setMode] = useState<CompareMode>("side");
  const refA = parseRef(params.get("a"));
  const refB = parseRef(params.get("b"));

  const gallery = useQuery({ queryKey: ["gallery"], queryFn: api.getGallery });

  const backToGallery = (
    <Button component={Link} to="/gallery" variant="subtle" size="xs"
      leftSection={<IconArrowLeft size={14} />}>
      Back to Gallery
    </Button>
  );

  if (!refA || !refB) {
    return (
      <Stack>
        <Title order={2}>Compare stacks</Title>
        <Alert color="yellow" title="Pick two stacks to compare">
          Select two images in the Gallery and choose “Compare”. A comparison link
          looks like <code>/compare?a=M_42:3&amp;b=M_42:7</code>.
        </Alert>
        {backToGallery}
      </Stack>
    );
  }

  if (gallery.isError && !gallery.data) {
    return <QueryError error={gallery.error} onRetry={() => gallery.refetch()} />;
  }
  if (gallery.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }

  const items = gallery.data?.items ?? [];
  const find = (r: { safe: string; run_id: number }) =>
    items.find((it) => it.safe === r.safe && it.run_id === r.run_id) ?? null;
  const a = find(refA);
  const b = find(refB);

  if (!a || !b) {
    return (
      <Stack>
        <Title order={2}>Compare stacks</Title>
        <Alert color="red" title="One of those stacks no longer exists">
          A stack referenced by this comparison couldn’t be found — it may have been
          deleted. Pick two current images from the Gallery.
        </Alert>
        {backToGallery}
      </Stack>
    );
  }

  const verdict = noiseComparison(a, b);

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap" gap="xs">
        <Group gap="xs">
          <IconGitCompare size={24} />
          <Title order={2}>Compare stacks</Title>
        </Group>
        <Group gap="sm">
          <SegmentedControl
            size="xs" value={mode} onChange={(v) => setMode(v as CompareMode)}
            data={[{ label: "Side by side", value: "side" }, { label: "Blink", value: "blink" }]}
            aria-label="Compare mode"
          />
          {backToGallery}
        </Group>
      </Group>

      {verdict ? (
        <Alert color="teal" variant="light" py="xs" title={undefined}>
          <Text size="sm">
            <b>{verdict.winner}</b> has <b>{verdict.pct}% lower</b> background noise
            {" "}— it's the cleaner stack. (Noise σ is normalized so it's comparable
            across gain/exposure; it isn't the only measure of a better image.)
          </Text>
        </Alert>
      ) : null}

      {mode === "side" ? (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {[["A", a] as const, ["B", b] as const].map(([tag, it]) => (
            <Paper key={tag} withBorder p="sm" radius="md">
              <Stack gap="xs">
                <Group gap="xs">
                  <Badge color={tag === "A" ? "blue" : "grape"} variant="filled">{tag}</Badge>
                  <CardMeta item={it} />
                </Group>
                {it.has_preview ? (
                  <Image src={it.preview_url} fit="contain" bg="#000" h={420} radius="sm" />
                ) : (
                  <Center h={420} bg="dark.6"><Text c="dimmed">No preview</Text></Center>
                )}
              </Stack>
            </Paper>
          ))}
        </SimpleGrid>
      ) : (
        <Paper withBorder p="sm" radius="md">
          <Blink a={a} b={b} />
        </Paper>
      )}
    </Stack>
  );
}
