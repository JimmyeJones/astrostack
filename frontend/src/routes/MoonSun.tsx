import {
  Alert, Badge, Button, Card, Center, Checkbox, Group, Image, Loader, Paper,
  Select, SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle, IconArrowBackUp, IconChartBar, IconCrop, IconDownload,
  IconMoon, IconSun, IconVideo, IconWand,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type VideoCapture } from "../api/client";
import { QueryError } from "../components/QueryError";
import { ScanToPhoneButton } from "../components/ScanToPhoneButton";
import { SharePictureButton } from "../components/SharePictureButton";
import { sharePictureText } from "../share";
import { videoPreviewSrc } from "../components/videoPreviewSrc";
import { VideoQuickLookCard } from "../components/VideoQuickLookCard";
import { VideoSharpnessCard } from "../components/VideoSharpnessCard";
// The framing copy is shared with the Gallery's video-still card, which offers
// the identical crop — re-exported here so this page stays the obvious place to
// look for it (and its existing callers/tests keep importing it from one place).
import { cropNote, cropSuggestion, subjectNoun } from "../components/videoFraming";

export { cropNote, cropSuggestion, subjectNoun };

// Local, like Storage.tsx's `gb` — a video is MB-to-GB sized, and there is no
// shared byte formatter to reach for.
function fileSize(bytes: number): string {
  if (!bytes) return "0 MB";
  const mb = bytes / 1024 ** 2;
  return mb < 1024 ? `${mb.toFixed(0)} MB` : `${(mb / 1024).toFixed(2)} GB`;
}

// Keep-% presets, phrased as what they *do* rather than as a number. Lucky
// imaging's one real decision is how ruthless to be, and a beginner has no way
// to guess "25%" — but they can absolutely answer "was the air steady?".
// These three values must stay in step with `DEFAULT_CANDIDATES` in
// `seestack/video/quality.py`: the "How steady was your capture?" panel measures
// the trade-off at exactly these settings and its "try this instead" button
// selects one of them here.
export const KEEP_PRESETS = [
  { value: "15", label: "Only the very best (15%) — sharpest, a bit noisier" },
  { value: "30", label: "Best few (30%) — recommended" },
  { value: "50", label: "Half of them (50%) — smoother, a little softer" },
];

export const DEFAULT_KEEP = "30";

// How hard to sharpen the finished picture. A lucky stack is an average, and
// averaging softens — every planetary tool finishes with a sharpening step for
// exactly that reason. The amounts must stay in step with `SHARPEN_PRESETS` in
// `seestack/video/detail.py`, which is what actually renders them.
export const SHARPEN_PRESETS = [
  { value: "0", name: "Off", label: "Off — the plain stacked picture" },
  { value: "0.6", name: "Gentle", label: "Gentle — recommended" },
  { value: "1.2", name: "Medium", label: "Medium — more surface detail" },
  { value: "2", name: "Strong", label: "Strong — as far as it goes" },
];

export const DEFAULT_SHARPEN = "0";

/** How a finished picture says it was sharpened, or null when it wasn't.
 *
 * Named by the nearest preset rather than printed as a number: "1.2" means
 * nothing to the person looking at the picture, and a still made by a hand-written
 * API call can still be described in the same words as one made from the menu.
 */
export function sharpenNote(amount: number | undefined | null): string | null {
  if (!amount || !Number.isFinite(amount) || amount <= 0) return null;
  const preset = SHARPEN_PRESETS
    .filter((p) => Number(p.value) > 0)
    .reduce((best, p) => (
      Math.abs(Number(p.value) - amount) < Math.abs(Number(best.value) - amount) ? p : best
    ));
  return `Sharpening: ${preset.name} — surface detail lifted after stacking.`;
}

/** One-line summary of a finished still, in plain language (pure, tested). */
export function resultSummary(r: {
  n_stacked: number; n_graded: number; width: number; height: number;
}): string {
  const cleaner = Math.sqrt(Math.max(1, r.n_stacked));
  return (
    `Stacked the sharpest ${r.n_stacked} of ${r.n_graded} frames `
    + `— about ${cleaner.toFixed(1)}× cleaner than a single frame `
    + `(${r.width}×${r.height}).`
  );
}

function CaptureIcon({ kind }: { kind: VideoCapture["kind"] }) {
  if (kind === "lunar") return <IconMoon size={20} color="var(--mantine-color-yellow-4)" />;
  if (kind === "solar") return <IconSun size={20} color="var(--mantine-color-orange-4)" />;
  return <IconVideo size={20} color="var(--mantine-color-dimmed)" />;
}

function CaptureCard({ capture, disabled }: { capture: VideoCapture; disabled: boolean }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [keep, setKeep] = useState<string>(DEFAULT_KEEP);
  const [crop, setCrop] = useState(false);
  const [sharpen, setSharpen] = useState<string>(DEFAULT_SHARPEN);
  const [file, setFile] = useState<string | null>(
    capture.files.length === 1 ? capture.files[0].name : null,
  );

  // The override lets the "crop it" suggestion act in one click: setting the
  // checkbox and firing the mutation in the same handler would send the *old*
  // value, since state updates don't apply until the next render.
  const stack = useMutation({
    mutationFn: (over: { crop?: boolean } = {}) => api.stackVideoCapture(capture.id, {
      keep_percent: Number(keep),
      file_name: file ?? undefined,
      crop: over.crop ?? crop,
      sharpen: Number(sharpen),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      notifications.show({
        message: `Stacking your ${capture.label} video — this takes a minute or two.`,
        color: "violet",
      });
      navigate("/jobs");
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // Grading is the cheap half of the stack (one decode, a score per frame), so
  // it can be run on its own to answer "how picky should I be?" *before* the
  // stack is spent finding out. It never touches an existing still.
  const grade = useMutation({
    mutationFn: () => api.gradeVideoCapture(capture.id, { file_name: file ?? undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      notifications.show({
        message: `Checking your ${capture.label} video — reading it through once.`,
        color: "violet",
      });
      navigate("/jobs");
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // Cropping a still that already exists never re-decodes the capture — it
  // slices the saved picture — so it is a plain request with an instant answer,
  // not a job. Undo is offered whenever the full frame is still saved beside it.
  const cropStill = useMutation({
    mutationFn: () => api.cropVideoStill(capture.id),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: ["gallery"] });
      notifications.show({
        message: (
          `Trimmed ${Math.round((r.crop_trim_fraction ?? 0) * 100)}% of empty sky `
          + `— your ${capture.label} picture is now ${r.width}×${r.height}.`
        ),
        color: "teal",
      });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const restoreStill = useMutation({
    mutationFn: () => api.restoreVideoStill(capture.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["videos"] });
      qc.invalidateQueries({ queryKey: ["gallery"] });
      notifications.show({ message: "Put the full frame back.", color: "teal" });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const result = capture.result;
  // The source clip is gone from `incoming/` — cleared off the NAS, which is
  // exactly what the in-place crop was built to survive. The picture is still
  // here (the backend lists the finished still anyway, so this page stays the
  // one that owns it), but nothing that needs to decode the video can run, so
  // the stacking half of the card is hidden rather than offered and failed.
  const sourceGone = capture.files.length === 0;
  const suggestCrop = cropSuggestion(result, capture.kind);
  const cropped = cropNote(result, capture.kind);

  return (
    <Card withBorder radius="md" padding="md">
      <Group justify="space-between" wrap="nowrap" mb="sm">
        <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
          <CaptureIcon kind={capture.kind} />
          <div style={{ minWidth: 0 }}>
            <Text fw={600} truncate>{capture.label}</Text>
            <Text size="xs" c="dimmed" truncate>
              {sourceGone
                ? `${capture.folder_name} · video no longer in your incoming folder`
                : `${capture.folder_name} · ${capture.files.length} `
                  + `${capture.files.length === 1 ? "video" : "videos"} · `
                  + fileSize(capture.total_bytes)}
            </Text>
          </div>
        </Group>
        {result ? <Badge color="teal" variant="light">Stacked</Badge> : null}
      </Group>

      {result ? (
        <Card.Section mb="sm">
          <Image
            src={videoPreviewSrc(result)}
            alt={`Stacked ${capture.label}`}
            fit="contain"
            mah={280}
            bg="black"
          />
        </Card.Section>
      ) : null}

      {result ? (
        <Stack gap={4} mb="sm">
          <Text size="sm">{resultSummary(result)}</Text>
          {cropped ? (
            <Group gap="xs" wrap="nowrap" align="center">
              <Text size="xs" c="dimmed">{cropped}</Text>
              {/* A framing decision should never be one-way: the full frame is
                  kept beside the cropped one, so undoing it is a click. */}
              {result.crop_restorable ? (
                <Button
                  size="compact-xs"
                  variant="subtle"
                  leftSection={<IconArrowBackUp size={12} />}
                  onClick={() => restoreStill.mutate()}
                  loading={restoreStill.isPending}
                >
                  Undo crop
                </Button>
              ) : null}
            </Group>
          ) : null}
          {/* Provenance: a sharpened picture should say so, so nobody wonders
              later why it looks crisper than the last one. */}
          {sharpenNote(result.sharpen_amount) ? (
            <Text size="xs" c="dimmed">{sharpenNote(result.sharpen_amount)}</Text>
          ) : null}
          {result.warnings.map((w) => (
            <Text key={w} size="xs" c="dimmed">{w}</Text>
          ))}
          {/* Most people won't think to ask for a crop before they've seen how
              much sky their Seestar left around the Moon — so the offer waits
              until the picture itself can make the case. */}
          {suggestCrop ? (
            <Alert
              color="violet"
              variant="light"
              icon={<IconCrop size={18} />}
              p="xs"
              mt={4}
            >
              <Text size="xs">{suggestCrop}</Text>
              <Button
                size="compact-xs"
                variant="light"
                mt={6}
                leftSection={<IconCrop size={12} />}
                onClick={() => cropStill.mutate()}
                loading={cropStill.isPending}
              >
                Crop it
              </Button>
            </Alert>
          ) : null}
          <Group gap="xs" mt={4}>
            <Button
              size="xs"
              variant="light"
              leftSection={<IconDownload size={14} />}
              component="a"
              href={result.preview_url}
              download={`${capture.id}.png`}
            >
              PNG
            </Button>
            <Button
              size="xs"
              variant="subtle"
              leftSection={<IconDownload size={14} />}
              component="a"
              href={result.tiff_url}
            >
              16-bit TIFF
            </Button>
            {/* The first thing a beginner wants to do with a Moon picture is
                show someone — and the QR needs nothing but the picture's URL,
                so the same control the stack pages carry works verbatim here. */}
            <ScanToPhoneButton
              url={result.preview_url}
              caption={
                "Point your phone camera at this code to open your "
                + `${subjectNoun(capture.kind)} picture and save it.`
              }
            />
            {/* …and on a phone, where that QR is redundant with the OS's own
                sheet, this is the control that actually helps. It renders
                nothing on a browser that can't share files, so a desktop still
                sees exactly the row it saw before. */}
            <SharePictureButton
              {...(() => {
                const { title, text, filename } = sharePictureText(
                  capture.label,
                  new Date(result.created_utc).toLocaleDateString(),
                  "png",
                );
                return { filename, title, text };
              })()}
              url={result.preview_url}
              label="Share"
            />
          </Group>
          {/* The evidence behind "how picky should we be?", measured on this
              capture. Self-hiding for a still stacked before the scores were
              kept. Its suggestion drives the same Select below, so acting on it
              is one click then "Stack again". */}
          <VideoSharpnessCard
            profile={result.sharpness}
            onUseSuggestion={(pct) => setKeep(String(pct))}
          />
        </Stack>
      ) : null}

      {sourceGone ? (
        <Text size="xs" c="dimmed">
          The video this came from isn't in your incoming folder any more, so it
          can't be stacked again — your picture is safe here either way.
        </Text>
      ) : null}

      {!sourceGone && capture.files.length > 1 ? (
        <Select
          label="Which recording?"
          size="sm"
          mb="sm"
          data={capture.files.map((f) => ({
            value: f.name, label: `${f.name} (${fileSize(f.size_bytes)})`,
          }))}
          value={file}
          onChange={setFile}
          placeholder="The longest one"
          clearable
        />
      ) : null}

      {/* Before any stack exists, the same panel from the grade-only pass — so
          the setting below is an informed choice rather than a guess. Once a
          still exists the result's own panel (above) is the better one to show,
          since it can mark where the cut actually fell. */}
      {!result && !sourceGone ? (
        <>
          <VideoSharpnessCard
            profile={capture.sharpness}
            onUseSuggestion={(pct) => setKeep(String(pct))}
          />
          {/* The curve says how much the frames vary; the frame itself says
              whether there is anything worth stacking in the first place. Both
              come out of the one check, so both are shown before the stack. */}
          <VideoQuickLookCard
            quicklook={capture.quicklook}
            subject={subjectNoun(capture.kind)}
          />
        </>
      ) : null}

      {sourceGone ? null : (
        <>
          <Select
            label="How picky should we be?"
            description="Seeing makes some frames much sharper than others; we keep the best and throw the rest away."
            size="sm"
            data={KEEP_PRESETS}
            value={keep}
            onChange={(v) => setKeep(v ?? DEFAULT_KEEP)}
            allowDeselect={false}
            mb="sm"
            mt="sm"
          />

          {/* A stack is an average, and averaging softens — so the last step of
              every planetary workflow is a sharpen. The editor can't open a
              Moon still, so without this the picture the user downloads is the
              soft one. Off by default: the picture an existing install has been
              getting must not change under it. */}
          <Select
            label="Sharpen the detail"
            description="Stacking makes a clean picture but a slightly soft one. This brings the surface detail back."
            size="sm"
            data={SHARPEN_PRESETS}
            value={sharpen}
            onChange={(v) => setSharpen(v ?? DEFAULT_SHARPEN)}
            allowDeselect={false}
            mb="sm"
          />

          <Checkbox
            label={`Crop to the ${subjectNoun(capture.kind)}`}
            description={
              `Trims the empty sky around it, so your picture is mostly `
              + `${subjectNoun(capture.kind)}. Left alone if there's nothing to trim.`
            }
            size="sm"
            mb="sm"
            checked={crop}
            onChange={(e) => setCrop(e.currentTarget.checked)}
          />

          <Button
            fullWidth
            leftSection={<IconWand size={16} />}
            onClick={() => stack.mutate({})}
            loading={stack.isPending}
            disabled={disabled}
          >
            {result ? "Stack again" : "Stack video"}
          </Button>

          {/* Only worth offering while there is nothing to compare against — once a
              still exists its own panel already answers the question. */}
          {!result && !capture.sharpness ? (
            <Button
              fullWidth
              mt="xs"
              variant="subtle"
              size="sm"
              leftSection={<IconChartBar size={16} />}
              onClick={() => grade.mutate()}
              loading={grade.isPending}
              disabled={disabled}
            >
              Check this capture first
            </Button>
          ) : null}
        </>
      )}
    </Card>
  );
}

export function MoonSunView() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["videos"], queryFn: api.listVideoCaptures, refetchInterval: 15_000,
  });

  if (isError && !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }
  if (isLoading || !data) {
    return <Center h={300}><Loader /></Center>;
  }

  return (
    <Stack gap="md">
      <div>
        <Title order={2}>Moon &amp; Sun</Title>
        <Text c="dimmed" size="sm">
          Shot a video of the Moon or the Sun with your Seestar? We&apos;ll pick out the
          sharpest moments and combine them into one crisp picture.
        </Text>
      </div>

      {!data.available && data.hint ? (
        <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title="Not available yet">
          {data.hint}
        </Alert>
      ) : null}

      {data.captures.length === 0 ? (
        <Paper withBorder p="xl" radius="md">
          <Stack align="center" gap="xs">
            <IconVideo size={40} color="var(--mantine-color-dark-3)" />
            <Text fw={600}>No Moon or Sun videos yet</Text>
            <Text size="sm" c="dimmed" ta="center" maw={520}>
              When you record the Moon or the Sun, your Seestar saves it into a folder
              whose name ends in <b>_video</b> (like <b>Lunar_video</b>). Copy that folder
              into your watched folder and it&apos;ll show up here.
            </Text>
            <Text size="xs" c="dimmed">{data.incoming_dir}</Text>
          </Stack>
        </Paper>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {data.captures.map((c) => (
            <CaptureCard key={c.id} capture={c} disabled={!data.available} />
          ))}
        </SimpleGrid>
      )}

      <Text size="xs" c="dimmed">
        Why this works: the air never sits still, so a handful of frames in any video
        are much sharper than the rest. Keeping only those — and averaging them —
        gives you detail one frame can&apos;t, with far less noise.
      </Text>
    </Stack>
  );
}
