import { Button, Card, Group, Stack, Text } from "@mantine/core";
import { IconDownload, IconFileZip, IconLayoutGrid } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/** How many pictures the wall holds. Matches the backend's default cap — past
 * roughly nine, each picture is too small to enjoy at social-media sizes, and
 * the point of the wall is the pictures, not the count. */
const WALL_TILES = 9;

/** "My deep-sky wall" — every finished target as one shareable picture, plus
 * the one tap that gets every picture out of the app.
 *
 * The gallery can only ever show one image at a time, so nothing in the app
 * says *"look at everything I've captured"* — and that montage is the thing a
 * beginner actually posts at the end of a good run of clear nights. The recap
 * poster next to this card shares the *numbers* over one hero image; this
 * shares the pictures themselves.
 *
 * Two audiences, one card. The **wall** is deep-sky targets only (that's what
 * the montage endpoint composes), so it needs two finished targets to be worth
 * anything. The **zip** is every picture you have — targets *and* finished
 * Moon/Sun stills — so it shows up for someone whose only pictures so far are
 * lunar ones, which for a Seestar owner is a very common first week.
 *
 * Self-hiding by contract: fewer than two pictures of any kind gets nothing at
 * all, because a "wall" of one is just the picture the gallery already shows
 * (the montage endpoint enforces the same floor with a 404). Nothing is
 * written — the montage is rendered on demand from previews the app already
 * keeps, exactly like the recap poster.
 */
export function MyDeepSkyWallCard() {
  const { data } = useQuery({
    queryKey: ["library-summary"], queryFn: api.getLibrarySummary,
    staleTime: 60_000,
  });

  const heroes = data?.heroes ?? [];
  const stills = data?.n_finished_stills ?? 0;
  // What "Download all" actually hands over: one picture per finished target,
  // plus every Moon/Sun still. Counting heroes alone under-promised.
  const total = heroes.length + stills;
  if (total < 2) return null;
  // The montage is composed from library targets only, so it needs two of those
  // — a stills-only library gets the zip without the wall.
  const canWall = heroes.length >= 2;

  const shown = Math.min(heroes.length, WALL_TILES);
  return (
    <Card withBorder radius="md" padding="md">
      <Stack gap="xs">
        <Group gap="xs" wrap="nowrap">
          <IconLayoutGrid size={20} color="var(--mantine-color-teal-4)" />
          <Text fw={600}>{canWall ? "My deep-sky wall" : "My pictures"}</Text>
        </Group>
        <Text size="sm" c="dimmed">
          {canWall
            ? `Your ${shown} best finished pictures on one canvas, each labelled with `
              + "its target and how long you spent on it — one image to post instead "
              + "of a dozen."
            : "Every picture you've finished so far, in one download — to back up "
              + "or drop into a phone album."}
          {canWall && heroes.length > shown
            ? ` (You have ${heroes.length} finished, so this shows the ${shown} you've`
              + " given the most time to.)"
            : ""}
        </Text>
        <Group gap="xs">
          {canWall && (
            <Button size="xs" color="teal" leftSection={<IconDownload size={14} />}
              component="a" href={api.galleryMontageUrl(WALL_TILES)} download>
              Download wall
            </Button>
          )}
          {/* The other half of "get my pictures out": the pictures themselves
              rather than a montage of them. Sits in this card rather than adding
              a block to the page — it's the same moment, one tap along. */}
          <Button size="xs" variant={canWall ? "light" : "filled"} color="teal"
            leftSection={<IconFileZip size={14} />}
            component="a" href={api.galleryPicturesZipUrl()} download>
            {`Download all ${total} pictures`}
          </Button>
        </Group>
        <Text size="xs" c="dimmed">
          {canWall
            ? "The wall is one image to post. \"Download all\" gives you the "
              + "pictures themselves in a zip — "
            : "\"Download all\" gives you the pictures themselves in a zip — "}
          {stills > 0
            ? "one per target plus every Moon and Sun picture you've stacked, each "
              + "named for it — to back up or drop into a phone album."
            : "one per target, named for it — to back up or drop into a phone album."}
          {" "}
          {/* Said plainly, because the zip holds each target's stored *preview*
              (`_write_preview_png` caps it at 1024 px), and this line used to
              call them "the full-size pictures themselves". Someone who backs
              their season up and later tries to print from it would find that
              out at the worst possible moment. */}
          Each one is the picture at the size you see it here — right for a phone
          album, not for printing. To print one, open it and choose
          "Full-res PNG".
        </Text>
      </Stack>
    </Card>
  );
}
