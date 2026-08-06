import { Anchor, Button, Group, List, Paper, Progress, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconCircleCheck, IconCircleDashed, IconRoute } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import {
  firstImageComplete, firstImageDone, firstImageDoneMessage, firstImageNextStep,
  firstImageSteps,
} from "./firstImageSteps";

// Two localStorage flags, both defensively guarded so a disabled/broken store can
// never break the Dashboard (same pattern as the readiness-banner dismissal):
//
//  * `STARTED_KEY` is set the first time the card renders with a step still open.
//    It's what keeps this card off an *established* install: an upgrade of a box
//    that already has stacks has every step ticked on first render, never sets
//    the flag, and so never shows the card at all — no "well done on your first
//    picture" for someone with 300 of them.
//  * `DISMISS_KEY` is the user saying "got it", after which it stays gone.
const STARTED_KEY = "astrostack.dashboard.firstImageStarted";
const DISMISS_KEY = "astrostack.dashboard.firstImageDismissed";

function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function writeFlag(key: string): void {
  try {
    localStorage.setItem(key, "1");
  } catch {
    /* a disabled store just means the card behaves as if never flagged */
  }
}

/**
 * "Your first image" — a small, self-checking map of the journey from an empty
 * app to a finished picture, for the one night a beginner most needs it.
 *
 * Reads only what the Dashboard already fetches (`/api/system`, `/api/stats`),
 * ticks its own steps off, and disappears for good once the user has made their
 * first picture and said "got it". Read-only and additive: it changes nothing
 * about how the app behaves, it just says what to do next.
 */
export function FirstImageCard() {
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.getStats });
  const system = useQuery({
    queryKey: ["system"], queryFn: api.getSystem, staleTime: 60_000,
  });
  const [dismissed, setDismissed] = useState(() => readFlag(DISMISS_KEY));

  const loaded = !!stats.data && !!system.data;
  const steps = firstImageSteps(system.data, stats.data);
  // "Done" counts a stacked Moon/Sun still, which no step can ever tick — see
  // `firstImageDone`. `complete` stays the strict four-step reading, because the
  // progress bar is about *those* steps and must not claim them.
  const complete = firstImageComplete(steps);
  const done = firstImageDone(steps, stats.data);
  const next = firstImageNextStep(steps);

  // Remember that this install was *seen* mid-journey, so the congratulation at
  // the end only ever reaches someone who actually walked it here.
  useEffect(() => {
    if (loaded && !done) writeFlag(STARTED_KEY);
  }, [loaded, done]);

  if (!loaded || dismissed) return null;
  if (done && !readFlag(STARTED_KEY)) return null;

  const doneCount = steps.filter((s) => s.done).length;
  return (
    <Paper withBorder p="md" radius="md" data-testid="first-image-card">
      <Group justify="space-between" wrap="nowrap" mb={4}>
        <Group gap={8} wrap="nowrap">
          <ThemeIcon size={26} radius="xl" variant="light" color="violet">
            <IconRoute size={16} />
          </ThemeIcon>
          <Text fw={600}>Your first image</Text>
        </Group>
        {complete || !done ? (
          <Text size="xs" c="dimmed">{doneCount} of {steps.length} done</Text>
        ) : null}
      </Group>
      {/* Hidden when the picture came from a video: the bar measures the
          deep-sky steps, and "0 of 4" under a congratulation reads as a
          contradiction rather than as progress. */}
      {complete || !done ? (
        <Progress value={(doneCount / steps.length) * 100} size="sm" color="violet"
          mb="sm" aria-label="First image progress" />
      ) : null}
      {done ? (
        <Stack gap="xs">
          <Text size="sm">{firstImageDoneMessage(steps)}</Text>
          <Group gap="sm">
            <Button size="xs" variant="light" component={Link} to="/gallery">
              See your pictures
            </Button>
            <Button size="xs" variant="subtle" color="gray"
              onClick={() => { writeFlag(DISMISS_KEY); setDismissed(true); }}>
              Got it
            </Button>
          </Group>
        </Stack>
      ) : (
        <Stack gap="xs">
          <Text size="sm" c="dimmed">
            {next
              ? `Next: ${next.hint}`
              : "Four steps from a folder of subs to a finished picture."}
          </Text>
          <List spacing={6} size="sm" center>
            {steps.map((s) => (
              <List.Item
                key={s.key}
                icon={
                  <ThemeIcon size={18} radius="xl" variant="light"
                    color={s.done ? "teal" : "gray"}>
                    {s.done ? <IconCircleCheck size={12} /> : <IconCircleDashed size={12} />}
                  </ThemeIcon>
                }
              >
                <Group gap={8} wrap="wrap">
                  <Text size="sm" c={s.done ? "dimmed" : undefined}
                    td={s.done ? "line-through" : undefined} span>
                    {s.label}
                  </Text>
                  {!s.done ? (
                    <Anchor component={Link} to={s.href} size="sm">{s.action}</Anchor>
                  ) : null}
                </Group>
              </List.Item>
            ))}
          </List>
          <Group>
            <Button size="xs" variant="subtle" color="gray"
              onClick={() => { writeFlag(DISMISS_KEY); setDismissed(true); }}>
              Hide this
            </Button>
          </Group>
        </Stack>
      )}
    </Paper>
  );
}
