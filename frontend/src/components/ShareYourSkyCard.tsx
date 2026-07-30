import { Alert, Button, Card, Code, Group, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCopy, IconDownload, IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/** "Share your sky" — turn the whole-library recap into something postable.
 *
 * The numbers a hobbyist is quietly proud of already live on the "Your sky, so
 * far" page, but only as a web page nobody else can see. This card offers the
 * two things you actually need to show someone: a square poster (rendered
 * server-side over your own best picture) and the caption to post beside it.
 *
 * Self-hiding by contract: nothing rendered while loading, on an error, or on a
 * library that hasn't collected any light yet (`has_anything: false`) — the
 * page it sits on already has its own empty state, and an offer to share
 * nothing would be worse than silence.
 */
export function ShareYourSkyCard() {
  const { data } = useQuery({
    queryKey: ["library-recap"], queryFn: api.getLibraryRecap,
    staleTime: 60_000,
  });

  if (!data || !data.has_anything) return null;

  const copyCaption = async () => {
    try {
      await navigator.clipboard.writeText(data.caption);
      notifications.show({
        message: "Caption copied — paste it wherever you're sharing.", color: "teal",
      });
    } catch {
      // Clipboard blocked (insecure context / permissions) — show the caption so
      // the user can still select and copy it by hand, exactly like the
      // per-picture "Copy caption" does.
      notifications.show({
        title: "Copy this caption", message: data.caption, color: "blue",
        autoClose: false,
      });
    }
  };

  return (
    <Card withBorder radius="md" padding="md">
      <Stack gap="xs">
        <Group gap="xs" wrap="nowrap">
          <IconSparkles size={20} color="var(--mantine-color-violet-4)" />
          <Text fw={600}>Share your sky</Text>
        </Group>
        <Text size="sm" c="dimmed">
          Everything above, as one picture you can post — your own best image
          behind the numbers.
        </Text>
        {data.caption ? (
          <Alert variant="light" color="violet" p="xs">
            <Code style={{ whiteSpace: "pre-wrap", background: "transparent" }}>
              {data.caption}
            </Code>
          </Alert>
        ) : null}
        <Group gap="xs">
          <Button size="xs" leftSection={<IconDownload size={14} />}
            component="a" href={api.recapPosterUrl()} download>
            Download poster
          </Button>
          {data.caption ? (
            <Button size="xs" variant="light" leftSection={<IconCopy size={14} />}
              onClick={copyCaption}>
              Copy caption
            </Button>
          ) : null}
        </Group>
        {data.since ? <Text size="xs" c="dimmed">{data.since}</Text> : null}
      </Stack>
    </Card>
  );
}
