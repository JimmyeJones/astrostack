import { Button, Card, Group, Stack, Text } from "@mantine/core";
import { IconDownload, IconLayoutGrid } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/** How many pictures the wall holds. Matches the backend's default cap — past
 * roughly nine, each picture is too small to enjoy at social-media sizes, and
 * the point of the wall is the pictures, not the count. */
const WALL_TILES = 9;

/** "My deep-sky wall" — every finished target as one shareable picture.
 *
 * The gallery can only ever show one image at a time, so nothing in the app
 * says *"look at everything I've captured"* — and that montage is the thing a
 * beginner actually posts at the end of a good run of clear nights. The recap
 * poster next to this card shares the *numbers* over one hero image; this
 * shares the pictures themselves.
 *
 * Self-hiding by contract: a library with fewer than two finished pictures gets
 * nothing at all, because a "wall" of one is just the picture the gallery
 * already shows (the endpoint enforces the same floor with a 404). Nothing is
 * written — the montage is rendered on demand from previews the app already
 * keeps, exactly like the recap poster.
 */
export function MyDeepSkyWallCard() {
  const { data } = useQuery({
    queryKey: ["library-summary"], queryFn: api.getLibrarySummary,
    staleTime: 60_000,
  });

  const heroes = data?.heroes ?? [];
  if (heroes.length < 2) return null;

  const shown = Math.min(heroes.length, WALL_TILES);
  return (
    <Card withBorder radius="md" padding="md">
      <Stack gap="xs">
        <Group gap="xs" wrap="nowrap">
          <IconLayoutGrid size={20} color="var(--mantine-color-teal-4)" />
          <Text fw={600}>My deep-sky wall</Text>
        </Group>
        <Text size="sm" c="dimmed">
          {`Your ${shown} best finished pictures on one canvas, each labelled with `}
          {"its target and how long you spent on it — one image to post instead "}
          {"of a dozen."}
          {heroes.length > shown
            ? ` (You have ${heroes.length} finished, so this shows the ${shown} you've`
              + " given the most time to.)"
            : ""}
        </Text>
        <Group gap="xs">
          <Button size="xs" color="teal" leftSection={<IconDownload size={14} />}
            component="a" href={api.galleryMontageUrl(WALL_TILES)} download>
            Download wall
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
