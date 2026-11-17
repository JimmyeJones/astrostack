import {
  ActionIcon, Box, Card, Center, Group, Image, Menu, SimpleGrid, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import { IconPhotoDown, IconStack2 } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { DashboardStats } from "../../api/client";
import { announceFullResDownload, fullResPngLabel } from "../../fullres";
import { pictureDateLabel } from "../../format";
import { BestPicturesStrip } from "../BestPicturesStrip";
import { ImagingLogButton } from "../ImagingLogButton";
import { InsightTabs } from "../InsightTabs";
import { FrameCountBadge } from "../target/FrameCountBadge";

// Trigger a picture download without navigating: the recent-stack card is itself
// a <Link>, so we can't nest a download <a> inside it. Programmatically click a
// transient anchor instead (the endpoint serves a Content-Disposition attachment,
// so this saves the PNG rather than opening it).
export function triggerPictureDownload(href: string): void {
  const a = document.createElement("a");
  a.href = href;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** The newest finished pictures, newest first, each one a link to its History
 * page with a download menu on the thumbnail — or a plain pointer to the
 * Library while there are none yet. */
function NewestPictures({ stacks }: { stacks: DashboardStats["recent_stacks"] }) {
  return (
    <>
      {stacks.length === 0 ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <IconStack2 size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">No stacks yet. Stack a target to see it here.</Text>
            <Text component={Link} to="/library" size="sm" c="violet">Go to Library →</Text>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, xs: 2, sm: 3, lg: 4 }}>
          {stacks.map((s) => (
            <Card key={`${s.safe}-${s.run_id}`} withBorder padding="sm" radius="md"
              component={Link} to={`/targets/${s.safe}/history`}>
              <Card.Section>
                {s.has_preview ? (
                  <Box style={{ position: "relative" }}>
                    <Image src={s.preview_url} h={140} alt={s.target_name} />
                    {/* The card is a <Link>; a wrapper stops every click inside
                        the menu (trigger *and* the portalled dropdown, which
                        bubbles through the React tree) from navigating. Guarding
                        here rather than on the trigger keeps the trigger's onClick
                        free for Mantine's open-menu handler. */}
                    <Box
                      style={{ position: "absolute", top: 6, right: 6 }}
                      onClick={(e) => { e.stopPropagation(); }}
                    >
                      <Menu shadow="md" position="bottom-end" withinPortal>
                        <Menu.Target>
                          <Tooltip label="Download this picture (PNG or JPEG)">
                            <ActionIcon
                              variant="filled" color="dark" radius="xl"
                              aria-label={`Download picture of ${s.target_name}`}
                              style={{ opacity: 0.85 }}
                            >
                              <IconPhotoDown size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Menu.Target>
                        <Menu.Dropdown>
                          {s.has_fits ? (
                            <Menu.Item onClick={() => {
                              announceFullResDownload(s.canvas_w, s.canvas_h);
                              triggerPictureDownload(api.stackFullResPngUrl(s.safe, s.run_id));
                            }}>
                              {fullResPngLabel(s.canvas_w, s.canvas_h)}
                            </Menu.Item>
                          ) : null}
                          <Menu.Item onClick={() => triggerPictureDownload(
                            api.stackArtifactUrl(s.safe, s.run_id, "preview"))}>
                            {s.has_fits ? "Quick preview PNG (up to 1024px)" : "PNG (best quality)"}
                          </Menu.Item>
                          <Menu.Item onClick={() => triggerPictureDownload(
                            api.stackArtifactUrl(s.safe, s.run_id, "jpeg"))}>
                            JPEG (smaller — best for sharing)
                          </Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
                    </Box>
                  </Box>
                ) : (
                  <Center h={140} bg="dark.6">
                    <IconStack2 size={36} color="var(--mantine-color-dark-3)" />
                  </Center>
                )}
              </Card.Section>
              <Text fw={600} mt="xs" lineClamp={1}>{s.target_name}</Text>
              <Group justify="space-between" mt={4}>
                <FrameCountBadge
                  nFramesUsed={s.n_frames_used}
                  fieldFulls={s.field_fulls}
                  color="violet"
                />
                {/* The picture's date, and *which* date it is. This used to be
                    a bare stamp — and it was the run's own, i.e. when the stack
                    ran, which anyone reads as the night they shot it. On a
                    re-stack of a back catalogue that is out by years, on the
                    app's front page. It now prefers the night the subs were
                    taken, and says "Stacked" when that is all the run knows.
                    (A raw `slice(0, 10)` before that printed the *UTC* calendar
                    day, tomorrow's date for an evening stack west of UTC.) */}
                <Text size="xs" c="dimmed">
                  {pictureDateLabel(
                    s.capture_night_start, s.capture_night_end, s.timestamp_utc,
                    s.capture_nights)}
                </Text>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </>
  );
}

/**
 * "Your pictures" — the Dashboard's one picture group: the newest pictures and
 * the ones the app rates best, as two tabs of one section.
 *
 * Split out of `routes/Dashboard.tsx` for the owner's "recursive organization"
 * ask (2026-11-17). *Recent stacks* and *My best pictures* used to be two
 * headed sections one below the other — two of the page's then seven top-level
 * groups, both answering "show me my pictures". They now share one heading:
 * **Newest** opens first (it is what the old page led with), **Best** is one
 * click away, and the "View gallery", "View all" and imaging-log links are all
 * still here. `InsightTabs` gives a tab only to a group that has something to
 * show, so until there are two finished pictures to rank (the best-pictures
 * endpoint's own floor) there is no tab strip at all — just the newest ones.
 */
export function YourPictures({ stats }: { stats: DashboardStats }) {
  return (
    <Stack gap={0} data-dashboard-group="pictures">
      <Group justify="space-between" mt="sm">
        <Title order={4}>Your pictures</Title>
        <Group gap="lg">
          <ImagingLogButton nStacks={stats.n_stack_runs} />
          <Text component={Link} to="/gallery" size="sm" c="violet">View gallery →</Text>
        </Group>
      </Group>
      <InsightTabs
        data-testid="dashboard-pictures"
        groups={[
          { key: "newest", label: "Newest",
            node: <NewestPictures stacks={stats.recent_stacks} /> },
          { key: "best", label: "Best", node: <BestPicturesStrip showTitle={false} /> },
        ]}
      />
    </Stack>
  );
}
