import {
  Accordion, Alert, Button, Center, Group, Loader, Paper, Progress,
  Select, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import { IconFlask, IconPlayerPlay, IconTelescope } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api, type StackOptionField } from "../api/client";
import { StackOptionControl as FieldControl } from "../components/StackOptionControl";
import { useJobEvents } from "../hooks/useJobEvents";

export function StackView() {
  const { safe = "" } = useParams();
  const [searchParams] = useSearchParams();
  const reuseRunId = searchParams.get("from");
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJobEvents(jobId);

  const schema = useQuery({ queryKey: ["schema"], queryFn: api.optionsSchema });
  const defaults = useQuery({
    queryKey: ["stack-defaults", safe],
    queryFn: () => api.getStackDefaults(safe),
  });
  const frames = useQuery({ queryKey: ["frames", safe], queryFn: () => api.listFrames(safe) });
  const masters = useQuery({
    queryKey: ["calibration-masters"],
    queryFn: api.listCalibrationMasters,
  });
  const suggestions = useQuery({
    queryKey: ["calibration-suggestions", safe],
    queryFn: () => api.calibrationSuggestions(safe),
  });
  // When arriving via "Reuse settings" (?from=<runId>), fetch that run's options
  // so we can pre-fill the form from how a previous stack was made.
  const reuse = useQuery({
    queryKey: ["stack-run-options", safe, reuseRunId],
    queryFn: () => api.stackRunOptions(safe, Number(reuseRunId)),
    enabled: !!reuseRunId,
  });
  // Pre-run sizing: output canvas + estimated peak memory for the current
  // canvas-affecting knobs, so we can warn *before* a run is refused for OOM.
  const drizzleOn = !!values.drizzle;
  const drizzleScale = Number(values.drizzle_scale ?? 1.5);
  const drizzleReject = !!values.drizzle_reject;
  const mosaicCanvas = String(values.mosaic_canvas ?? "auto");
  const estimate = useQuery({
    queryKey: ["stack-estimate", safe, drizzleOn, drizzleScale, drizzleReject, mosaicCanvas],
    queryFn: () => api.stackEstimate(safe, {
      drizzle: drizzleOn, drizzle_scale: drizzleScale,
      drizzle_reject: drizzleReject, mosaic_canvas: mosaicCanvas,
    }),
    enabled: Object.keys(values).length > 0,
    retry: false,
  });

  const qcSolve = useMutation({
    mutationFn: () => api.qcSolve(safe),
    onSuccess: () => {
      notifications.show({ message: "QC + plate-solve started — watch the Jobs page", color: "violet" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  useEffect(() => {
    if (!defaults.data) return;
    // Base on this target's defaults, then overlay a reused run's settings (if
    // any) once they've loaded, so "Reuse settings" wins over the defaults.
    if (reuseRunId && !reuse.data) return;  // wait for the reuse payload first
    const reused = reuseRunId && reuse.data ? reuse.data.options : {};
    setValues({ ...defaults.data, ...reused });
  }, [defaults.data, reuseRunId, reuse.data]);

  // When a stack finishes it may have auto-rejected outlier frames — refresh
  // the frame list so the solved/accepted counts (and this page's guard) update.
  useEffect(() => {
    if (job?.state === "done") qc.invalidateQueries({ queryKey: ["frames", safe] });
  }, [job?.state, qc, safe]);

  const trigger = useMutation({
    mutationFn: () => api.triggerStack(safe, values),
    onSuccess: (r) => {
      setJobId(r.job_id);
      notifications.show({ message: "Stacking started", color: "violet" });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const saveDefaults = useMutation({
    mutationFn: () => api.putStackDefaults(safe, values),
    onSuccess: () => notifications.show({
      title: "Saved as defaults",
      message: "These options will pre-fill this form and drive auto-stacking for this target.",
      color: "teal",
    }),
    onError: (e: Error) => notifications.show({ message: `Save failed: ${e.message}`, color: "red" }),
  });

  if (schema.isLoading || defaults.isLoading || (!!reuseRunId && reuse.isLoading)) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const fields = schema.data ?? [];
  const set = (k: string, v: unknown) => setValues((p) => ({ ...p, [k]: v }));
  const isDisabled = (f: StackOptionField) =>
    f.depends_on ? !values[f.depends_on] : false;

  const simple = fields.filter((f) => f.group === "simple");
  const advanced = fields.filter((f) => f.group === "advanced");

  const sug = suggestions.data;
  const recDarkId = sug?.dark_master_id ?? null;
  const recFlatId = sug?.flat_master_id ?? null;
  const recFlatDarkId = sug?.flat_dark_master_id ?? null;
  // Badge the master matching `recId` (may differ per select — the light dark
  // and the flat-dark are both "dark" masters but recommended for different
  // exposures).
  const masterOpts = (kind: string, recId: number | null) =>
    (masters.data ?? [])
      .filter((m) => m.kind === kind && m.exists)
      .map((m) => {
        const star = m.id === recId ? " ★ recommended" : "";
        return {
          value: String(m.id),
          label: `${m.name} (${m.n_frames} frames, ${m.width_px}×${m.height_px})${star}`,
        };
      });
  const darkOpts = masterOpts("dark", recDarkId);
  const flatDarkOpts = masterOpts("dark", recFlatDarkId);
  const flatOpts = masterOpts("flat", recFlatId);
  const hasMasters = darkOpts.length > 0 || flatOpts.length > 0;
  // Show the "use recommended" hint only when there's a suggestion the user
  // hasn't already applied. The flat-dark is only relevant once a flat is set.
  const canApplyRec = (recDarkId !== null && String(values.dark_master_id ?? "") !== String(recDarkId))
    || (recFlatId !== null && String(values.flat_master_id ?? "") !== String(recFlatId))
    || (recFlatDarkId !== null && String(values.flat_dark_master_id ?? "") !== String(recFlatDarkId));
  const applyRecommended = () => {
    if (recDarkId !== null) set("dark_master_id", String(recDarkId));
    if (recFlatId !== null) set("flat_master_id", String(recFlatId));
    if (recFlatDarkId !== null) set("flat_dark_master_id", String(recFlatDarkId));
  };
  const asStr = (v: unknown) => (v === undefined || v === null ? null : String(v));

  // Inline cautions when a chosen master is a poor match for the data. A dark
  // captures thermal/bias signal at a *specific* exposure, so an exposure
  // mismatch either under- or over-subtracts; a flat-dark must instead match the
  // flat's exposure. Advisory only — the pick is still honoured.
  const masterById = (id: unknown) =>
    (masters.data ?? []).find((m) => String(m.id) === String(id ?? ""));
  const expMismatch = (a: number | null | undefined, b: number | null | undefined) =>
    a != null && b != null && b > 0 && Math.abs(a - b) / b > 0.25;
  const subExp = sug?.params.exposure_s ?? null;
  const darkM = masterById(values.dark_master_id);
  const darkWarning = expMismatch(darkM?.exposure_s, subExp)
    ? `This dark was shot at ${darkM?.exposure_s}s but your subs are ${subExp}s — a mismatched dark leaves residual thermal signal or over-subtracts. A ${subExp}s dark matches better.`
    : null;
  const flatM = masterById(values.flat_master_id);
  const flatDarkM = masterById(values.flat_dark_master_id);
  const flatDarkWarning = flatDarkM && expMismatch(flatDarkM.exposure_s, flatM?.exposure_s)
    ? `This flat-dark was shot at ${flatDarkM.exposure_s}s but your flat is ${flatM?.exposure_s}s — a flat-dark should match the flat's exposure to remove its pedestal cleanly.`
    : null;
  const running = job && (job.state === "running" || job.state === "queued");
  const pct = job && job.total ? Math.round((job.done / job.total) * 100) : 0;

  // Stacking needs at least one accepted, plate-solved frame to align against.
  // Block it in the UI (rather than letting the job error) when there are none.
  const solvedAccepted = (frames.data ?? []).filter((f) => f.accept && f.solved).length;
  const noSolved = !frames.isLoading && frames.data !== undefined && solvedAccepted === 0;
  const excludedFrames = (job?.result?.excluded_frames as string[] | undefined) ?? [];

  // "Keep streaked frames" leaves satellite/plane-trailed subs accepted so that
  // per-pixel rejection can clean them. If the user then stacks *without* any
  // rejection, the streak lands in the result — warn them so the kept frames
  // aren't a silent footgun. Advisory only.
  const streakedAccepted = (frames.data ?? [])
    .filter((f) => f.accept && f.solved && f.streak_detected).length;
  const rejectionOn = values.drizzle
    ? !!values.drizzle_reject
    : (!!values.sigma_clip && solvedAccepted >= 4);
  const streakNoRejectionWarning =
    streakedAccepted > 0 && !rejectionOn
      ? `${streakedAccepted} accepted frame${streakedAccepted === 1 ? " has" : "s have"} a detected satellite/plane streak, but this stack has no per-pixel rejection enabled — the trail${streakedAccepted === 1 ? "" : "s"} will show in the result. Turn on ${values.drizzle ? "“Drizzle outlier rejection”" : "sigma clipping"} (or reject those frames) to remove ${streakedAccepted === 1 ? "it" : "them"}.`
      : null;

  // Sigma-clip rejection estimates each pixel's spread across the stack, so it
  // needs a handful of frames to be meaningful. With only a few it can throw
  // away real signal as if it were an outlier — a knob a beginner can't reason
  // about, so surface a plain-language "why". Advisory only; the pick stands.
  const SIGMA_CLIP_MIN_FRAMES = 5;
  const sigmaClipWarning =
    values.sigma_clip && !frames.isLoading && solvedAccepted > 0
    && solvedAccepted < SIGMA_CLIP_MIN_FRAMES
      ? `Sigma-clip rejection estimates each pixel's spread across frames, but you only have ${solvedAccepted} accepted, solved frame${solvedAccepted === 1 ? "" : "s"}. With fewer than ~${SIGMA_CLIP_MIN_FRAMES} it can reject real signal as an outlier — consider turning it off for this stack.`
      : null;

  // The flip side of the low-frame caution: with a big stack the per-pixel σ is
  // very well estimated, so the default κ=3 leaves a lot of satellite/plane/
  // cosmic-ray signal in that a tighter clip would safely reject. Suggest
  // nudging κ down for very large stacks. Advisory only; the pick stands.
  const SIGMA_CLIP_LARGE_FRAMES = 200;
  const kappa = Number(values.sigma_kappa ?? 3);
  const sigmaKappaLargeHint =
    values.sigma_clip && !frames.isLoading
    && solvedAccepted >= SIGMA_CLIP_LARGE_FRAMES && kappa >= 3
      ? `With ${solvedAccepted} accepted frames the per-pixel spread is very well measured, so a tighter sigma-clip (κ≈2.5) can safely reject more satellites, planes and cosmic rays than the default κ=${kappa % 1 === 0 ? kappa.toFixed(0) : kappa}. Lower the Sigma kappa in Advanced options if you see trails survive.`
      : null;

  // Drizzle accumulates in a single pass, so the sigma-clip toggle doesn't
  // apply to it — a user who enabled both would reasonably expect satellite
  // trails to be rejected and be surprised when they aren't. Point them at
  // the drizzle-specific rejection instead. Advisory only.
  const drizzleClipHint =
    values.drizzle && values.sigma_clip && !values.drizzle_reject
      ? "Sigma clipping doesn't apply to drizzle's single-pass accumulation — enable “Drizzle outlier rejection” to reject satellites and cosmic rays in drizzled stacks."
      : null;

  // Pre-run sizing line: shows the output canvas the current knobs would
  // produce and the estimated peak working memory, so a big drizzle/mosaic
  // canvas doesn't get silently refused for OOM only after the user hits Stack.
  const est = estimate.data;
  const estimateLine = est
    ? `${est.n_frames} accepted, solved frame${est.n_frames === 1 ? "" : "s"}`
      + (est.is_mosaic ? " · mosaic canvas" : "")
      + ` · output ${est.output_w}×${est.output_h}`
      + ` · ~${est.peak_gb.toFixed(est.peak_gb < 1 ? 2 : 1)} GB peak memory`
    : null;
  const estimateOverBudget = est?.would_exceed
    ? `This stack would need ~${est.peak_gb.toFixed(1)} GB of working memory, over the ~${est.budget_gb.toFixed(1)} GB budget on this server, so the run will be refused. Lower the drizzle scale, switch Canvas mode to “reference”, or reject off-target frames.`
    : null;

  return (
    <Stack maw={720}>
      <Group justify="space-between">
        <Title order={2}>Stack — {safe}</Title>
        <Button component={Link} to={`/targets/${safe}`} variant="subtle">
          Back to frames
        </Button>
      </Group>

      {reuseRunId && reuse.data ? (
        <Alert color="blue" variant="light" py={6} px="sm">
          <Text size="xs">
            Settings pre-filled from run #{reuseRunId}. Adjust anything, then start a fresh stack.
          </Text>
        </Alert>
      ) : null}

      {noSolved ? (
        <Alert color="yellow" title="No plate-solved frames yet" icon={<IconTelescope size={18} />}>
          <Stack gap="xs" align="flex-start">
            <Text size="sm">
              Stacking needs at least one accepted frame with a successful plate-solve to align
              against. Run plate-solving first, then come back to stack.
            </Text>
            <Button
              size="xs" variant="light"
              leftSection={<IconTelescope size={14} />}
              onClick={() => qcSolve.mutate()}
              loading={qcSolve.isPending}
            >
              Run QC + plate-solve
            </Button>
          </Stack>
        </Alert>
      ) : null}

      <Paper withBorder p="lg">
        <Stack>
          {simple.map((f) => (
            <FieldControl
              key={f.key}
              field={f}
              value={values[f.key]}
              disabled={isDisabled(f)}
              onChange={(v) => set(f.key, v)}
            />
          ))}

          <Paper withBorder p="sm" bg="var(--mantine-color-default)">
            <Group gap={6} mb={hasMasters ? "xs" : 0}>
              <IconFlask size={16} />
              <Text fw={600} size="sm">Calibration</Text>
            </Group>
            {hasMasters ? (
              <Stack gap="xs">
                {canApplyRec ? (
                  <Group gap="xs" justify="space-between" wrap="nowrap">
                    <Text size="xs" c="dimmed">
                      Matched to this target's frames
                      {sug?.params.exposure_s ? ` (${sug.params.exposure_s}s subs)` : ""}.
                    </Text>
                    <Button size="compact-xs" variant="light" onClick={applyRecommended}>
                      Use recommended
                    </Button>
                  </Group>
                ) : null}
                <Group grow align="flex-end">
                  <Select
                    label="Master dark" placeholder="None" clearable
                    data={darkOpts} value={asStr(values.dark_master_id)}
                    onChange={(v) => set("dark_master_id", v)}
                    disabled={darkOpts.length === 0}
                  />
                  <Select
                    label="Master flat" placeholder="None" clearable
                    data={flatOpts} value={asStr(values.flat_master_id)}
                    onChange={(v) => set("flat_master_id", v)}
                    disabled={flatOpts.length === 0}
                  />
                </Group>
                {darkWarning ? (
                  <Alert color="yellow" variant="light" py={6} px="sm">
                    <Text size="xs">{darkWarning}</Text>
                  </Alert>
                ) : null}
                {values.flat_master_id && darkOpts.length > 0 ? (
                  <Select
                    label="Flat-dark (optional)"
                    description="A dark matched to the flat's exposure, subtracted from the flat before normalising for a more accurate flat."
                    placeholder="None" clearable
                    data={flatDarkOpts} value={asStr(values.flat_dark_master_id)}
                    onChange={(v) => set("flat_dark_master_id", v)}
                  />
                ) : null}
                {flatDarkWarning ? (
                  <Alert color="yellow" variant="light" py={6} px="sm">
                    <Text size="xs">{flatDarkWarning}</Text>
                  </Alert>
                ) : null}
              </Stack>
            ) : (
              <Text size="xs" c="dimmed">
                No masters built yet. Create darks/flats on the{" "}
                <Link to="/calibration">Calibration page</Link> to apply them here.
              </Text>
            )}
          </Paper>

          <Accordion variant="separated" mt="xs">
            <Accordion.Item value="advanced">
              <Accordion.Control>Advanced options</Accordion.Control>
              <Accordion.Panel>
                <Stack>
                  {advanced.map((f) => (
                    <FieldControl
                      key={f.key}
                      field={f}
                      value={values[f.key]}
                      disabled={isDisabled(f)}
                      onChange={(v) => set(f.key, v)}
                    />
                  ))}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>

          {sigmaClipWarning ? (
            <Alert color="yellow" variant="light" py={6} px="sm">
              <Text size="xs">{sigmaClipWarning}</Text>
            </Alert>
          ) : null}

          {sigmaKappaLargeHint ? (
            <Alert color="blue" variant="light" py={6} px="sm">
              <Text size="xs">{sigmaKappaLargeHint}</Text>
            </Alert>
          ) : null}

          {streakNoRejectionWarning ? (
            <Alert color="yellow" variant="light" py={6} px="sm">
              <Text size="xs">{streakNoRejectionWarning}</Text>
            </Alert>
          ) : null}

          {drizzleClipHint ? (
            <Alert color="blue" variant="light" py={6} px="sm">
              <Text size="xs">{drizzleClipHint}</Text>
            </Alert>
          ) : null}

          {estimateOverBudget ? (
            <Alert color="red" variant="light" py={6} px="sm">
              <Text size="xs">{estimateOverBudget}</Text>
              {est?.suggested_drizzle_scale ? (
                <Button
                  mt={6}
                  size="xs"
                  variant="light"
                  color="red"
                  onClick={() => set("drizzle_scale", est.suggested_drizzle_scale)}
                >
                  Use drizzle ×{est.suggested_drizzle_scale} instead (fits the budget)
                </Button>
              ) : est?.suggested_reference_canvas ? (
                <Button
                  mt={6}
                  size="xs"
                  variant="light"
                  color="red"
                  onClick={() => set("mosaic_canvas", "reference")}
                >
                  Use the reference canvas instead (fits the budget)
                </Button>
              ) : null}
            </Alert>
          ) : estimateLine && !noSolved ? (
            <Text size="xs" c="dimmed">{estimateLine}</Text>
          ) : null}

          {job ? (
            <Stack gap={4}>
              <Group justify="space-between">
                <Text size="sm" c="dimmed">
                  {job.state === "done"
                    ? "Done"
                    : job.state === "error"
                      ? `Error: ${job.error}`
                      : `${job.phase || "working"} ${job.done}/${job.total}`}
                </Text>
                <Text size="sm" c="dimmed">{pct}%</Text>
              </Group>
              <Progress
                value={job.state === "done" ? 100 : pct}
                color={job.state === "error" ? "red" : job.state === "done" ? "teal" : "violet"}
                animated={Boolean(running)}
              />
              {job.state === "done" && excludedFrames.length > 0 ? (
                <Alert color="orange" mt="xs" p="xs">
                  <Text size="xs">
                    Dropped {excludedFrames.length} frame(s) with a bad plate-solve (footprint far
                    from the group) and flagged them rejected: {excludedFrames.join(", ")}
                  </Text>
                </Alert>
              ) : null}
              {job.state === "done" ? (
                <Button component={Link} to={`/targets/${safe}/history`} variant="light" mt="xs">
                  View result in History
                </Button>
              ) : null}
            </Stack>
          ) : null}

          <Group justify="flex-end" mt="sm">
            <Tooltip label="Remember these options for this target — they pre-fill this form and are used when auto-stacking is on">
              <Button variant="default" onClick={() => saveDefaults.mutate()} loading={saveDefaults.isPending}>
                Save as defaults
              </Button>
            </Tooltip>
            <Tooltip
              label="Plate-solve at least one accepted frame first"
              disabled={!noSolved}
            >
              <Button
                leftSection={<IconPlayerPlay size={16} />}
                onClick={() => trigger.mutate()}
                loading={trigger.isPending || Boolean(running)}
                disabled={noSolved}
              >
                Start stacking
              </Button>
            </Tooltip>
          </Group>
        </Stack>
      </Paper>
    </Stack>
  );
}
