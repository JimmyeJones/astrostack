/**
 * "Your year under the stars" — one calendar year of imaging, on its own page.
 *
 * The app already had both ends of the time axis and nothing in between: a
 * *night* ("Last night"), and the *whole hobby* ("Your sky, so far"). This is
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
  defaultRecapYear, recapYearOptions, yearNightCards, yearTargetCards,
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
  const nightCards = yearNightCards(
    data.longest_night, data.sharpest_night, formatIntegration);
  const targetCards = yearTargetCards(
    data.year, data.target_names, data.first_lights);

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

          {/* One card when the year's longest night was also its sharpest —
              which a short season usually makes true, and a one-standout year
              always does. `yearNightCards` keeps both figures on it. */}
          {nightCards.length > 0 ? (
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              {nightCards.map((c) => (
                <NightCard
                  key={c.key}
                  icon={c.key === "sharpest"
                    ? <IconMoonStars size={22} color="var(--mantine-color-teal-4)" />
                    : <IconClock size={22} color="var(--mantine-color-violet-4)" />}
                  title={c.title} lines={c.lines} />
              ))}
            </SimpleGrid>
          ) : null}

          {/* One card when everything the year pointed at was new — the same
              call `yearNightCards` makes above, for the same reason. */}
          {targetCards.map((card) => (
            <Card key={card.key} withBorder radius="md" padding="md"
              data-testid={card.key}>
              <Group gap="xs" mb="xs" wrap="nowrap">
                {card.highlight ? (
                  <IconSparkles size={18} color="var(--mantine-color-yellow-5)" />
                ) : null}
                <Text fw={600}>{card.title}</Text>
              </Group>
              {card.blurb ? (
                <Text size="xs" c="dimmed" mb="sm">{card.blurb}</Text>
              ) : null}
              <Group gap="xs">
                {card.chips.map((chip) => (
                  chip.safe ? (
                    <Badge key={chip.name} variant="light" size="lg"
                      component={Link} to={`/targets/${chip.safe}`}
                      style={{ cursor: "pointer" }}>
                      {chip.name}
                    </Badge>
                  ) : (
                    <Badge key={chip.name} size="lg"
                      variant={card.highlight ? "light" : "default"}
                      color={card.highlight ? "gray" : undefined}>
                      {chip.name}
                    </Badge>
                  )
                ))}
              </Group>
            </Card>
          ))}
        </>
      )}
    </Stack>
  );
}
