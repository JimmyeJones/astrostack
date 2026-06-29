import { AppShell, Badge, Box, Burger, Button, Group, NavLink, ScrollArea, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconActivity, IconDatabase, IconFileText, IconFlask, IconGauge, IconLayoutGrid, IconPhoto, IconRadar2, IconSettings, IconStars, IconTelescope } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink as RouterNavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api } from "./api/client";

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

function ActiveJobsBadge() {
  const { data } = useQuery({
    queryKey: ["jobs"],
    queryFn: api.listJobs,
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

  const links = [
    { to: "/", label: "Dashboard", icon: <IconGauge size={18} />, end: true },
    { to: "/library", label: "Library", icon: <IconStars size={18} /> },
    { to: "/telescope", label: "Telescope", icon: <IconTelescope size={18} /> },
    { to: "/gallery", label: "Gallery", icon: <IconLayoutGrid size={18} /> },
    { to: "/sky", label: "Sky Map", icon: <IconRadar2 size={18} /> },
    { to: "/jobs", label: "Jobs", icon: <IconActivity size={18} /> },
    { to: "/calibration", label: "Calibration", icon: <IconFlask size={18} /> },
    { to: "/storage", label: "Storage", icon: <IconDatabase size={18} /> },
    { to: "/logs", label: "Logs", icon: <IconFileText size={18} /> },
    { to: "/settings", label: "Settings", icon: <IconSettings size={18} /> },
  ];

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
          {links.map((l) => (
            <NavLink
              key={l.to}
              component={RouterNavLink}
              to={l.to}
              end={l.end}
              label={l.label}
              leftSection={l.icon}
              onClick={closeNav}
              active={l.end ? location.pathname === "/" : location.pathname.startsWith(l.to)}
            />
          ))}
          <Text size="xs" c="dimmed" mt="lg" px="sm">
            Drop Seestar folders into the watched dataset; processing runs automatically.
          </Text>
          <AppVersion />
        </ScrollArea>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
