import { useState } from "react";
import {
  Badge, Card, Center, Group, Image, Loader, SimpleGrid, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import { IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type BestPicture } from "../api/client";
import { sharePictureText } from "../share";
import { ImageLightbox } from "../components/ImageLightbox";
import { WallpaperMenu } from "../components/WallpaperMenu";
import { QueryError } from "../components/QueryError";
import { bestPictureReason } from "../components/bestPictures";

function BestCard({ pic, rank, onView }: {
  pic: BestPicture;
  rank: number;
  onView: (pic: BestPicture) => void;
}) {
  const reason = bestPictureReason(pic);
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
            first. Click any picture to view, download, or share it.
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
        rawHref={viewing?.has_fits
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "fits") : undefined}
        toolbarExtra={viewing?.has_preview
          ? <WallpaperMenu safe={viewing.safe} runId={viewing.run_id} variant="subtle" /> : undefined}
        {...(viewing?.has_preview
          ? (() => {
              const { title, text, filename } = sharePictureText(
                viewing.target_name,
                new Date(viewing.timestamp_utc).toLocaleDateString(),
              );
              return { shareFilename: filename, shareTitle: title, shareText: text };
            })()
          : {})}
        onClose={() => setViewing(null)}
      />
    </Stack>
  );
}
