import { Group, Image, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type BestFrame } from "../api/client";

/**
 * Plain-language caption for the "First look" card. Pure/testable.
 *
 * Answers "did tonight work?" before the stack even runs: names the sharpest
 * accepted sub out of however many the night brought in, and when it was
 * captured. Kept beginner-friendly — no jargon in the headline; the FWHM / star
 * count sit on a quieter second line (see {@link firstLookMetrics}).
 */
export function firstLookCaption(best: BestFrame): string {
  const of = best.n_accepted > 1 ? ` of ${best.n_accepted}` : "";
  let caption = `Your sharpest sub${of}`;
  if (best.captured_utc) {
    const t = new Date(best.captured_utc);
    if (!Number.isNaN(t.getTime())) {
      caption += ` — captured ${t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    }
  }
  return caption;
}

/** The quiet metric line ("FWHM 2.1 px · 480 stars"), or null when unmeasured. */
export function firstLookMetrics(best: BestFrame): string | null {
  const parts: string[] = [];
  if (best.fwhm_px != null) parts.push(`FWHM ${best.fwhm_px.toFixed(1)} px`);
  if (best.star_count != null) parts.push(`${best.star_count} stars`);
  return parts.length ? parts.join(" · ") : null;
}

/**
 * "First look" — the sharpest accepted sub, shown the moment QC finishes and
 * before the stack runs. A beginner drops a night's subs and then waits minutes
 * for a stack with nothing to look at; this gives instant "yes, it worked"
 * reassurance and a chance to catch a bad framing/focus night early. Read-only:
 * reuses the existing per-frame preview thumbnail and QC metrics.
 *
 * Renders nothing until an accepted sub has been QC'd (`frame_id` present). The
 * parent hides it once a finished stack exists, so the real picture supersedes
 * this pre-stack peek.
 */
export function FirstLookCard({ safe }: { safe: string }) {
  const best = useQuery({
    queryKey: ["best-frame", safe],
    queryFn: () => api.bestFrame(safe),
    enabled: !!safe,
  });
  const data = best.data;
  if (!data || data.frame_id == null) return null;
  const metrics = firstLookMetrics(data);
  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="grape"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconSparkles size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>First look</Text>
          <Image
            src={api.framePreviewUrl(safe, data.frame_id, 640)}
            radius="sm"
            alt="Sharpest sub preview"
            style={{ maxWidth: 320, width: "100%" }}
          />
          <Text size="sm" c="dimmed">{firstLookCaption(data)}</Text>
          {metrics ? <Text size="xs" c="dimmed">{metrics}</Text> : null}
        </Stack>
      </Group>
    </Paper>
  );
}
