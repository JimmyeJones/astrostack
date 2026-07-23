import { Card, Group, Image, SimpleGrid, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { bestPictureReason } from "./bestPictures";

// How many pictures the Dashboard strip previews — a distilled taste of the full
// "My best pictures" wall, not the whole thing.
const STRIP_LIMIT = 4;

/** A compact, self-hiding "My best pictures" strip for the Dashboard: the top few
 * auto-ranked finished stacks across every target, linking through to the full
 * wall. Renders nothing until the wall has something worth showing (the endpoint
 * self-hides below two finished pictures), so a new install sees no empty card. */
export function BestPicturesStrip() {
  const best = useQuery({
    queryKey: ["galleryBest", "strip"],
    queryFn: () => api.getGalleryBest(STRIP_LIMIT),
  });

  const items = best.data?.items ?? [];
  // Self-hide on load, error, or an empty/too-thin collection — never an empty card.
  if (best.isLoading || best.isError || items.length === 0) return null;

  return (
    <>
      <Group justify="space-between" mt="sm">
        <Title order={4}>My best pictures</Title>
        <Text component={Link} to="/best" size="sm" c="violet">View all →</Text>
      </Group>
      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        {items.map((pic) => {
          const reason = bestPictureReason(pic);
          return (
            <Card
              key={`${pic.safe}-${pic.run_id}`} withBorder padding="xs" radius="md"
              component={Link} to={`/targets/${pic.safe}/history`}
            >
              <Card.Section>
                <Image src={pic.preview_url} h={120} fit="contain" bg="#000"
                  alt={pic.target_name} />
              </Card.Section>
              <Text fw={600} size="sm" truncate mt={6}>{pic.target_name}</Text>
              {reason ? (
                <Text size="xs" c="dimmed" truncate title={reason}>{reason}</Text>
              ) : null}
            </Card>
          );
        })}
      </SimpleGrid>
    </>
  );
}
