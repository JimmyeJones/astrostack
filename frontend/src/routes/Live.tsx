import {
  Alert, Anchor, Badge, Card, Center, Group, Image, Loader, Progress, Select,
  Stack, Text, Title,
} from "@mantine/core";
import { IconAntenna, IconMoonStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, type LiveSession, type Target } from "../api/client";
import { QueryError } from "../components/QueryError";
import {
  alsoActiveTonight, conditionsCause, conditionsLine, freshnessLine, goalLine,
  mostRecentlyActive, sharpnessLine, tonightHeadline,
} from "../live/liveSession";
import { useKeepAwake } from "../useKeepAwake";

// How often to re-ask while the page is open. A capture night moves in minutes,
// not seconds, and the endpoint is a read-only aggregation over the frames table
// — but this page is meant to be left open on a phone for hours, so keep the
// poll gentle. The watcher's own ingest cadence is the real floor on how fresh
// the answer can be anyway.
const POLL_MS = 30_000;

const VERDICT_COLOR: Record<string, string> = {
  good: "teal",
  mixed: "yellow",
  poor: "orange",
  unknown: "gray",
};

/**
 * **"Tonight, live"** — how the session happening *right now* is going.
 *
 * The app could already tell you what to shoot (the Tonight planner) and what
 * last night gave you (the session recap), but had nothing for the hour you're
 * actually standing outside next to the Seestar. That's when the two questions
 * are *"is this actually working?"* and *"have I got enough to go inside?"* —
 * and the app knows both, live: the watcher QCs every sub within a minute or two
 * of it landing, so it holds each one's accept verdict and star size while the
 * night is still running. That's the differentiated bit; the Seestar's own
 * screen shows a preview, not whether the subs are any good.
 *
 * Zero navigation by design: it opens on whichever target's frames arrived most
 * recently, which on a capture night is the one filling up. `?target=<safe>`
 * pins a specific one (and is what the picker writes), so the view is
 * bookmarkable either way.
 *
 * Read-only throughout — it never starts a stack, never writes, and never nags.
 */
export function LiveView() {
  const [params, setParams] = useSearchParams();
  const pinned = params.get("target");

  const targets = useQuery({ queryKey: ["targets"], queryFn: api.listTargets });
  const auto = mostRecentlyActive(targets.data);
  const safe = pinned ?? auto?.safe_name ?? null;
  const target = (targets.data ?? []).find((t) => t.safe_name === safe) ?? null;

  const live = useQuery({
    queryKey: ["live-session", safe],
    queryFn: () => api.liveSession(safe!),
    enabled: !!safe,
    refetchInterval: POLL_MS,
  });

  // This page is meant to be propped up outdoors for hours, and a phone dimming
  // three minutes in is the whole reason you'd walk back over to it. Held only
  // while the session is still running, so a finished night lets the screen
  // sleep; the same best-effort helper the slideshow uses (see useKeepAwake).
  useKeepAwake(!!live.data?.active);

  if (targets.isError) {
    return <QueryError error={targets.error} onRetry={() => targets.refetch()} />;
  }
  if (targets.isLoading) return <Center h={300}><Loader /></Center>;

  const picker = (targets.data ?? []).length > 1 ? (
    <Select
      size="sm"
      label="Watching"
      data={(targets.data ?? []).map((t) => ({ value: t.safe_name, label: t.name }))}
      value={safe}
      onChange={(v) => setParams(v ? { target: v } : {})}
      allowDeselect={false}
      searchable
    />
  ) : null;

  return (
    // Mobile-first: one narrow column, big type, nothing that needs a wide
    // screen. This is read one-handed in the dark.
    <Stack gap="md" maw={560}>
      <Group gap="xs" wrap="nowrap">
        <IconAntenna size={22} />
        <Title order={3}>Tonight, live</Title>
      </Group>
      <Text size="sm" c="dimmed">
        How the session happening right now is going — the app checks every sub as
        it lands, so you don't have to wait until morning to know it's working.
      </Text>

      {picker}

      {!safe ? (
        <Alert color="gray" icon={<IconMoonStars size={18} />} title="Nothing captured yet">
          <Text size="sm">
            Once frames start arriving, this page will show the night filling up.
            Drop some subs in and they'll appear here within a minute or two.
          </Text>
        </Alert>
      ) : live.isError ? (
        <QueryError error={live.error} onRetry={() => live.refetch()} />
      ) : live.isLoading ? (
        <Center h={200}><Loader /></Center>
      ) : !live.data ? (
        <Alert color="gray" icon={<IconMoonStars size={18} />}
          title="No session to show yet">
          <Text size="sm">
            {target?.name ?? "This target"} has no subs with a capture time yet, so
            there's no night to follow. It'll appear here as soon as frames land.
          </Text>
        </Alert>
      ) : (
        <>
          <LiveCard safe={safe} name={target?.name ?? safe} live={live.data} />
          <AlsoTonight targets={targets.data} currentSafe={safe}
            onPick={(s) => setParams({ target: s })} />
        </>
      )}
    </Stack>
  );
}

/**
 * "You also shot these around the same time" — one line, only when it's true.
 *
 * The page opens on whichever target's frames arrived most recently, which is
 * right, but a Seestar that re-points mid-night (or a mosaic split across panels)
 * would otherwise leave the earlier target invisible unless the reader knows to
 * use the picker above. Costs no extra request: it reads the same target list the
 * page already loaded. Renders nothing when the night only had one target, which
 * is the common case.
 */
function AlsoTonight({ targets, currentSafe, onPick }: {
  targets: Target[] | undefined;
  currentSafe: string;
  onPick: (safe: string) => void;
}) {
  const others = alsoActiveTonight(targets, currentSafe);
  if (!others.length) return null;
  return (
    <Text size="sm" c="dimmed">
      Also shot around the same time:{" "}
      {others.map((t, i) => (
        <span key={t.safe_name}>
          {i ? ", " : ""}
          <Anchor component="button" type="button" inherit
            onClick={() => onPick(t.safe_name)}>
            {t.name}
          </Anchor>
        </span>
      ))}
    </Text>
  );
}

function LiveCard({ safe, name, live }: {
  safe: string;
  name: string;
  live: LiveSession;
}) {
  const cause = conditionsCause(live);
  const sharp = sharpnessLine(live);
  const goal = goalLine(live);
  const goalPct = live.goal_exposure_s && live.goal_exposure_s > 0
    ? Math.min(100, (live.total_kept_exposure_s / live.goal_exposure_s) * 100)
    : null;

  return (
    <Card withBorder radius="md" padding="md">
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text fw={600} size="lg" style={{ minWidth: 0 }}>
            <Link to={`/targets/${safe}`} style={{ color: "inherit" }}>{name}</Link>
          </Text>
          {/* The one-glance answer: is it still going? A finished session says so
              rather than pretending, so nobody stands outside watching a page
              that stopped updating hours ago. */}
          <Badge color={live.active ? "teal" : "gray"} variant="light">
            {live.active ? "Capturing" : "Finished"}
          </Badge>
        </Group>

        <Text size="xl" fw={700}>{tonightHeadline(live)}</Text>
        <Text size="xs" c="dimmed">{freshnessLine(live)}</Text>

        {/* "Is it working?" — the rolling read over the last handful of subs,
            which is what catches cloud rolling in after a great first half. */}
        <Alert
          color={VERDICT_COLOR[live.conditions.verdict] ?? "gray"}
          p="xs" variant="light"
        >
          <Text size="sm" fw={500}>{conditionsLine(live)}</Text>
          {cause ? <Text size="xs" mt={2}>{cause}</Text> : null}
          {sharp ? <Text size="xs" c="dimmed" mt={2}>{sharp}</Text> : null}
        </Alert>

        {/* "Have I got enough to go inside?" — only when a goal is set; the app
            never invents one. */}
        {goal ? (
          <Stack gap={4}>
            <Text size="sm">{goal}</Text>
            {goalPct != null ? (
              <Progress value={goalPct} size="sm" radius="xl"
                color={goalPct >= 100 ? "teal" : "blue"} />
            ) : null}
          </Stack>
        ) : null}

        {/* The freshest sub the app actually *kept* — proof, in a picture, that
            frames are landing and passing QC. Never one it just set aside. */}
        {live.newest_kept_frame_id != null ? (
          <Stack gap={4}>
            <Text size="xs" c="dimmed">Newest sub the app kept</Text>
            <Image
              src={api.framePreviewUrl(safe, live.newest_kept_frame_id, 640)}
              radius="sm" bg="#000" fit="contain" h={220}
              alt="The most recent accepted sub"
            />
          </Stack>
        ) : null}
      </Stack>
    </Card>
  );
}
