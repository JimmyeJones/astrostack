import {
  Alert, Badge, Button, Card, Center, Group, Image, Loader, Paper, Select,
  SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle, IconDownload, IconMoon, IconSun, IconVideo, IconWand,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type VideoCapture } from "../api/client";
import { QueryError } from "../components/QueryError";

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
export const KEEP_PRESETS = [
  { value: "15", label: "Only the very best (15%) — sharpest, a bit noisier" },
  { value: "30", label: "Best few (30%) — recommended" },
  { value: "50", label: "Half of them (50%) — smoother, a little softer" },
];

export const DEFAULT_KEEP = "30";

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
  const [file, setFile] = useState<string | null>(
    capture.files.length === 1 ? capture.files[0].name : null,
  );

  const stack = useMutation({
    mutationFn: () => api.stackVideoCapture(capture.id, {
      keep_percent: Number(keep),
      file_name: file ?? undefined,
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

  const result = capture.result;

  return (
    <Card withBorder radius="md" padding="md">
      <Group justify="space-between" wrap="nowrap" mb="sm">
        <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
          <CaptureIcon kind={capture.kind} />
          <div style={{ minWidth: 0 }}>
            <Text fw={600} truncate>{capture.label}</Text>
            <Text size="xs" c="dimmed" truncate>
              {capture.folder_name} · {capture.files.length}{" "}
              {capture.files.length === 1 ? "video" : "videos"} ·{" "}
              {fileSize(capture.total_bytes)}
            </Text>
          </div>
        </Group>
        {result ? <Badge color="teal" variant="light">Stacked</Badge> : null}
      </Group>

      {result ? (
        <Card.Section mb="sm">
          <Image
            src={`${result.preview_url}?t=${encodeURIComponent(result.created_utc)}`}
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
          {result.warnings.map((w) => (
            <Text key={w} size="xs" c="dimmed">{w}</Text>
          ))}
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
          </Group>
        </Stack>
      ) : null}

      {capture.files.length > 1 ? (
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

      <Select
        label="How picky should we be?"
        description="Seeing makes some frames much sharper than others; we keep the best and throw the rest away."
        size="sm"
        data={KEEP_PRESETS}
        value={keep}
        onChange={(v) => setKeep(v ?? DEFAULT_KEEP)}
        allowDeselect={false}
        mb="sm"
      />

      <Button
        fullWidth
        leftSection={<IconWand size={16} />}
        onClick={() => stack.mutate()}
        loading={stack.isPending}
        disabled={disabled}
      >
        {result ? "Stack again" : "Stack video"}
      </Button>
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
