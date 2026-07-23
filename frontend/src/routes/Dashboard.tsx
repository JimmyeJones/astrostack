import {
  ActionIcon, Alert, Badge, Box, Button, Card, Center, Group, Image, Loader, Menu, Paper,
  SimpleGrid, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import {
  IconActivity, IconClock, IconLayoutGrid, IconPhoto, IconPhotoDown, IconStack2, IconStars,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { formatIntegration } from "../format";
import { astapReadiness, astapReadinessSignature } from "../components/dashboard/astapReadiness";
import { folderReadiness, folderReadinessSignature } from "../components/dashboard/folderReadiness";
import { LastNightCard } from "../components/LastNightCard";
import { LibraryProgressCard } from "../components/LibraryProgressCard";
import { QueryError } from "../components/QueryError";
import { SuggestTargetsCard } from "../components/SuggestTargetsCard";
import { BestPicturesStrip } from "../components/BestPicturesStrip";

// Dismissal of the first-run readiness banners, keyed to the *specific* problem
// so dismissing one never suppresses a genuinely different (or returning) one:
// we store the current readiness *signature* rather than a bare boolean, and a
// banner reappears whenever the live signature differs from the dismissed one.
// A banner also self-clears once the problem is fixed (readiness → ready → no
// signature). localStorage-only and defensively guarded so a disabled/broken
// store never breaks the page.
const ASTAP_DISMISS_KEY = "astrostack.dashboard.astapBannerDismissed";
const FOLDER_DISMISS_KEY = "astrostack.dashboard.folderBannerDismissed";

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

function loadDismissedSig(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function saveDismissedSig(key: string, sig: string): void {
  try {
    localStorage.setItem(key, sig);
  } catch {
    /* storage unavailable — the banner just won't stay dismissed across reloads */
  }
}

function StatCard({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: string; sub?: string;
}) {
  return (
    <Paper withBorder p="md" radius="md">
      <Group gap="sm" wrap="nowrap">
        <Center w={40} h={40} bg="dark.6" style={{ borderRadius: 8, flexShrink: 0 }}>
          {icon}
        </Center>
        <div style={{ minWidth: 0 }}>
          <Text size="xs" c="dimmed">{label}</Text>
          <Text fw={700} size="lg" lh={1.2}>{value}</Text>
          {sub ? <Text size="xs" c="dimmed">{sub}</Text> : null}
        </div>
      </Group>
    </Paper>
  );
}

export function Dashboard() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["stats"], queryFn: api.getStats, refetchInterval: 10_000,
  });
  const system = useQuery({ queryKey: ["system"], queryFn: api.getSystem, staleTime: 60_000 });
  const [astapDismissedSig, setAstapDismissedSig] = useState(() => loadDismissedSig(ASTAP_DISMISS_KEY));
  const [folderDismissedSig, setFolderDismissedSig] = useState(() => loadDismissedSig(FOLDER_DISMISS_KEY));

  const solve = astapReadiness(system.data?.astap);
  const folders = folderReadiness(system.data?.folders);
  const astapSig = astapReadinessSignature(solve);
  const folderSig = folderReadinessSignature(folders);

  if (isError && !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }
  if (isLoading || !data) {
    return <Center h={300}><Loader /></Center>;
  }

  const accept = data.acceptance_rate == null ? "—" : `${Math.round(data.acceptance_rate * 100)}%`;
  const free = data.disk.free_gb != null ? `${data.disk.free_gb} GB` : "—";
  const usedSub = data.disk.total_gb != null ? `of ${data.disk.total_gb} GB` : undefined;

  return (
    <Stack>
      <Title order={2}>Dashboard</Title>

      {!solve.ready && astapSig !== astapDismissedSig ? (
        <Alert color="yellow" variant="light"
          withCloseButton
          onClose={() => {
            if (astapSig) { setAstapDismissedSig(astapSig); saveDismissedSig(ASTAP_DISMISS_KEY, astapSig); }
          }}
          title={solve.kind === "astap"
            ? "Plate-solving isn't set up yet"
            : "Plate-solving needs a star database"}>
          <Text size="sm">
            {solve.kind === "astap"
              ? "Solving gives every frame sky coordinates, and it's required before you "
                + "can stack anything. ASTAP (the plate-solver) wasn't found, so set it up "
                + "before you drop in frames."
              : "ASTAP was found, but it has no star database to match against — solving "
                + "needs one, and solving is required before you can stack. Add a star "
                + "database before you drop in frames."}
          </Text>
          <Button component={Link} to="/settings" size="xs" variant="light" color="yellow" mt="xs">
            Fix in Settings
          </Button>
        </Alert>
      ) : null}

      {!folders.ready && folderSig !== folderDismissedSig ? (
        <Alert color="yellow" variant="light"
          withCloseButton
          onClose={() => {
            if (folderSig) { setFolderDismissedSig(folderSig); saveDismissedSig(FOLDER_DISMISS_KEY, folderSig); }
          }}
          title={folders.kind === "incoming"
            ? (folders.problem === "missing"
              ? "Your incoming folder doesn't exist yet"
              : "Your incoming folder isn't writable")
            : (folders.problem === "missing"
              ? "Your library folder doesn't exist yet"
              : "Your library folder isn't writable")}>
          <Text size="sm">
            {folders.kind === "incoming"
              ? (folders.problem === "missing"
                ? "The folder you drop frames into can't be found — \"Scan incoming\" will "
                  + "find nothing until it exists. Check the folder is mounted and the path "
                  + "is right."
                : "The folder you drop frames into is read-only, so scanning it may fail. "
                  + "Check the folder's permissions or the path.")
              : (folders.problem === "missing"
                ? "The folder your stacks and library are written to can't be found — "
                  + "processing will fail until it exists. Check the folder is mounted and "
                  + "the path is right."
                : "The folder your stacks and library are written to is read-only, so "
                  + "processing can't save its results. Check the folder's permissions or "
                  + "the path.")}
          </Text>
          <Button component={Link} to="/settings" size="xs" variant="light" color="yellow" mt="xs">
            Fix in Settings
          </Button>
        </Alert>
      ) : null}

      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
        <StatCard icon={<IconStars size={22} color="var(--mantine-color-violet-4)" />}
          label="Targets" value={String(data.n_targets)}
          sub={`${data.n_targets_with_stacks} stacked`} />
        <StatCard icon={<IconClock size={22} color="var(--mantine-color-violet-4)" />}
          label="Integration" value={formatIntegration(data.integration_hours * 3600)} />
        <StatCard icon={<IconPhoto size={22} color="var(--mantine-color-violet-4)" />}
          label="Frames" value={String(data.n_frames)}
          sub={`${data.n_frames_accepted} kept · ${accept}`} />
        <StatCard icon={<IconStack2 size={22} color="var(--mantine-color-violet-4)" />}
          label="Stacks" value={String(data.n_stack_runs)} />
        <StatCard icon={<IconActivity size={22} color="var(--mantine-color-violet-4)" />}
          label="Active jobs" value={String(data.active_jobs)} />
        <StatCard icon={<IconLayoutGrid size={22} color="var(--mantine-color-violet-4)" />}
          label="Free disk" value={free} sub={usedSub} />
      </SimpleGrid>

      <LastNightCard />

      <LibraryProgressCard />

      <SuggestTargetsCard />

      <BestPicturesStrip />

      <Group justify="space-between" mt="sm">
        <Title order={4}>Recent stacks</Title>
        <Text component={Link} to="/gallery" size="sm" c="violet">View gallery →</Text>
      </Group>

      {data.recent_stacks.length === 0 ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <IconStack2 size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">No stacks yet. Stack a target to see it here.</Text>
            <Text component={Link} to="/library" size="sm" c="violet">Go to Library →</Text>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, xs: 2, sm: 3, lg: 4 }}>
          {data.recent_stacks.map((s) => (
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
                          <Menu.Item onClick={() => triggerPictureDownload(
                            api.stackArtifactUrl(s.safe, s.run_id, "preview"))}>
                            PNG (best quality)
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
                <Badge variant="light" color="violet">{s.n_frames_used} frames</Badge>
                <Text size="xs" c="dimmed">{s.timestamp_utc.slice(0, 10)}</Text>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
