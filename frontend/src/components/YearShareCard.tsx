import { Alert, Button, Card, Code, Group, Image, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCopy, IconDownload, IconPhotoStar } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import { api, type YearHero } from "../api/client";

/**
 * "Your year, as something you can post" — the shareable half of the year page.
 *
 * The year page tells the story; this is the part a beginner actually shows
 * someone: their own best picture from that year, a square poster of the year's
 * numbers rendered over it, and the caption to paste beside it. One card rather
 * than three, so a page the owner already calls busy doesn't grow another
 * always-on banner for each piece.
 *
 * The picture is the year's best target's *newest* stack, so when that target
 * was imaged in more than one year the backend hands us a `note` saying so —
 * shown verbatim, because a picture captioned as "your 2026" that quietly
 * contains 2025's light is exactly the kind of small dishonesty this app
 * doesn't do.
 */
export function YearShareCard({ year, caption, hero }: {
  year: number;
  caption?: string;
  hero?: YearHero | null;
}) {
  const copyCaption = async () => {
    if (!caption) return;
    try {
      await navigator.clipboard.writeText(caption);
      notifications.show({
        message: "Caption copied — paste it wherever you're sharing.", color: "teal",
      });
    } catch {
      // Clipboard blocked (insecure context / permissions) — show the caption so
      // the user can still select and copy it by hand, exactly like the
      // whole-library share card does.
      notifications.show({
        title: "Copy this caption", message: caption, color: "blue",
        autoClose: false,
      });
    }
  };

  return (
    <Card withBorder radius="md" padding="md" data-testid="year-share">
      <Group align="flex-start" gap="md" wrap="wrap">
        {hero?.thumbnail_url ? (
          <Stack gap={4} style={{ width: 180 }} data-testid="year-hero">
            <Image
              src={hero.thumbnail_url} alt={`Your picture of ${hero.name}`}
              radius="sm" h={180} w={180} fit="cover" />
            <Text size="sm" fw={600}>
              <Text component={Link} to={`/targets/${hero.safe}`} inherit c="violet">
                Your picture of {hero.name}
              </Text>
            </Text>
            <Text size="xs" c="dimmed">
              {hero.note
                ? hero.note
                : `Everything you shot of it was in ${year}.`}
            </Text>
          </Stack>
        ) : null}
        <Stack gap="xs" style={{ flex: 1, minWidth: 240 }}>
          <Group gap="xs" wrap="nowrap">
            <IconPhotoStar size={20} color="var(--mantine-color-violet-4)" />
            <Text fw={600}>Share your {year}</Text>
          </Group>
          <Text size="sm" c="dimmed">
            Your year as one picture you can post — the numbers above over your
            own best image of the year.
          </Text>
          {caption ? (
            <Alert variant="light" color="violet" p="xs">
              <Code style={{ whiteSpace: "pre-wrap", background: "transparent" }}>
                {caption}
              </Code>
            </Alert>
          ) : null}
          <Group gap="xs">
            <Button size="xs" leftSection={<IconDownload size={14} />}
              component="a" href={api.yearPosterUrl(year)} download>
              Download poster
            </Button>
            {caption ? (
              <Button size="xs" variant="light" leftSection={<IconCopy size={14} />}
                onClick={copyCaption}>
                Copy caption
              </Button>
            ) : null}
          </Group>
        </Stack>
      </Group>
    </Card>
  );
}
