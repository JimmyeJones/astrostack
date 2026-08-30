import { useState } from "react";
import {
  ActionIcon, Badge, Button, Card, Center, Group, Image, Loader, SimpleGrid, Stack,
  Text, Title, Tooltip,
} from "@mantine/core";
import { IconPlayerPlay, IconSparkles, IconStarFilled } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type BestPicture } from "../api/client";
import { formatStampDate } from "../format";
import { sharePictureText } from "../share";
import { ImageLightbox } from "../components/ImageLightbox";
import { WallpaperMenu } from "../components/WallpaperMenu";
import { QueryError } from "../components/QueryError";
import { bestPictureReason, pinnedNote } from "../components/bestPictures";
import { runSlideKey, showFromHref } from "../showAndTell";

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
          <Tooltip label={pinned} multiline w={280}>
            <Badge
              variant="filled" color="yellow" size="sm"
              leftSection={<IconStarFilled size={11} />}
              styles={{ root: { position: "absolute", top: 8, right: 8, zIndex: 2 } }}
            >
              Pinned
            </Badge>
          </Tooltip>
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
  const [viewing, setViewing] = useState<BestPicture | null>(null);

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
        {items.length > 0 ? (
          <Tooltip label="Your finest finished stacks across every target, picked automatically by total integration time, cleanliness, and frame count.">
            <Badge variant="light">{items.length}</Badge>
          </Tooltip>
        ) : null}
        {/* The entry point to the slideshow. It lives here rather than as a
            sixteenth sidebar link: this is the page you're already on when you
            want to show someone your pictures. */}
        <Button
          component={Link} to="/show" size="xs" variant="light" ml="auto"
          leftSection={<IconPlayerPlay size={14} />}
        >
          Play slideshow
        </Button>
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
                formatStampDate(viewing.timestamp_utc),
              );
              return { shareFilename: filename, shareTitle: title, shareText: text };
            })()
          : {})}
        onClose={() => setViewing(null)}
      />
    </Stack>
  );
}
