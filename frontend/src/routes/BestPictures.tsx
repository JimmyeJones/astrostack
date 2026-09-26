import { useState } from "react";
import {
  ActionIcon, Badge, Button, Card, Center, Group, Image, Loader, SimpleGrid, Stack,
  Text, Title, Tooltip,
} from "@mantine/core";
import { IconPlayerPlay, IconSparkles, IconStarFilled } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type BestPicture } from "../api/client";
import { formatCaptureNights } from "../format";
import { sharePictureText } from "../share";
import { ImageLightbox } from "../components/ImageLightbox";
import { storedPreviewScaleBar } from "../components/AnnotatedImage";
import { postCaptionForRun } from "../components/postCaption";
import { WallpaperMenu } from "../components/WallpaperMenu";
import { QueryError } from "../components/QueryError";
import { bestPictureReason, pinnedNote, rankingHint } from "../components/bestPictures";
import { hasAnythingToShow, runSlideKey, showFromHref } from "../showAndTell";
import { HintAnchor } from "../components/HintAnchor";

function BestCard({ pic, rank, onView }: {
  pic: BestPicture;
  rank: number;
  onView: (pic: BestPicture) => void;
}) {
  const reason = bestPictureReason(pic);
  const pinned = pinnedNote(pic);
  return (
    <Card withBorder padding="md" radius="md">
      <Card.Section style={{ position: "relative" }}>
        {/* A quiet rank chip for the top three — a gentle "these are your finest"
            cue without turning the wall into a leaderboard. */}
        {rank <= 3 ? (
          <Badge
            variant="filled" color="violet" size="sm"
            styles={{ root: { position: "absolute", top: 8, left: 8, zIndex: 2 } }}
          >
            #{rank}
          </Badge>
        ) : null}
        {/* The user's own pick. The score line can't explain why a favourite is
            sitting above a deeper stack, so say it on the picture itself. */}
        {pinned ? (
          <HintAnchor label={pinned} multiline w={280}>
            <Badge
              variant="filled" color="yellow" size="sm"
              leftSection={<IconStarFilled size={11} />}
              styles={{ root: { position: "absolute", top: 8, right: 8, zIndex: 2 } }}
            >
              Pinned
            </Badge>
          </HintAnchor>
        ) : null}
        <Tooltip label="Click to view fullscreen" openDelay={400}>
          <Image
            src={pic.preview_url} h={220} fit="contain" bg="#000"
            style={{ cursor: "zoom-in" }}
            onClick={() => onView(pic)}
          />
        </Tooltip>
      </Card.Section>

      <Group justify="space-between" mt="sm" wrap="nowrap">
        <Text fw={600} truncate component={Link} to={`/targets/${pic.safe}/history`}>
          {pic.target_name}
        </Text>
      </Group>
      {reason ? (
        <Text size="sm" c="dimmed" truncate title={reason}>
          {reason}
        </Text>
      ) : null}
    </Card>
  );
}

export function BestPicturesView() {
  const best = useQuery({ queryKey: ["galleryBest"], queryFn: () => api.getGalleryBest() });
  // The slideshow draws Moon/Sun stills as well as this wall, so whether it has
  // anything to play is not a question this page's own data can answer. Same
  // query key the show itself uses, so the two share one cached response.
  const gallery = useQuery({ queryKey: ["gallery"], queryFn: api.getGallery });
  const [viewing, setViewing] = useState<BestPicture | null>(null);
  // The run's stored-preview geometry, which decides whether the caption's
  // "N full Moons wide" sentence describes the picture being handed over or the
  // wider canvas behind it. Only on a FITS-backed run: the endpoint is a header
  // read and 404s without one, and a run with no FITS has no bar to place either.
  const viewingInfo = useQuery({
    queryKey: ["stack-info", viewing?.safe, viewing?.run_id],
    queryFn: () => api.stackRunInfo(viewing!.safe, viewing!.run_id),
    enabled: !!viewing?.has_fits,
    staleTime: Infinity,
  });
  // The bar itself comes from the annotations, on the same key and staleness the
  // Gallery viewer and the Target hero use — so a picture opened on one of those
  // pages has already paid for this one.
  const viewingAnnotations = useQuery({
    queryKey: ["annotations", viewing?.safe, viewing?.run_id],
    queryFn: () => api.stackAnnotations(viewing!.safe, viewing!.run_id),
    enabled: !!viewing?.has_fits,
    staleTime: Infinity,
  });
  // "My best pictures" is the page you open to show someone your pictures, and
  // its viewer was handing the OS share sheet the target's name and a date while
  // the same picture, shared from the Target page or History or the Gallery,
  // went out with its whole story. One builder, one sentence, every surface.
  //
  // The identity comes off the row rather than a per-picture lookup: the wall's
  // own endpoint already resolves the catalogue match to fill `object_type` and
  // `blurb`, so `object_id`/`object_name` ride along for nothing. An unmatched
  // target, or an older backend that sends neither, captions under the name the
  // wall shows — which is what this viewer did for every picture before.
  const viewingCaption = viewing
    ? postCaptionForRun(
        viewing,
        {
          id: viewing.object_id, name: viewing.object_name,
          type: viewing.object_type, blurb: viewing.blurb,
        },
        storedPreviewScaleBar(viewingAnnotations.data, viewingInfo.data ?? {}),
        viewing.target_name)
    : undefined;

  if (best.isError && !best.data) {
    return <QueryError error={best.error} onRetry={() => best.refetch()} />;
  }
  if (best.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }

  const items = best.data?.items ?? [];

  return (
    <Stack>
      <Group gap="xs">
        <IconSparkles size={24} />
        <Title order={2}>My best pictures</Title>
        {/* The hint's wording comes from `bestPictures.rankingHint` rather than
            being spelled here, because it is a claim about what
            `seestack.portfolio.rank_portfolio` blends — and it was wrong on
            both counts it could be (it named three of the four metrics, and
            called the leading one a *total* where the ranker reads it per
            pixel). One place owns it, and a mirror test holds the metric list to
            the scorer's own. */}
        {items.length > 0 ? (
          <HintAnchor label={rankingHint()} multiline w={320}>
            <Badge variant="light">{items.length}</Badge>
          </HintAnchor>
        ) : null}
        {/* The entry point to the slideshow. It lives here rather than as a
            sixteenth sidebar link: this is the page you're already on when you
            want to show someone your pictures.

            Shown only once something is known to be playable — on a fresh
            install this page is otherwise a paragraph saying your pictures will
            gather here later, under a primary-looking button that goes nowhere.
            `hasAnythingToShow` asks the show's own builder rather than this
            wall's length, because a first finished Moon still is a real show
            with an empty wall — and `n_finished` for the same reason pointing
            the other way: this wall is empty below two finished pictures, while
            the show plays from one, so `items` alone hid the button over a
            picture the beginner had just made. A failed gallery query is *unknown*, not empty,
            so the button stays: /show has a graceful "nothing to show yet"
            state, and hiding a working slideshow is the worse mistake. */}
        {hasAnythingToShow(items, gallery.data?.videos, best.data?.n_finished)
          || gallery.isError ? (
          <Button
            component={Link} to="/show" size="xs" variant="light" ml="auto"
            leftSection={<IconPlayerPlay size={14} />}
          >
            Play slideshow
          </Button>
        ) : null}
      </Group>

      {items.length === 0 ? (
        <Text c="dimmed">
          Once you've finished stacking a couple of targets, your best pictures
          will gather here automatically — a wall of your finest results across
          everything you've shot.
        </Text>
      ) : (
        <>
          <Text c="dimmed" size="sm">
            Your finest finished stacks, ranked automatically — deepest, cleanest
            first. Click any picture to view, download, or share it. Got a
            favourite the ranking missed? Open that target's History and press
            <b> Set as cover</b> — it'll show that picture here, always.
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3, lg: 4 }}>
            {items.map((pic, i) => (
              <BestCard
                key={`${pic.safe}-${pic.run_id}`} pic={pic} rank={i + 1}
                onView={setViewing}
              />
            ))}
          </SimpleGrid>
        </>
      )}

      <ImageLightbox
        src={viewing ? viewing.preview_url : null}
        title={viewing ? `${viewing.target_name} · ${viewing.output_basename}` : undefined}
        downloadHref={viewing?.has_preview
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "preview") : undefined}
        jpegHref={viewing?.has_preview
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "jpeg") : undefined}
        fullResHref={viewing?.has_fits
          ? api.stackFullResPngUrl(viewing.safe, viewing.run_id) : undefined}
        fullResCanvas={viewing ? { w: viewing.canvas_w, h: viewing.canvas_h } : undefined}
        rawHref={viewing?.has_fits
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "fits") : undefined}
        toolbarExtra={viewing?.has_preview
          ? (
            <Group gap={4} wrap="nowrap">
              {/* "Show me this one" — the slideshow already exists, but until now
                  it always began at the top of the ranked wall, so the picture
                  you were actually looking at was the last thing anyone saw. */}
              <Tooltip label="Start the slideshow on this picture">
                <ActionIcon
                  variant="subtle" color="gray" aria-label="Start the slideshow here"
                  component={Link} to={showFromHref(runSlideKey(viewing.safe, viewing.run_id))}
                >
                  <IconPlayerPlay size={18} />
                </ActionIcon>
              </Tooltip>
              <WallpaperMenu safe={viewing.safe} runId={viewing.run_id} variant="subtle" />
            </Group>
          ) : undefined}
        {...(viewing?.has_preview
          ? (() => {
              const { title, text, filename } = sharePictureText(
                viewing.target_name,
                formatCaptureNights(
                  viewing.capture_night_start, viewing.capture_night_end),
              );
              // Title and filename stay a short label and a slug; only the
              // caption is the full sentence.
              return {
                shareFilename: filename, shareTitle: title,
                shareText: viewingCaption ?? text,
              };
            })()
          : {})}
        onClose={() => setViewing(null)}
      />
    </Stack>
  );
}
