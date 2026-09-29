import { useState } from "react";
import { Button, Group, Image, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconDownload, IconMovie, IconStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { SharePictureButton } from "./SharePictureButton";
import { deepeningBlurb, deepeningCaption, deepeningClip } from "../deepeningReel";
import {
  nightReelOfferBlurb, nightReelOfferCost, nightReelStackHref,
} from "../nightReelOffer";

/** The card's shell, shared by the reel and the offer that stands in for it —
 * one heading and one icon, so "night after night" reads as one place in the
 * app whether it is showing the clip or how to get one. */
function ReelShell({ children }: { children: React.ReactNode }) {
  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="indigo"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconStars size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>Your target, night after night</Text>
          {children}
        </Stack>
      </Group>
    </Paper>
  );
}

/**
 * "Your target, night after night" — a small looping animation of the same
 * object getting cleaner and deeper across successive re-stacks, assembled from
 * the master FITS the app already archives each time you re-stack. The single
 * most rewarding arc of the hobby ("look how far my picture has come"), and the
 * one thing a multi-night beginner most wants to share.
 *
 * Renders **nothing** until a target has ≥2 stacks on disk (`available: false`,
 * not an error) — a single-stack target has no arc yet — so it never nags. Every
 * frame is tone-mapped with one shared stretch (see seestack.render.deepening),
 * so the only visible change is the noise dropping, not a brightness flicker.
 *
 * The one exception to the self-hiding is the **offer**: a target stacked once
 * across several nights already holds every sub this reel is made of, and the
 * only reason it has no clip is that `save_progress` is an advanced switch that
 * is off by default. There the card says so and sets the form up, rather than
 * leaving a beginner to find a switch they have never heard of. The backend
 * decides when that is honest (`webapp/reeloffer.py`); everywhere else this
 * still renders nothing at all.
 *
 * Starts collapsed (a single "Play" button) so the Target page doesn't build the
 * animation up front; the `<img>` is only requested once the user chooses to
 * watch it.
 */
export function DeepeningReelCard({
  safe,
  name,
}: {
  safe: string;
  /** Display name for the caption/share; falls back to `safe`. */
  name?: string;
}) {
  const [playing, setPlaying] = useState(false);
  const info = useQuery({
    queryKey: ["deepening-reel", safe],
    queryFn: () => api.deepeningReelInfo(safe),
    enabled: !!safe,
  });
  if (!info.data?.available) {
    const offer = info.data?.reel_offer;
    if (!offer) return null;
    return (
      <ReelShell>
        <Text size="xs" c="dimmed">{nightReelOfferBlurb(name, offer)}</Text>
        <Text size="xs" c="dimmed">{nightReelOfferCost(offer)}</Text>
        <Group gap="xs">
          <Button size="xs" variant="light" color="indigo"
            component={Link} to={nightReelStackHref(safe, offer)}
            leftSection={<IconMovie size={14} />}>
            Set up that stack
          </Button>
        </Group>
      </ReelShell>
    );
  }

  const src = api.deepeningReelUrl(safe);
  const caption = deepeningCaption(name, info.data);
  const clip = deepeningClip(name || safe, info.data.format);
  return (
    <ReelShell>
      <Text size="xs" c="dimmed">
        {deepeningBlurb(name, info.data)}
      </Text>
      {playing ? (
        <>
          <Image src={src} radius="sm" fit="contain"
            alt="Your target getting deeper across successive stacks"
            style={{ maxHeight: 360 }} />
          {caption ? (
            <Text size="xs" c="dimmed" ta="center">{caption}</Text>
          ) : null}
          <Group gap="xs">
            <Button size="xs" variant="light" leftSection={<IconDownload size={14} />}
              component="a" href={src} download>
              Download clip
            </Button>
            <SharePictureButton
              url={src}
              filename={clip.filename}
              title={clip.title}
              text={clip.text}
              label="Share clip"
              tooltip="Share this clip to another app"
              ariaLabel="Share clip"
              errorMessage="Couldn't share this clip — try downloading it instead."
            />
          </Group>
        </>
      ) : (
        <Group gap="xs">
          <Button size="xs" variant="light" color="indigo"
            leftSection={<IconMovie size={14} />}
            onClick={() => setPlaying(true)}>
            Play
          </Button>
        </Group>
      )}
    </ReelShell>
  );
}
