import { useEffect, useRef, useState } from "react";
import {
  Alert, Badge, Box, Button, Center, Group, Image, Loader, Paper, SegmentedControl,
  SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import { IconArrowLeft, IconGitCompare } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, type GalleryItem } from "../api/client";
import { formatIntegration, pictureDateLabel } from "../format";
import { NoiseReadout, hasNoise } from "../components/NoiseBadge";
import { HazyNightBadge } from "../components/HazyNightBadge";
import { PanelSeamsBadge } from "../components/PanelSeamsBadge";
import { CalibrationBadge } from "../components/CalibrationBadge";
import { RejectionBadge } from "../components/RejectionBadge";
import { QueryError } from "../components/QueryError";
import { splitClipLeft, splitFraction, splitLeftPct } from "../components/editor/splitCompare";

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
//
// `sameTarget` is what the *claim* hangs on. Normalising for gain and exposure
// makes the figure comparable between two stacks **of the same field**; it does
// not make it comparable across two different objects, where the number is
// mostly about how bright and busy that patch of sky is. The Gallery lets you
// select any two pictures, so "B is the cleaner stack" was being said about
// M 42 against NGC 7000. The figure survives a cross-target comparison (it is
// still each picture's own measured noise) — the verdict doesn't, so the caller
// keeps one and drops the other rather than hiding the line entirely.
export function noiseComparison(
  a: GalleryItem, b: GalleryItem,
): { winner: "A" | "B"; loser: "A" | "B"; pct: number; sameTarget: boolean } | null {
  if (!hasNoise(a.noise_sigma) || !hasNoise(b.noise_sigma)) return null;
  const sa = a.noise_sigma as number;
  const sb = b.noise_sigma as number;
  if (sa <= 0 || sb <= 0 || sa === sb) return null;
  const [winner, loser, hi, lo] =
    sa < sb ? ["A", "B", sb, sa] as const : ["B", "A", sa, sb] as const;
  return {
    winner, loser, pct: Math.round((1 - lo / hi) * 100), sameTarget: a.safe === b.safe,
  };
}

// Compare the two stacks' panel-flatness verdicts into a plain sentence — the
// same "answer it out loud" job `noiseComparison` does for noise, for the third
// axis of "did my new stack get better?" that only mosaic shooters have.
//
// Both sides must carry a verdict the app knows (so both are mosaics the stacker
// could measure — every single-field stack and every run made before the
// measurement existed serves `null`), and the two must *differ*: when they agree
// the two chips already say it and there is nothing to weigh. Deliberately no
// magnitude — the verdicts are coarse words, and the beginner never sees the
// ratio behind them, so "2× flatter" would be inventing precision.
export function panelComparison(
  a: GalleryItem, b: GalleryItem,
): { winner: "A" | "B"; loser: "A" | "B" } | null {
  const known = (v?: string | null) => v === "flat" || v === "check";
  if (!known(a.seam_verdict) || !known(b.seam_verdict)) return null;
  if (a.seam_verdict === b.seam_verdict) return null;
  return a.seam_verdict === "flat"
    ? { winner: "A", loser: "B" }
    : { winner: "B", loser: "A" };
}

// "Did it get better?" is, more often than not, answered by *depth* rather than
// by processing: the second stack is better because it has two more nights in
// it. That is the one fact this page's own dates can't show — so say it.
//
// Deliberately narrow. Both runs must have **recorded** their night count
// (schema 19+); a count is never inferred from the window, because 15→18 Nov is
// equally consistent with two nights and with four. The counts must differ (when
// they agree there is nothing to weigh), and both sides must be the *same
// target* — "M 42 has more nights than NGC 7000" compares nothing.
export function nightsComparison(
  a: GalleryItem, b: GalleryItem,
): { winner: "A" | "B"; more: number; fewer: number } | null {
  if (a.safe !== b.safe) return null;
  const na = a.capture_nights;
  const nb = b.capture_nights;
  const ok = (n?: number | null): n is number =>
    typeof n === "number" && Number.isFinite(n) && n >= 1;
  if (!ok(na) || !ok(nb) || na === nb) return null;
  return na > nb
    ? { winner: "A", more: na, fewer: nb }
    : { winner: "B", more: nb, fewer: na };
}

type CompareMode = "side" | "split" | "blink";

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
          <PanelSeamsBadge verdict={item.seam_verdict} />
          <CalibrationBadge calstat={item.calstat} />
          <Badge variant="light">{item.n_frames_used} frames</Badge>
        </Group>
      </Group>
      <Text size="xs" c="dimmed" truncate>
        {item.output_basename} · {item.canvas_w}×{item.canvas_h}
        {item.total_exposure_s ? ` · ${formatIntegration(item.total_exposure_s)}` : ""}
        {hasNoise(item.noise_sigma) ? <> · <NoiseReadout sigma={item.noise_sigma} /></> : null}
      </Text>
      {/* "Side by side" is the mode most people compare in, and it carried no
          date at all — so the one thing that usually explains the difference
          (this stack has more nights in it) was invisible here. Labelled, and it
          drops itself and its separator when there is no usable date. */}
      {compareDateLabel(item) ? (
        <Text size="xs" c="dimmed" truncate>{compareDateLabel(item)}</Text>
      ) : null}
    </Stack>
  );
}

/**
 * The one-line date for a compare side, **labelled** — "Shot over 4 nights,
 * 15–18 Nov 2024", or a labelled "Stacked 30 Aug 2026" for a run made before the
 * app recorded when its subs were taken. "" when neither date is usable, so the
 * clause is simply dropped.
 *
 * This page's whole question is *"did it get better?"*, and the honest answer is
 * usually *"yes, because the second one has two more nights in it"* — precisely
 * the fact a **processing** stamp cannot show. Printing the run's
 * `timestamp_utc` bare (as this did) also read as a capture date, which on a
 * re-stack of a back catalogue is years out. `pictureDateLabel` is the same
 * helper the Gallery card, the Sky footprint and the share sheet use, so no two
 * surfaces can date one picture differently.
 */
export function compareDateLabel(item: GalleryItem): string {
  return pictureDateLabel(
    item.capture_night_start, item.capture_night_end, item.timestamp_utc,
    item.capture_nights,
  );
}

/** One side of the A/B provenance strip: which stack this is (colour-keyed to the
 * split/blink badge) and its plain-language provenance — basename, frame count,
 * integration, date and measured noise — so a beginner scrubbing the divider can
 * tell *which* stack is which (is A the deep 5-night one or the old 2-night one?),
 * the exact thing the bare "A"/"B" badges couldn't answer. */
function AbSide({ label, color, item }: { label: string; color: string; item: GalleryItem }) {
  const date = compareDateLabel(item);
  return (
    <Stack gap={2} style={{ flex: 1, minWidth: 0 }} data-testid={`ab-side-${label}`}>
      <Group gap={6} wrap="nowrap">
        <Badge color={color} variant="filled" size="sm" style={{ flexShrink: 0 }}>{label}</Badge>
        <Text fw={600} size="sm" truncate component={Link}
          to={`/targets/${item.safe}/history`}>
          {item.target_name}
        </Text>
      </Group>
      <Text size="xs" c="dimmed" truncate>{item.output_basename}</Text>
      <Text size="xs" c="dimmed" truncate>
        {item.n_frames_used} frames
        {item.total_exposure_s ? ` · ${formatIntegration(item.total_exposure_s)}` : ""}
        {date ? ` · ${date}` : ""}
        {hasNoise(item.noise_sigma) ? <> · <NoiseReadout sigma={item.noise_sigma} /></> : null}
      </Text>
    </Stack>
  );
}

/** Two-column A/B provenance strip shown above the Split and Blink comparators,
 * so those modes are as trustworthy as "Side by side" about *which* stack is
 * which. Frontend-only; every field already rides on the gallery items. */
function AbMetaStrip({ a, b }: { a: GalleryItem; b: GalleryItem }) {
  return (
    <Group align="flex-start" gap="md" wrap="nowrap"
      style={{ width: "100%", maxWidth: 640 }}>
      <AbSide label="A" color="blue" item={a} />
      <AbSide label="B" color="grape" item={b} />
    </Group>
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
      <AbMetaStrip a={a} b={b} />
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

/** Split comparator: overlays A on top of B and clips A with a draggable vertical
 * divider, so you scrub one line across a single frame to see exactly where the
 * two stacks differ (faint detail emerging, noise dropping, a cleaned trail) —
 * the most direct answer to "did my new stack actually get better?". Reuses the
 * editor's tested split-divider geometry. Left of the divider is A, right is B. */
function Split({ a, b }: { a: GalleryItem; b: GalleryItem }) {
  const [frac, setFrac] = useState(0.5);
  const dragging = useRef(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  const moveTo = (clientX: number) => {
    const rect = boxRef.current?.getBoundingClientRect();
    if (!rect) return;
    setFrac(splitFraction(clientX, rect.left, rect.width));
  };

  if (!a.has_preview || !b.has_preview) {
    return (
      <Text size="sm" c="dimmed" ta="center" py="lg">
        Split needs a preview image for both stacks. Try “Side by side”.
      </Text>
    );
  }

  return (
    <Stack gap="xs" align="center">
      <AbMetaStrip a={a} b={b} />
      <Box
        ref={boxRef}
        onPointerDown={(e) => {
          dragging.current = true;
          (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
          moveTo(e.clientX);
        }}
        onPointerMove={(e) => { if (dragging.current) moveTo(e.clientX); }}
        onPointerUp={() => { dragging.current = false; }}
        aria-label="Drag to reveal — left is A, right is B"
        style={{
          position: "relative", width: "100%", maxWidth: 640, maxHeight: 420,
          overflow: "hidden", borderRadius: 6, cursor: "ew-resize",
          touchAction: "none", userSelect: "none",
        }}
      >
        {/* Base (right of divider): B. */}
        <img src={b.preview_url} alt={`B: ${b.output_basename}`}
          draggable={false}
          style={{ display: "block", width: "100%", maxHeight: 420,
            objectFit: "contain", background: "#000" }} />
        {/* Overlay (left of divider): A, clipped. */}
        <img src={a.preview_url} alt={`A: ${a.output_basename}`}
          draggable={false}
          style={{
            position: "absolute", inset: 0, width: "100%", height: "100%",
            objectFit: "contain", background: "#000", clipPath: splitClipLeft(frac),
          }} />
        {/* Divider. */}
        <Box style={{
          position: "absolute", top: 0, bottom: 0, left: splitLeftPct(frac),
          width: 2, background: "var(--mantine-color-gray-2)",
          transform: "translateX(-1px)", pointerEvents: "none",
        }} />
        <Badge style={{ position: "absolute", top: 8, left: 8, pointerEvents: "none" }}
          color="blue" variant="filled">A</Badge>
        <Badge style={{ position: "absolute", top: 8, right: 8, pointerEvents: "none" }}
          color="grape" variant="filled">B</Badge>
      </Box>
      <Text size="xs" c="dimmed">
        Drag the divider — left is A, right is B.
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
  const panels = panelComparison(a, b);
  const nights = nightsComparison(a, b);

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
            data={[
              { label: "Side by side", value: "side" },
              { label: "Split", value: "split" },
              { label: "Blink", value: "blink" },
            ]}
            aria-label="Compare mode"
          />
          {backToGallery}
        </Group>
      </Group>

      {verdict || panels || nights ? (
        <Alert color="teal" variant="light" py="xs" title={undefined}>
          <Stack gap={4}>
            {verdict && verdict.sameTarget ? (
              <Text size="sm" data-testid="noise-verdict">
                <b>{verdict.winner}</b> has <b>{verdict.pct}% lower</b> background noise
                {" "}— it's the cleaner stack. (Noise σ is normalized so it's comparable
                across gain/exposure; it isn't the only measure of a better image.)
              </Text>
            ) : null}
            {/* Two different objects: keep the measurement, drop the verdict. A
                darker, emptier field reads quieter than a bright nebula however
                well either was stacked, so "the cleaner stack" would be a claim
                about the sky, not about the stacking. */}
            {verdict && !verdict.sameTarget ? (
              <Text size="sm" data-testid="noise-verdict">
                <b>{verdict.winner}</b> ({verdict.winner === "A" ? a.target_name : b.target_name})
                {" "}reads <b>{verdict.pct}% lower</b> background noise than <b>{verdict.loser}</b>
                {" "}({verdict.loser === "A" ? a.target_name : b.target_name}) — but these are two
                {" "}different objects, so that's mostly about the sky you were pointing at, not
                {" "}about which stack came out better.
              </Text>
            ) : null}
            {panels ? (
              <Text size="sm">
                <b>{panels.winner}</b>'s mosaic panels evened out, while <b>{panels.loser}</b>'s
                {" "}sky still steps where its panels join — so <b>{panels.loser}</b> may show
                {" "}faint seams once it's stretched.
              </Text>
            ) : null}
            {nights ? (
              <Text size="sm">
                <b>{nights.winner}</b> is made of subs from <b>{nights.more} nights</b>
                {" "}against {nights.fewer} — on the same target that's usually the
                {" "}biggest difference between two stacks, whatever the settings.
              </Text>
            ) : null}
          </Stack>
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
      ) : mode === "split" ? (
        <Paper withBorder p="sm" radius="md">
          <Split a={a} b={b} />
        </Paper>
      ) : (
        <Paper withBorder p="sm" radius="md">
          <Blink a={a} b={b} />
        </Paper>
      )}
    </Stack>
  );
}
