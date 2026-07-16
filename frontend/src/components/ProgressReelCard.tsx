import { useState } from "react";
import { Button, Group, Image, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconDownload, IconMovie, IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { SharePictureButton } from "./SharePictureButton";
import { shareClipText } from "../share";

/**
 * "Watch your picture come together" — a small looping animation of the stack
 * building up from noise to a clean image, assembled from the evenly-spaced
 * snapshots the stacker keeps when `save_progress` is on. A delightful, purely
 * additive beginner extra shown on the finished result.
 *
 * Renders **nothing** unless this run actually has a multi-frame reel (the
 * common case — `save_progress` is off by default — reads `available: false`,
 * not an error), so it never nags a run that wasn't captured with it on.
 *
 * The card starts collapsed (a single "Play" button) so History's list of runs
 * doesn't fetch every animation up front; the animation `<img>` is only
 * requested once the user chooses to watch it.
 */
export function ProgressReelCard({
  safe,
  runId,
  name,
}: {
  safe: string;
  runId: number;
  /** Display name for the share caption/filename; falls back to `safe`. */
  name?: string;
}) {
  const [playing, setPlaying] = useState(false);
  const info = useQuery({
    queryKey: ["progress-reel", safe, runId],
    queryFn: () => api.stackProgressInfo(safe, runId),
    enabled: !!safe,
  });
  if (!info.data?.available) return null;

  const src = api.stackProgressUrl(safe, runId);
  const clip = shareClipText(name || safe, info.data.format);
  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="grape"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconSparkles size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>Watch your picture appear</Text>
          <Text size="xs" c="dimmed">
            A short loop of your image coming together as {info.data.frames} frames
            stacked — from a single noisy sub to the clean result.
          </Text>
          {playing ? (
            <>
              <Image src={src} radius="sm" fit="contain"
                alt="Your stack building up frame by frame"
                style={{ maxHeight: 360 }} />
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
              <Button size="xs" variant="light" color="grape"
                leftSection={<IconMovie size={14} />}
                onClick={() => setPlaying(true)}>
                Play
              </Button>
            </Group>
          )}
        </Stack>
      </Group>
    </Paper>
  );
}
