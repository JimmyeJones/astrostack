import { AppShell, Badge, Button, Group, NavLink, ScrollArea, Text, Title } from "@mantine/core";
import { IconActivity, IconPhoto, IconRadar2, IconSettings, IconStars } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink as RouterNavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api } from "./api/client";

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
    { to: "/", label: "Library", icon: <IconStars size={18} />, end: true },
    { to: "/jobs", label: "Jobs", icon: <IconActivity size={18} /> },
    { to: "/settings", label: "Settings", icon: <IconSettings size={18} /> },
  ];

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 240, breakpoint: "sm" }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <IconPhoto size={26} color="var(--mantine-color-violet-4)" />
            <Title order={3}>AstroStack</Title>
          </Group>
          <Group>
            <ActiveJobsBadge />
            <Button
              leftSection={<IconRadar2 size={16} />}
              onClick={() => scan.mutate()}
              loading={scan.isPending}
              variant="light"
            >
              Scan incoming
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
              active={l.end ? location.pathname === "/" : location.pathname.startsWith(l.to)}
            />
          ))}
          <Text size="xs" c="dimmed" mt="lg" px="sm">
            Drop Seestar folders into the watched dataset; processing runs automatically.
          </Text>
        </ScrollArea>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
