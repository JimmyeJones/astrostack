import { Button, Card, Group, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconDownload, IconFileZip, IconLayoutGrid, IconPhotoDown } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { pngProgressLabel } from "./editor/pngProgress";
import { isJobPollAbort, pollJobUntilDone } from "./editor/pollJob";

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

  // "Full-size pictures": the same pictures rendered at native resolution. It
  // cannot be a plain download link like the two above — nothing on disk holds a
  // target's full-size picture — so it starts a job, reports where it has got
  // to, and sends the browser to the finished file. Same shape as the editor's
  // full-res PNG button, which is the render this repeats per target.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const [fullProgress, setFullProgress] = useState<string | null>(null);
  const buildFullSize = useMutation({
    mutationFn: async () => {
      setFullProgress("Preparing…");
      const { job_id } = await api.startPicturesArchive();
      const job = await pollJobUntilDone(job_id, {
        getJob: api.getJob,
        isAbandoned: () => !mounted.current,
        failureMessage: "Preparing your pictures failed",
        onProgress: (j) => setFullProgress(pngProgressLabel(j)),
      });
      return { jobId: job_id, n: Number(job.result?.n_pictures) || 0 };
    },
    onSuccess: ({ jobId, n }) => {
      const a = document.createElement("a");
      a.href = api.galleryPicturesArchiveUrl(jobId);
      document.body.appendChild(a);
      a.click();
      a.remove();
      notifications.show({
        message: n > 0
          ? `${n} full-size pictures ready — your download is starting.`
          : "Your pictures are ready — the download is starting.",
        color: "teal",
      });
    },
    onError: (e: Error) => {
      if (!isJobPollAbort(e)) notifications.show({ message: e.message, color: "red" });
    },
    onSettled: () => setFullProgress(null),
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
          {/* The printable answer, next to the phone-album one. Separate rather
              than a size dropdown on the button above: this one takes minutes
              (every picture is re-rendered), and a download that silently
              becomes a wait is the surprise worth avoiding. */}
          <Button size="xs" variant="light" color="teal"
            leftSection={<IconPhotoDown size={14} />}
            loading={buildFullSize.isPending}
            onClick={() => buildFullSize.mutate()}>
            {fullProgress ?? "Full-size versions"}
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
          album, not for printing. For printing, "Full-size versions" makes the
          same pictures again at their true size; it takes a few minutes, because
          each one is rendered fresh.
        </Text>
      </Stack>
    </Card>
  );
}
