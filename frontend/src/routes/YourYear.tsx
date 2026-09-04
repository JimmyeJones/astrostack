/**
 * "Your year under the stars" — one calendar year of imaging, on its own page.
 *
 * The app already had both ends of the time axis and nothing in between: a
 * *night* ("Last session"), and the *whole hobby* ("Your sky, so far"). This is
 * the middle — the season a beginner actually wants to look back on in January
 * and show someone.
 *
 * It is a nested route under "Your sky, so far" (`/sky-so-far/:year`) rather
 * than a new nav entry: the sidebar keeps its grouping, and the year stays
 * bookmarkable. Everything on it is read-only recall of nights the app already
 * folded for the Dashboard heatmap, so it costs no extra library walk.
 */
import {
  Anchor, Badge, Button, Card, Center, Group, Loader, Paper, SimpleGrid, Stack,
  Text, Title,
} from "@mantine/core";
import {
  IconArrowLeft, IconCalendarStar, IconClock, IconMoonStars, IconSparkles,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { QueryError } from "../components/QueryError";
import { YearShareCard } from "../components/YearShareCard";
import { formatIntegration } from "../format";
import {
  defaultRecapYear, longestNightLines, recapYearOptions, sharpestNightLines,
} from "../yourYear";

function StatCard({ value, label }: { value: string; label: string }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Text fw={700} size="xl" lh={1.2}>{value}</Text>
      <Text size="xs" c="dimmed">{label}</Text>
    </Paper>
  );
}

function NightCard({ icon, title, lines }: {
  icon: React.ReactNode;
  title: string;
  lines: { date: string; value: string; detail: string };
}) {
  return (
    <Paper withBorder p="md" radius="md">
      <Group gap="sm" wrap="nowrap">
        <Center w={40} h={40} bg="dark.6" style={{ borderRadius: 8, flexShrink: 0 }}>
          {icon}
        </Center>
        <div style={{ minWidth: 0 }}>
          <Text size="xs" c="dimmed">{title} · {lines.date}</Text>
          <Text fw={700} size="lg" lh={1.2}>{lines.value}</Text>
          <Text size="xs" c="dimmed">{lines.detail}</Text>
        </div>
      </Group>
    </Paper>
  );
}

export function YourYearView() {
  const { year: yearParam } = useParams();
  const thisYear = new Date().getFullYear();
  // A missing or unreadable `:year` is a link into "my most recent year", not an
  // error — so the page asks for the current one and, once the answer names the
  // years that have data, offers the newest of them.
  const parsed = Number(yearParam);
  const year = Number.isInteger(parsed) && parsed >= 1900 && parsed <= 2999
    ? parsed : thisYear;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["year-recap", year],
    queryFn: () => api.getYearRecap(year),
    staleTime: 60_000,
  });

  if (isError && !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }
  if (isLoading || !data) {
    return <Center h={300}><Loader /></Center>;
  }

  const years = recapYearOptions(data);
  const suggested = defaultRecapYear(data.years_with_data, thisYear);
  const longest = longestNightLines(data.longest_night, formatIntegration);
  const sharpest = sharpestNightLines(data.sharpest_night);

  return (
    <Stack gap="md">
      <div>
        <Anchor component={Link} to="/sky-so-far" size="sm" c="dimmed">
          <Group gap={4} wrap="nowrap">
            <IconArrowLeft size={14} /> Your sky, so far
          </Group>
        </Anchor>
        <Title order={2}>Your {data.year} under the stars</Title>
        {data.has_anything ? (
          <Text c="dimmed" size="sm">{data.headline}</Text>
        ) : null}
      </div>

      {years.length > 1 ? (
        <Group gap="xs" data-testid="year-picker">
          {years.map((y) => (
            <Button
              key={y} size="compact-sm" component={Link} to={`/sky-so-far/${y}`}
              variant={y === data.year ? "filled" : "default"}>
              {y}
            </Button>
          ))}
        </Group>
      ) : null}

      {!data.has_anything ? (
        <Card withBorder padding="xl" data-testid="year-empty">
          <Stack align="center" gap="sm">
            <IconCalendarStar size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed" ta="center">{data.empty_message}</Text>
            {suggested !== data.year ? (
              <Button component={Link} to={`/sky-so-far/${suggested}`}
                variant="light" size="compact-sm">
                See {suggested} instead
              </Button>
            ) : (
              <Text component={Link} to="/library" size="sm" c="violet">
                Go to Library →
              </Text>
            )}
          </Stack>
        </Card>
      ) : (
        <>
          <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
            {data.stats.map((s) => (
              <StatCard key={s.label} value={s.value} label={s.label} />
            ))}
          </SimpleGrid>

          <YearShareCard year={data.year} caption={data.caption}
            hero={data.hero} />

          {(longest || sharpest) ? (
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              {longest ? (
                <NightCard
                  icon={<IconClock size={22} color="var(--mantine-color-violet-4)" />}
                  title="Longest night" lines={longest} />
              ) : null}
              {sharpest ? (
                <NightCard
                  icon={<IconMoonStars size={22} color="var(--mantine-color-teal-4)" />}
                  title="Sharpest night" lines={sharpest} />
              ) : null}
            </SimpleGrid>
          ) : null}

          {data.first_lights.length > 0 ? (
            <Card withBorder radius="md" padding="md" data-testid="first-lights">
              <Group gap="xs" mb="xs" wrap="nowrap">
                <IconSparkles size={18} color="var(--mantine-color-yellow-5)" />
                <Text fw={600}>
                  First light in {data.year}
                </Text>
              </Group>
              <Text size="xs" c="dimmed" mb="sm">
                {data.first_lights.length === 1
                  ? "One object you'd never imaged before."
                  : `${data.first_lights.length} objects you'd never imaged before.`}
              </Text>
              <Group gap="xs">
                {data.first_lights.map((f) => (
                  f.safe ? (
                    <Badge key={f.name} variant="light" size="lg"
                      component={Link} to={`/targets/${f.safe}`}
                      style={{ cursor: "pointer" }}>
                      {f.name}
                    </Badge>
                  ) : (
                    <Badge key={f.name} variant="light" size="lg" color="gray">
                      {f.name}
                    </Badge>
                  )
                ))}
              </Group>
            </Card>
          ) : null}

          {data.target_names.length > 0 ? (
            <Card withBorder radius="md" padding="md" data-testid="year-targets">
              <Text fw={600} mb="xs">What you pointed at</Text>
              <Group gap="xs">
                {data.target_names.map((n) => (
                  <Badge key={n} variant="default" size="lg">{n}</Badge>
                ))}
              </Group>
            </Card>
          ) : null}
        </>
      )}
    </Stack>
  );
}
