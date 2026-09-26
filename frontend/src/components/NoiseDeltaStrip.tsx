import { useState } from "react";
import { Button, Group, Image, Stack, Text } from "@mantine/core";
import { IconPhotoScan } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  NOISE_DELTA_BLURB, noiseDeltaSides, noiseDeltaVerdict,
} from "../noiseDelta";

/**
 * The *picture* half of "Did it get better?" — one patch of sky from the previous
 * stack beside the same patch from the newest, at full resolution and under one
 * shared stretch.
 *
 * The card around this has always answered the question in words and a link. The
 * owner asked to *see* it (2026-09-25), and a whole-canvas A/B at card size
 * cannot show it: both previews are shrunk 5–10× on the way to the screen and
 * decimation averages the grain away before it arrives. A small native-resolution
 * crop is the only version of this picture that carries the thing the sentence is
 * about.
 *
 * Off until asked. The two crops cost two decimated passes over both masters to
 * place (the backend caches the result, but the first one is real work on a
 * mosaic), so the Target page does not spend that on every view — exactly like
 * the deepening reel's "Play". Self-hides entirely when the backend says there is
 * no honest picture here: an editor export on either side, a canvas too small to
 * yield a patch, or no patch of sky covered in both.
 */
export function NoiseDeltaStrip({
  safe, newestId, previousId, newestLabel, previousLabel,
}: {
  safe: string;
  newestId: number;
  previousId: number;
  /** Dates for the two halves, as the card itself spells them. */
  newestLabel?: string | null;
  previousLabel?: string | null;
}) {
  const [shown, setShown] = useState(false);
  const info = useQuery({
    queryKey: ["noise-delta", safe, newestId, previousId],
    queryFn: () => api.noiseDeltaInfo(safe, newestId, previousId).catch(() => null),
    enabled: shown && !!safe,
  });
  if (!shown) {
    return (
      <Group gap="xs">
        <Button size="compact-xs" variant="subtle" color="grape"
          data-testid="noise-delta-show"
          leftSection={<IconPhotoScan size={14} />}
          onClick={() => setShown(true)}>
          Show me the difference
        </Button>
      </Group>
    );
  }
  if (info.isPending) {
    return <Text size="xs" c="dimmed">Finding a patch of sky in both pictures…</Text>;
  }
  if (!info.data?.available) return null;
  const verdict = noiseDeltaVerdict(info.data);
  return (
    <Stack gap={4} data-testid="noise-delta-strip">
      <Image src={api.noiseDeltaUrl(safe, newestId, previousId)} radius="sm"
        fit="contain" style={{ maxHeight: 220 }}
        alt="The same patch of sky in your previous stack and your newest one, side by side" />
      <Text size="xs" c="dimmed">
        {noiseDeltaSides(previousLabel, newestLabel)} {NOISE_DELTA_BLURB}
      </Text>
      {verdict ? (
        <Text size="xs" data-testid="noise-delta-verdict">{verdict}</Text>
      ) : null}
    </Stack>
  );
}
