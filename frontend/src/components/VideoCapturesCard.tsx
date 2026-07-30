import { Badge, Button, Group, Paper, Stack, Text } from "@mantine/core";
import { IconVideo } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type VideoCapture } from "../api/client";

/**
 * The card's sentence — what's waiting and whether anything's been made of it
 * yet. Pure so it can be tested without rendering.
 *
 * A Moon/Sun video is the one thing you can drop in that the scan will
 * (correctly) report as "nothing found": `*_video/` folders hold no stackable
 * subs, so the deep-sky pipeline walks straight past them. Without a word on
 * the Dashboard, a beginner who copies `Lunar_video/` over sees the scan find
 * zero targets and reasonably concludes the app can't use it.
 */
export function describeCaptures(captures: VideoCapture[]): string {
  const total = captures.length;
  const unstacked = captures.filter((c) => !c.result).length;
  const what = total === 1 ? captures[0].label : "Moon and Sun";
  if (unstacked === 0) {
    return total === 1
      ? `Your ${what} video is stacked and ready to look at.`
      : `All ${total} of your Moon and Sun videos are stacked.`;
  }
  if (unstacked === 1 && total === 1) {
    return `You have a ${what} video waiting — we can turn it into one sharp picture.`;
  }
  return (
    `${unstacked} of your ${total} Moon and Sun videos haven't been stacked yet `
    + `— we can turn each into one sharp picture.`
  );
}

/**
 * "You have a Moon video waiting" — a small, self-hiding Dashboard card that
 * closes the loop on video captures. Renders nothing at all when the incoming
 * folder holds no `*_video/` capture, which is the normal case for a
 * deep-sky-only user.
 */
export function VideoCapturesCard() {
  const q = useQuery({
    queryKey: ["videos"],
    queryFn: api.listVideoCaptures,
    // The incoming folder is walked to answer this, so don't hammer it — the
    // Moon & Sun page itself refreshes faster while it's open.
    staleTime: 60_000,
  });
  const captures = q.data?.captures ?? [];
  if (captures.length === 0) return null;

  const unstacked = captures.filter((c) => !c.result).length;
  return (
    <Paper withBorder p="sm" radius="md">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <IconVideo size={22} style={{ flexShrink: 0, marginTop: 2 }}
          color="var(--mantine-color-yellow-5)" />
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Group gap="xs" justify="space-between" wrap="nowrap">
            <Text size="sm" fw={500}>Moon &amp; Sun videos</Text>
            {unstacked > 0 ? (
              <Badge variant="light" color="yellow" size="sm">
                {unstacked} to stack
              </Badge>
            ) : null}
          </Group>
          <Text size="sm" c="dimmed">{describeCaptures(captures)}</Text>
          <Group gap="xs">
            <Button size="xs" variant="light" component={Link} to="/moon-sun">
              {unstacked > 0 ? "Stack a video" : "Open Moon & Sun"}
            </Button>
          </Group>
        </Stack>
      </Group>
    </Paper>
  );
}
