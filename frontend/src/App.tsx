import { AppShell, Badge, Box, Burger, Button, Group, NavLink, ScrollArea, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconActivity, IconPhoto, IconRadar2 } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink as RouterNavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { useEffect, useRef } from "react";
import type { Job } from "./api/client";
import { api } from "./api/client";
import { isJobNotifyEnabled, justFinishedJobs, showJobNotification } from "./jobNotify";
import { isNavActive } from "./navActive";
import { NAV_SECTIONS } from "./nav";
import { jobKindLabel } from "./routes/Jobs";
import { AmbientToggle } from "./components/AmbientToggle";

// Shows the running backend build, so you can confirm a rebuild actually took
// effect (the version bumps with each shipped change).
function AppVersion() {
  const { data } = useQuery({ queryKey: ["system"], queryFn: api.getSystem, staleTime: 60_000 });
  if (!data?.version) return null;
  return (
    <Text size="xs" c="dimmed" mt="md" px="sm">
      AstroStack v{data.version}
    </Text>
  );
}

// Always-mounted, route-independent "your job finished" watcher — slice (b) of the
// opt-in desktop-notification feature. The Jobs page (slice a) only fired while it
// was the mounted route, so a beginner who kicked off a stack and then browsed to
// the Target/Editor/Gallery page (a very common flow) wasn't told until they came
// back. This lives in the top-level layout, so a job finishing *anywhere* pings.
//
// It is the single place notifications fire (the Jobs page no longer does), so a
// job can't double-notify. The opt-in is read fresh from localStorage on every poll
// via `isJobNotifyEnabled()`, so the Jobs-page toggle (which writes that key)
// controls it with no shared React state — flip it on and the next poll starts
// firing; flip it off and firing stops. `justFinishedJobs` only fires on an
// in-progress→done/error transition, and the baseline is tracked every poll even
// while disabled, so enabling mid-session never bursts for already-finished jobs.
export function GlobalJobNotifier() {
  const { data } = useQuery({
    queryKey: ["jobs"],
    // Wrap so the default limit applies (a bare `api.listJobs` would receive the
    // TanStack query context as its `limit` argument).
    queryFn: () => api.listJobs(),
    // Gentler than the Jobs page's 1.5 s live poll; the always-mounted
    // ActiveJobsBadge already refreshes this shared query, so this adds no real load.
    refetchInterval: 8000,
  });
  const prevJobs = useRef<Job[]>([]);
  useEffect(() => {
    if (!data) return;
    if (isJobNotifyEnabled()) {
      for (const j of justFinishedJobs(prevJobs.current, data)) {
        showJobNotification(j, jobKindLabel(j.kind));
      }
    }
    prevJobs.current = data;
  }, [data]);
  return null;
}

function ActiveJobsBadge() {
  const { data } = useQuery({
    queryKey: ["jobs"],
    // Wrap so the default limit applies (a bare `api.listJobs` would receive the
    // TanStack query context as its `limit` argument).
    queryFn: () => api.listJobs(),
    refetchInterval: 2000,
  });
  const active = (data ?? []).filter((j) => j.state === "running" || j.state === "queued").length;
  if (!active) return null;
  return (
    <Badge color="violet" variant="filled" leftSection={<IconActivity size={12} />}>
      {active} running
    </Badge>
  );
}

// After an in-place upgrade, some targets' images were made by an older engine
// version. Surface a small count badge on the Settings link so the user is nudged
// to reprocess without having to go looking — the reprocess control lives there.
function OutdatedTargetsBadge() {
  const { data } = useQuery({
    queryKey: ["reprocess-status"],
    queryFn: api.reprocessStatus,
    staleTime: 60_000,
  });
  const outdated = data?.outdated ?? 0;
  if (outdated <= 0) return null;
  return (
    <Badge color="grape" variant="light" size="sm" aria-label={`${outdated} targets out of date`}>
      {outdated}
    </Badge>
  );
}

export function App() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  // Mobile navbar drawer. On desktop the navbar is always shown (see AppShell
  // navbar.collapsed below); this only toggles the mobile overlay.
  const [navOpened, { toggle: toggleNav, close: closeNav }] = useDisclosure(false);

  const scan = useMutation({
    mutationFn: api.scan,
    onSuccess: () => {
      notifications.show({ message: "Scan started — watching for new frames", color: "violet" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      navigate("/jobs");
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !navOpened, desktop: false } }}
      padding={{ base: "sm", sm: "md" }}
    >
      <AppShell.Header>
        <Group h="100%" px={{ base: "sm", sm: "md" }} justify="space-between" wrap="nowrap" gap="xs">
          <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
            <Burger opened={navOpened} onClick={toggleNav} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <IconPhoto size={26} color="var(--mantine-color-violet-4)" style={{ flexShrink: 0 }} />
            <Title order={3} style={{ whiteSpace: "nowrap" }}>AstroStack</Title>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <ActiveJobsBadge />
            <AmbientToggle />
            <Button
              leftSection={<IconRadar2 size={16} />}
              onClick={() => scan.mutate()}
              loading={scan.isPending}
              variant="light"
              aria-label="Scan incoming"
              px={{ base: "xs", xs: "md" }}
            >
              <Box visibleFrom="xs">Scan incoming</Box>
            </Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <ScrollArea>
          {/* IA slice (d): the same 15 destinations, under plain-language headings.
              Nothing collapses — the headings only make the list scannable. */}
          {NAV_SECTIONS.map((section, i) => {
            const headingId = section.title ? `nav-section-${i}` : undefined;
            return (
              <Box key={section.title ?? "home"} role="group" aria-labelledby={headingId} mb={4}>
                {section.title && (
                  <Text id={headingId} size="xs" tt="uppercase" fw={700} c="dimmed" px="sm" mt="sm" mb={4}>
                    {section.title}
                  </Text>
                )}
                {section.links.map((l) => (
                  <NavLink
                    key={l.to}
                    component={RouterNavLink}
                    to={l.to}
                    end={l.end}
                    label={l.label}
                    leftSection={l.icon}
                    rightSection={l.to === "/settings" ? <OutdatedTargetsBadge /> : undefined}
                    onClick={closeNav}
                    active={isNavActive(location.pathname, l.to, l.end)}
                  />
                ))}
              </Box>
            );
          })}
          <Text size="xs" c="dimmed" mt="lg" px="sm">
            Drop Seestar folders into the watched dataset; processing runs automatically.
          </Text>
          <AppVersion />
        </ScrollArea>
      </AppShell.Navbar>

      <AppShell.Main>
        <GlobalJobNotifier />
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
