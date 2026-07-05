import {
  ActionIcon, Alert, Badge, Box, Button, Center, Grid, Group, HoverCard, Image,
  Loader, Modal, NumberFormatter, NumberInput, Paper, Select, Stack, Table,
  TagsInput, Text, Textarea, Title, Tooltip,
} from "@mantine/core";
import {
  IconAlertTriangle, IconArrowBackUp, IconCheck, IconDeviceFloppy, IconHistory,
  IconNotes, IconPhoto, IconSparkles, IconStack2, IconTelescope, IconWand, IconX,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api, type Frame } from "../api/client";
import { detectSolveSetupProblem } from "../components/target/solveSetup";

const NUM = (v: number | null, digits = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(digits);

type SortKey = "id" | "timestamp_utc" | "fwhm_px" | "star_count" | "eccentricity_median" | "sky_adu_median" | "transparency_score";

const REJECT_METRICS = [
  { value: "fwhm_px", label: "FWHM" },
  { value: "eccentricity_median", label: "Eccentricity" },
  { value: "star_count", label: "Star count" },
  { value: "sky_adu_median", label: "Sky level" },
  { value: "transparency_score", label: "Transparency" },
];

// Median of a non-empty numeric array (used for the within-target trailed
// eccentricity outlier count). Sorts a copy, so the input is left untouched.
function medianOf(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// Turn a raw `reject_reason` (qc:fwhm, bulk:streaked, user, …) into a plain-language
// label so a beginner can see *why* frames were dropped, not just how many.
const METRIC_LABEL: Record<string, string> = {
  fwhm_px: "FWHM", star_count: "star count",
  eccentricity_median: "eccentricity", sky_adu_median: "sky level",
  transparency_score: "transparency",
};
function rejectReasonLabel(reason: string): string {
  if (reason === "user") return "Manual reject";
  if (reason === "bulk:streaked") return "Streaked (bulk)";
  if (reason === "bulk:trailed") return "Trailed (bulk)";
  if (reason.startsWith("auto:grade:")) {
    const m = reason.slice(11);
    return `Auto-grade: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("qc:")) {
    const m = reason.slice(3);
    return `QC: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("bulk:")) {
    const m = reason.slice(5);
    return `Worst ${METRIC_LABEL[m] ?? m} (bulk)`;
  }
  if (reason === "auto:streak") return "Auto: streak";
  if (reason.startsWith("auto:")) {
    const m = reason.slice(5);
    return `Auto: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("qc_error")) return "QC error";
  if (reason.startsWith("solve_failed")) return "Plate-solve failed";
  return reason;
}

const SENSITIVITIES = [
  { value: "conservative", label: "Conservative — only gross outliers" },
  { value: "balanced", label: "Balanced (recommended)" },
  { value: "aggressive", label: "Aggressive — stricter cut" },
];

// Preview-first auto-grading: shows which accepted frames are statistical
// outliers (and why, in plain language) before anything is rejected.
function AutoGradeModal({
  safe, opened, onClose, onApplied,
}: {
  safe: string;
  opened: boolean;
  onClose: () => void;
  onApplied: (ids: number[]) => void;
}) {
  const [sensitivity, setSensitivity] = useState<string | undefined>(undefined);

  const preview = useQuery({
    queryKey: ["auto-grade", safe, sensitivity ?? "default"],
    queryFn: () => api.autoGradePreview(safe, sensitivity),
    enabled: opened,
  });

  const apply = useMutation({
    mutationFn: () => api.autoGradeApply(safe, sensitivity),
    onSuccess: (r) => {
      const ids = r.changed_ids ?? [];
      notifications.show({
        message: ids.length
          ? `Auto-grade rejected ${ids.length} frame${ids.length === 1 ? "" : "s"}`
          : "Nothing to reject — frames already graded",
        color: "violet",
      });
      onApplied(ids);
      onClose();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const report = preview.data;
  const recs = report?.recommendations ?? [];
  const nothingGradable = report && report.metrics_used.length === 0;

  return (
    <Modal opened={opened} onClose={onClose} title="Auto-grade frames" size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          Compares every accepted frame against this target's typical FWHM, star
          count, sky level, eccentricity and transparency, and flags the clear
          outliers — trailed, cloud-hit or hazy subs. Nothing is rejected until
          you apply, and one click undoes it.
        </Text>
        <Select
          label="Sensitivity" size="xs" w={280} allowDeselect={false}
          data={SENSITIVITIES}
          value={sensitivity ?? report?.sensitivity ?? "balanced"}
          onChange={(v) => setSensitivity(v ?? undefined)}
        />
        {preview.isLoading ? (
          <Center h={80}><Loader size="sm" /></Center>
        ) : preview.isError ? (
          <Alert color="red">{(preview.error as Error).message}</Alert>
        ) : nothingGradable ? (
          <Alert color="gray">
            Not enough graded frames to judge — run QC first (each metric needs
            at least 10 measured frames).
          </Alert>
        ) : recs.length === 0 ? (
          <Alert color="teal">
            No outliers found — your {report?.n_accepted ?? 0} accepted frames
            look consistent at this sensitivity.
          </Alert>
        ) : (
          <>
            <Text size="sm">
              <b>{recs.length}</b> of {report?.n_accepted} accepted frames look
              like outliers:
            </Text>
            {report?.capped ? (
              <Alert color="orange" p="xs">
                More frames were flagged than the 25% safety cap allows — only
                the worst are listed. Consider a conservative pass first, or
                review the night's data.
              </Alert>
            ) : null}
            <Table.ScrollContainer minWidth={400} mah={300}>
              <Table striped withTableBorder>
                <Table.Tbody>
                  {recs.map((rec) => (
                    <Table.Tr key={rec.frame_id}>
                      <Table.Td style={{ whiteSpace: "nowrap" }}>
                        <Text size="xs" fw={500}>{rec.name}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Stack gap={2}>
                          {rec.reasons.map((r) => (
                            <Text key={r.metric} size="xs" c="dimmed">{r.label}</Text>
                          ))}
                        </Stack>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </>
        )}
        <Group justify="flex-end">
          <Button variant="default" size="xs" onClick={onClose}>Cancel</Button>
          <Button
            size="xs" color="red" loading={apply.isPending}
            disabled={!recs.length}
            onClick={() => apply.mutate()}
          >
            Reject {recs.length || "0"} frame{recs.length === 1 ? "" : "s"}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function NotesPanel({ safe, notes, tags }: { safe: string; notes: string | null; tags: string[] }) {
  const qc = useQueryClient();
  const [noteText, setNoteText] = useState(notes ?? "");
  const [tagList, setTagList] = useState<string[]>(tags);

  // Re-sync when the loaded target changes (e.g. navigating between targets).
  useEffect(() => { setNoteText(notes ?? ""); setTagList(tags); }, [safe, notes, tags]);

  const save = useMutation({
    mutationFn: () => api.patchTarget(safe, { notes: noteText, tags: tagList }),
    onSuccess: () => {
      notifications.show({ message: "Notes saved", color: "teal" });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      qc.invalidateQueries({ queryKey: ["targets"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const dirty = noteText !== (notes ?? "") || tagList.join("\u0000") !== tags.join("\u0000");

  return (
    <Paper withBorder p="md">
      <Group gap={6} mb="xs">
        <IconNotes size={16} />
        <Text fw={600}>Notes &amp; tags</Text>
      </Group>
      <TagsInput
        label="Tags" placeholder="Add a tag…" value={tagList} onChange={setTagList}
        clearable mb="sm"
      />
      <Textarea
        label="Notes" placeholder="Acquisition notes, conditions, ideas…"
        autosize minRows={2} maxRows={8}
        value={noteText} onChange={(e) => setNoteText(e.currentTarget.value)}
      />
      <Group justify="flex-end" mt="sm">
        <Button size="xs" leftSection={<IconDeviceFloppy size={14} />}
          disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
          Save
        </Button>
      </Group>
    </Paper>
  );
}

export function TargetView() {
  const { safe = "" } = useParams();
  const qc = useQueryClient();
  const [sort, setSort] = useState<SortKey>("id");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [selected, setSelected] = useState<number | null>(null);
  const [bayer, setBayer] = useState<string | undefined>(undefined);
  const [rejectMetric, setRejectMetric] = useState("fwhm_px");
  const [rejectPct, setRejectPct] = useState(10);
  // Ids touched by the last bulk *reject* so we can offer a one-click undo of an
  // over-aggressive cut (a 30% reject_worst, or reject_streaked that went too far).
  const [lastReject, setLastReject] = useState<{ ids: number[]; label: string } | null>(null);
  const [gradeOpen, setGradeOpen] = useState(false);

  const target = useQuery({ queryKey: ["target", safe], queryFn: () => api.getTarget(safe) });
  const rejectedCount = target.data
    ? target.data.n_frames - target.data.n_frames_accepted
    : 0;
  // Only fetch the why-breakdown when there's something rejected to explain.
  const rejectSummary = useQuery({
    queryKey: ["reject-summary", safe],
    queryFn: () => api.rejectSummary(safe),
    enabled: rejectedCount > 0,
  });
  const frames = useQuery({
    queryKey: ["frames", safe, sort, order],
    queryFn: () => api.listFrames(safe, sort, order),
  });
  const runs = useQuery({ queryKey: ["runs", safe], queryFn: () => api.listStackRuns(safe) });
  const latestRun = runs.data?.[0];  // listStackRuns returns newest first

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.patchFrame(safe, id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["frames", safe] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
    },
  });

  const bulk = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.bulkFrames(safe, body),
    onSuccess: (r, body) => {
      notifications.show({ message: `Updated ${r.changed} frames`, color: "violet" });
      qc.invalidateQueries({ queryKey: ["frames", safe] });
      qc.invalidateQueries({ queryKey: ["target", safe] });  // accepted-count badge
      qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
      // Remember a bulk reject so the user can undo it; clear on the undo itself.
      const action = (body as { action?: string }).action;
      const ids = r.changed_ids ?? [];
      if (
        (action === "reject_worst" || action === "reject_streaked" ||
          action === "reject_trailed") && ids.length
      ) {
        const label =
          action === "reject_streaked" ? "streaked"
            : action === "reject_trailed" ? "trailed"
              : "worst-frame";
        setLastReject({ ids, label });
      } else {
        setLastReject(null);
      }
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const qcSolve = useMutation({
    mutationFn: () => api.qcSolve(safe),
    onSuccess: () => {
      notifications.show({ message: "QC + solve started", color: "violet" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  // Plate-solve *setup* problem (ASTAP or its star database not available) —
  // when present, every frame's solve fails identically, so the whole target's
  // frames pile up as "Plate-solve failed" with no hint that the fix is a
  // one-time setup step rather than dropping frames. Turn that into one
  // actionable banner. Null (the common case) renders nothing.
  const solveSetup = useMemo(
    () => detectSolveSetupProblem(rejectSummary.data?.counts),
    [rejectSummary.data],
  );

  const list = frames.data ?? [];
  // Accepted frames still carrying a streak flag (satellite/plane trail). With
  // "keep streaked frames" on, QC flags rather than rejects these, so per-pixel
  // rejection (sigma-clip / drizzle reject) can clean the trail while keeping
  // the frame's good signal. Surfacing the count tells the user at a glance what
  // that rejection will need to handle.
  const streakedAccepted = list.filter((f) => f.accept && f.streak_detected).length;
  // Accepted frames whose stars are a strong eccentricity outlier for this
  // target — a bad-tracking / wind / bumped-mount sub. A frame counts as
  // "trailed" only when its eccentricity is *both* a >3·MAD within-target
  // outlier *and* above an absolute floor of noticeably elongated stars, so a
  // uniformly round set never flags anything. Mirrors the server-side
  // `trailed_frame_ids` used by the reject_trailed bulk action; keep in sync.
  const trailedAccepted = useMemo(() => {
    const ecc = list
      .filter((f) => f.accept && f.eccentricity_median != null)
      .map((f) => f.eccentricity_median as number);
    if (ecc.length < 5) return 0;
    const med = medianOf(ecc);
    const mad = medianOf(ecc.map((v) => Math.abs(v - med)));
    const threshold = Math.max(med + 3 * mad, 0.6);
    return ecc.filter((v) => v > threshold).length;
  }, [list]);
  const selectedFrame = useMemo(
    () => list.find((f) => f.id === selected) ?? list[0],
    [list, selected],
  );

  // Keyboard grading: j/k or arrows to move, a to accept, r/x to reject. Skips
  // when typing in a field so notes/tags editing isn't hijacked.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || el?.isContentEditable) return;
      if (!list.length) return;
      const cur = selectedFrame;
      const idx = cur ? list.findIndex((f) => f.id === cur.id) : -1;
      switch (e.key) {
        case "ArrowDown":
        case "j": {
          e.preventDefault();
          const next = list[Math.min((idx < 0 ? -1 : idx) + 1, list.length - 1)];
          if (next) setSelected(next.id);
          break;
        }
        case "ArrowUp":
        case "k": {
          e.preventDefault();
          const prev = list[Math.max((idx < 0 ? 1 : idx) - 1, 0)];
          if (prev) setSelected(prev.id);
          break;
        }
        case "a":
          if (cur) { e.preventDefault(); patch.mutate({ id: cur.id, body: { accept: true } }); }
          break;
        case "r":
        case "x":
          if (cur) { e.preventDefault(); patch.mutate({ id: cur.id, body: { accept: false } }); }
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [list, selectedFrame, patch]);

  const setSortCol = (key: SortKey) => {
    if (sort === key) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setOrder("asc");
    }
  };

  if (target.isLoading) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const cols: { key: SortKey; label: string; hint?: string }[] = [
    { key: "timestamp_utc", label: "Time (UTC)" },
    {
      key: "fwhm_px", label: "FWHM",
      hint: "Full-width-half-maximum: how many pixels wide the stars are. "
        + "Lower = sharper. Rises with poor seeing, focus drift or clouds.",
    },
    {
      key: "star_count", label: "Stars",
      hint: "Number of stars detected in the frame. Drops on hazy or "
        + "cloud-affected subs. Higher is generally better.",
    },
    {
      key: "eccentricity_median", label: "Ecc.",
      hint: "Median star eccentricity (elongation): 0 = perfectly round, "
        + "closer to 1 = trailed. High values flag tracking error, wind or a "
        + "mount bump on that whole sub. Lower is better.",
    },
    {
      key: "sky_adu_median", label: "Sky",
      hint: "Median sky-background level of the frame. Rises with moonlight, "
        + "light pollution or thin cloud. Lower is darker (better).",
    },
    {
      key: "transparency_score", label: "Transp.",
      hint: "Transparency: median brightness of the frame's brightest stars. "
        + "Higher = clearer sky; low values flag haze or thin cloud. Relative, "
        + "comparable across this target's frames.",
    },
  ];

  return (
    <Stack>
      {solveSetup ? (
        <Alert color="orange" icon={<IconAlertTriangle size={18} />}
          title={solveSetup.kind === "astap"
            ? "Plate-solving isn't set up — ASTAP wasn't found"
            : "Plate-solving needs a star database"}>
          <Text size="sm">
            {solveSetup.kind === "astap"
              ? `${solveSetup.frames} frame${solveSetup.frames === 1 ? "" : "s"} couldn't be `
                + "plate-solved because ASTAP (the plate-solver) wasn't found. Frames need "
                + "sky coordinates before they can be stacked, so this blocks the whole "
                + "target. Install ASTAP and set its path in Settings, then re-run solving."
              : `${solveSetup.frames} frame${solveSetup.frames === 1 ? "" : "s"} couldn't be `
                + "plate-solved because ASTAP couldn't find a star database to match against. "
                + "Download an ASTAP star database (e.g. the D50/H17/H18 catalog) into ASTAP's "
                + "folder, then re-run solving."}
          </Text>
          <Group gap="xs" mt="xs">
            <Button size="xs" variant="filled" color="orange"
              loading={qcSolve.isPending} onClick={() => qcSolve.mutate()}>
              Re-run QC + Solve
            </Button>
            <Button size="xs" variant="light" color="orange"
              component={Link} to="/settings">
              Open Settings
            </Button>
          </Group>
        </Alert>
      ) : null}
      <Group justify="space-between" gap="xs">
        <Group gap="xs" style={{ minWidth: 0 }}>
          <Title order={2} style={{ wordBreak: "break-word" }}>{target.data?.name}</Title>
          <Badge variant="light" color="violet">
            {target.data?.n_frames_accepted}/{target.data?.n_frames} accepted
          </Badge>
          {rejectedCount > 0 ? (
            <HoverCard width={260} shadow="md" withArrow openDelay={100}>
              <HoverCard.Target>
                <Badge variant="light" color="gray" style={{ cursor: "help" }}>
                  {rejectedCount} rejected
                </Badge>
              </HoverCard.Target>
              <HoverCard.Dropdown>
                <Text size="sm" fw={600} mb={4}>Why frames were rejected</Text>
                {rejectSummary.data && Object.keys(rejectSummary.data.counts).length ? (
                  <Stack gap={2}>
                    {Object.entries(rejectSummary.data.counts)
                      .sort((a, b) => b[1] - a[1])
                      .map(([reason, n]) => (
                        <Group key={reason} justify="space-between" gap="xs">
                          <Text size="xs">{rejectReasonLabel(reason)}</Text>
                          <Text size="xs" fw={600}>{n}</Text>
                        </Group>
                      ))}
                  </Stack>
                ) : (
                  <Text size="xs" c="dimmed">
                    {rejectSummary.isLoading ? "Loading…" : "No breakdown available"}
                  </Text>
                )}
              </HoverCard.Dropdown>
            </HoverCard>
          ) : null}
          {lastReject ? (
            <Button
              size="compact-xs"
              variant="subtle"
              color="teal"
              leftSection={<IconArrowBackUp size={14} />}
              loading={bulk.isPending}
              aria-label="Undo last bulk reject"
              onClick={() => bulk.mutate({ action: "accept", ids: lastReject.ids })}
            >
              Undo {lastReject.label} reject ({lastReject.ids.length})
            </Button>
          ) : null}
          {streakedAccepted > 0 ? (
            <Group gap={4}>
              <Tooltip
                multiline
                w={260}
                label={`${streakedAccepted} accepted frame${streakedAccepted === 1 ? "" : "s"} carry a satellite/plane trail. Stack with sigma-clip or drizzle outlier rejection to remove the trail while keeping the frame, or reject them all here.`}
              >
                <Badge variant="light" color="orange">
                  {streakedAccepted} streaked
                </Badge>
              </Tooltip>
              <Button
                size="compact-xs"
                variant="subtle"
                color="orange"
                loading={bulk.isPending}
                aria-label="Reject all streaked frames"
                onClick={() => {
                  if (
                    window.confirm(
                      `Reject all ${streakedAccepted} accepted frame${streakedAccepted === 1 ? "" : "s"} carrying a satellite/plane trail?`,
                    )
                  ) {
                    bulk.mutate({ action: "reject_streaked" });
                  }
                }}
              >
                Reject all
              </Button>
            </Group>
          ) : null}
          {trailedAccepted > 0 ? (
            <Group gap={4}>
              <Tooltip
                multiline
                w={260}
                label={`${trailedAccepted} accepted frame${trailedAccepted === 1 ? "" : "s"} have unusually elongated stars for this target — a sign of tracking error, wind or a bumped mount on that whole sub. Rejecting them can sharpen the stack.`}
              >
                <Badge variant="light" color="yellow">
                  {trailedAccepted} trailed
                </Badge>
              </Tooltip>
              <Button
                size="compact-xs"
                variant="subtle"
                color="yellow"
                loading={bulk.isPending}
                aria-label="Reject all trailed frames"
                onClick={() => {
                  if (
                    window.confirm(
                      `Reject all ${trailedAccepted} accepted frame${trailedAccepted === 1 ? "" : "s"} with unusually elongated (trailed) stars?`,
                    )
                  ) {
                    bulk.mutate({ action: "reject_trailed" });
                  }
                }}
              >
                Reject all
              </Button>
            </Group>
          ) : null}
        </Group>
        <Group gap="xs">
          <Button
            variant="default"
            leftSection={<IconTelescope size={16} />}
            onClick={() => qcSolve.mutate()}
            loading={qcSolve.isPending}
            aria-label="Re-run QC and Solve"
          >
            <Box visibleFrom="sm">Re-run QC + Solve</Box>
          </Button>
          <Button component={Link} to={`/targets/${safe}/history`} variant="default"
            leftSection={<IconHistory size={16} />} aria-label="History">
            <Box visibleFrom="sm">History</Box>
          </Button>
          {latestRun ? (
            <Button component={Link} to={`/targets/${safe}/edit/${latestRun.id}`} variant="default"
              leftSection={<IconWand size={16} />} aria-label="Edit latest stack">
              <Box visibleFrom="sm">Edit</Box>
            </Button>
          ) : null}
          <Button component={Link} to={`/targets/${safe}/stack`}
            leftSection={<IconStack2 size={16} />} aria-label="Stack">
            <Box visibleFrom="sm">Stack</Box>
          </Button>
        </Group>
      </Group>

      <Grid>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Group mb="xs" gap="xs" align="flex-end">
            <Select size="xs" label="Reject worst by" w={150} value={rejectMetric}
              allowDeselect={false} data={REJECT_METRICS}
              onChange={(v) => setRejectMetric(v ?? "fwhm_px")} />
            <NumberInput size="xs" label="Percent" w={90} min={1} max={90} suffix="%"
              value={rejectPct} onChange={(v) => setRejectPct(Number(v) || 10)} />
            <Button size="xs" variant="light" color="red" loading={bulk.isPending}
              onClick={() => {
                const label = REJECT_METRICS.find((m) => m.value === rejectMetric)?.label;
                if (window.confirm(`Reject the worst ${rejectPct}% of accepted frames by ${label}?`)) {
                  bulk.mutate({ action: "reject_worst", metric: rejectMetric, fraction: rejectPct / 100 });
                }
              }}>
              Reject worst
            </Button>
            <Tooltip
              multiline w={280}
              label="Find statistical outliers across all quality metrics (trailed, cloud-hit, hazy subs) with a plain-language reason for each — preview first, then reject in one click."
            >
              <Button size="xs" variant="light" color="violet"
                leftSection={<IconSparkles size={14} />}
                onClick={() => setGradeOpen(true)}>
                Auto-grade
              </Button>
            </Tooltip>
          </Group>
          <AutoGradeModal
            safe={safe}
            opened={gradeOpen}
            onClose={() => setGradeOpen(false)}
            onApplied={(ids) => {
              qc.invalidateQueries({ queryKey: ["frames", safe] });
              qc.invalidateQueries({ queryKey: ["target", safe] });
              qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
              qc.invalidateQueries({ queryKey: ["auto-grade", safe] });
              if (ids.length) setLastReject({ ids, label: "auto-grade" });
            }}
          />
          <Text size="xs" c="dimmed" mb={4}>
            Keys: <b>j</b>/<b>k</b> move · <b>a</b> accept · <b>r</b> reject
          </Text>
          <Paper withBorder>
            <Table.ScrollContainer minWidth={620} mah="65vh">
              <Table stickyHeader highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={40}></Table.Th>
                    {cols.map((c) => (
                      <Table.Th
                        key={c.key}
                        onClick={() => setSortCol(c.key)}
                        style={{ cursor: "pointer" }}
                      >
                        {c.hint ? (
                          <Tooltip multiline w={240} label={c.hint}>
                            <span style={{ textDecoration: "underline dotted" }}>{c.label}</span>
                          </Tooltip>
                        ) : c.label}
                        {sort === c.key ? (order === "asc" ? " ▲" : " ▼") : ""}
                      </Table.Th>
                    ))}
                    <Table.Th w={50}>OK</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {list.map((f: Frame) => (
                    <Table.Tr
                      key={f.id}
                      onClick={() => setSelected(f.id)}
                      bg={selectedFrame?.id === f.id ? "var(--mantine-color-violet-light)" : undefined}
                      opacity={f.accept ? 1 : 0.45}
                      style={{ cursor: "pointer" }}
                    >
                      <Table.Td>
                        {f.solved ? (
                          <Tooltip label="Plate solved">
                            <IconTelescope size={14} color="var(--mantine-color-teal-5)" />
                          </Tooltip>
                        ) : null}
                      </Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="nowrap">
                          <span>{f.timestamp_utc?.replace("T", " ").slice(0, 19) ?? "—"}</span>
                          {!f.accept && f.reject_reason ? (
                            <Tooltip label={`Rejected — ${f.reject_reason}`}>
                              <Badge size="xs" color="gray" variant="light" style={{ flexShrink: 0 }}>
                                {rejectReasonLabel(f.reject_reason)}
                              </Badge>
                            </Tooltip>
                          ) : null}
                        </Group>
                      </Table.Td>
                      <Table.Td>{NUM(f.fwhm_px)}</Table.Td>
                      <Table.Td>{f.star_count ?? "—"}</Table.Td>
                      <Table.Td>{NUM(f.eccentricity_median)}</Table.Td>
                      <Table.Td><NumberFormatter value={f.sky_adu_median ?? 0} decimalScale={0} /></Table.Td>
                      <Table.Td>
                        {f.transparency_score == null
                          ? "—"
                          : <NumberFormatter value={f.transparency_score} decimalScale={0} />}
                      </Table.Td>
                      <Table.Td>
                        <ActionIcon
                          size="sm"
                          variant={f.accept ? "filled" : "subtle"}
                          color={f.accept ? "teal" : "red"}
                          aria-label={f.accept ? "Reject frame" : "Accept frame"}
                          onClick={(e) => {
                            e.stopPropagation();
                            patch.mutate({ id: f.id, body: { accept: !f.accept } });
                          }}
                        >
                          {f.accept ? <IconCheck size={14} /> : <IconX size={14} />}
                        </ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 5 }}>
          <Paper withBorder p="md">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>Preview</Text>
              <Select
                size="xs"
                placeholder="Bayer"
                w={110}
                data={["RGGB", "BGGR", "GRBG", "GBRG"]}
                value={bayer ?? null}
                onChange={(v) => setBayer(v ?? undefined)}
                clearable
              />
            </Group>
            {selectedFrame ? (
              <Stack gap="xs">
                <Box style={{ background: "#000", borderRadius: 8, overflow: "hidden" }}>
                  <Image
                    src={api.framePreviewUrl(safe, selectedFrame.id, 700, bayer)}
                    alt={selectedFrame.name}
                    fallbackSrc=""
                  />
                </Box>
                <Text size="sm" fw={500}>{selectedFrame.name}</Text>
                <Group gap="lg">
                  <Text size="xs" c="dimmed">FWHM {NUM(selectedFrame.fwhm_px)}</Text>
                  <Text size="xs" c="dimmed">Stars {selectedFrame.star_count ?? "—"}</Text>
                  <Text size="xs" c="dimmed">Exp {NUM(selectedFrame.exposure_s, 0)}s</Text>
                </Group>
                {(selectedFrame.ra_hint_deg != null || selectedFrame.solved) ? (
                  <Group gap="lg">
                    {selectedFrame.ra_hint_deg != null ? (
                      <Text size="xs" c="dimmed">
                        Target {NUM(selectedFrame.ra_hint_deg, 3)}°, {NUM(selectedFrame.dec_hint_deg, 3)}°
                      </Text>
                    ) : null}
                    {selectedFrame.solved ? (
                      <Text size="xs" c="teal">
                        Solved {NUM(selectedFrame.ra_center_deg, 3)}°, {NUM(selectedFrame.dec_center_deg, 3)}°
                      </Text>
                    ) : null}
                  </Group>
                ) : null}
              </Stack>
            ) : (
              <Center h={240}>
                <IconPhoto size={48} color="var(--mantine-color-dark-3)" />
              </Center>
            )}
          </Paper>

          {target.data ? (
            <Box mt="md">
              <NotesPanel safe={safe} notes={target.data.notes} tags={target.data.tags} />
            </Box>
          ) : null}
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
