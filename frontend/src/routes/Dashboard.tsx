import {
  ActionIcon, Alert, Box, Button, Card, Center, Group, Image, Loader, Menu, Paper,
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
import { loadDismissedSig, saveDismissedSig } from "../dismissal";
import { astapReadiness, astapReadinessSignature } from "../components/dashboard/astapReadiness";
import { folderReadiness, folderReadinessSignature } from "../components/dashboard/folderReadiness";
import { ContinueTonightCard } from "../components/ContinueTonightCard";
import { FirstImageCard } from "../components/dashboard/FirstImageCard";
import { PointHereTonightCard } from "../components/dashboard/PointHereTonightCard";
import { UnexportedEditsNote } from "../components/dashboard/UnexportedEditsNote";
import { FrameCountBadge } from "../components/target/FrameCountBadge";
import { ImagingCalendarCard } from "../components/ImagingCalendarCard";
import { LastNightCard } from "../components/LastNightCard";
import { LibraryProgressCard } from "../components/LibraryProgressCard";
import { QueryError } from "../components/QueryError";
import { SampleImageCard } from "../components/SampleImageCard";
import { SuggestTargetsCard } from "../components/SuggestTargetsCard";
import { VideoCapturesCard } from "../components/VideoCapturesCard";
import { BestPicturesStrip } from "../components/BestPicturesStrip";
import { ImagingLogButton } from "../components/ImagingLogButton";
import { NoticeBoard, NOTICE_PRIORITY } from "../components/NoticeBoard";
import { InsightTabs } from "../components/InsightTabs";

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
      {/* Every setup problem this page can raise, in one prioritised area (IA
          slice (e); the same board the Target page uses). Both notes are
          self-hiding and separately dismissable, so the board measures which of
          them actually speaks and folds any surplus behind one line. A later
          Dashboard warning should join this board rather than become one more
          always-on banner. */}
      <NoticeBoard
        data-testid="dashboard-notes"
        items={[
          { key: "folders", priority: NOTICE_PRIORITY.blocking,
            node: !folders.ready && folderSig !== folderDismissedSig ? (
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
            ) : null },
          { key: "astap", priority: NOTICE_PRIORITY.warning,
            node: !solve.ready && astapSig !== astapDismissedSig ? (
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
            ) : null },
          // Advisory, and the reason this board exists: work of the user's that
          // the app isn't showing anywhere. Self-hiding at zero, so on an
          // ordinary install it costs nothing and the board folds nothing.
          { key: "unexported-edits", priority: NOTICE_PRIORITY.advisory,
            node: <UnexportedEditsNote /> },
        ]}
      />

      <Title order={2}>Dashboard</Title>

      {/* The positive first-run map: four plain steps from a folder of subs to a
          finished picture, each ticking itself off. Self-hides on an established
          install (every step already done on first render) and once dismissed.
          Kept above the fold on purpose: it is what orients a brand-new library. */}
      <FirstImageCard />

      <SampleImageCard />

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

      <Group justify="space-between" mt="sm">
        <Title order={4}>Recent stacks</Title>
        <Group gap="lg">
          <ImagingLogButton nStacks={data.n_stack_runs} />
          <Text component={Link} to="/gallery" size="sm" c="violet">View gallery →</Text>
        </Group>
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
                          {s.has_fits ? (
                            <Menu.Item onClick={() => triggerPictureDownload(
                              api.stackFullResPngUrl(s.safe, s.run_id))}>
                              Full-res PNG (native size)
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
                <FrameCountBadge nFramesUsed={s.n_frames_used} color="violet" />
                <Text size="xs" c="dimmed">{s.timestamp_utc.slice(0, 10)}</Text>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      )}

      {/* The pictures the app itself rates highest, right under the newest ones —
          both are "your pictures", so they belong together above the analysis. */}
      <BestPicturesStrip />

      {/* Everything that *describes* the library rather than showing it, grouped
          instead of stacked (IA slice (e), reusing the Target page's `InsightTabs`
          from slice (b)). Seven full-width cards used to sit one below another
          between the stat row and the pictures; they are all still here, still one
          click away, but only one group is on screen at a time — and a group whose
          cards have nothing to say gets no tab at all. A later Dashboard card
          should join a group here rather than become an eighth stacked card. */}
      <InsightTabs
        data-testid="dashboard-insights"
        groups={[
          { key: "tonight", label: "Tonight", node: (
            <>
              {/* "Point here right now": of the targets already started, which is
                  best-placed at this moment *and* would gain most from another
                  hour. Self-hides when there's nothing to recommend. */}
              <PointHereTonightCard />
              <ContinueTonightCard />
              <SuggestTargetsCard />
            </>
          ) },
          { key: "recent", label: "Recent", node: (
            <>
              <LastNightCard />
              <VideoCapturesCard />
            </>
          ) },
          { key: "progress", label: "Progress", node: (
            <>
              <LibraryProgressCard />
              <ImagingCalendarCard />
            </>
          ) },
        ]}
      />
    </Stack>
  );
}
