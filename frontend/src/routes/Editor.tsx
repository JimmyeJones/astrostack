import {
  Button, Center, Grid, Group, Image, Loader, Menu, Paper, Select, Stack, Text,
  TextInput, Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import {
  IconArrowLeft, IconDeviceFloppy, IconDownload, IconPlus, IconSparkles, IconZoomScan,
} from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type EditOp, type OpInstance, type Recipe } from "../api/client";
import { ImageLightbox } from "../components/ImageLightbox";
import { Histogram } from "../components/editor/Histogram";
import { OpList } from "../components/editor/OpList";
import { OpParamPanel } from "../components/editor/OpParamPanel";
import { PresetMenu } from "../components/editor/PresetMenu";

const GROUP_LABELS: Record<string, string> = {
  background: "Background", tone: "Tone & color", detail: "Detail",
  stars_geometry: "Stars & geometry",
};
const GROUP_ORDER = ["background", "tone", "detail", "stars_geometry"];

function uid(): string {
  return (crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)).slice(0, 8);
}

function newOp(spec: EditOp): OpInstance {
  const params: Record<string, unknown> = {};
  spec.params.forEach((p) => { params[p.key] = p.default; });
  return { uid: uid(), id: spec.id, enabled: true, params };
}

export function EditorView() {
  const { safe = "", runId = "" } = useParams();
  const rid = Number(runId);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const opsSchema = useQuery({ queryKey: ["editor-ops"], queryFn: api.editorOps, staleTime: 60_000 });
  const saved = useQuery({ queryKey: ["recipe", safe, rid], queryFn: () => api.getRecipe(safe, rid) });

  const [ops, setOps] = useState<OpInstance[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [outputName, setOutputName] = useState("");
  const [tiffMode, setTiffMode] = useState("linear");
  const [lightbox, setLightbox] = useState(false);

  // Seed ops from the saved recipe once.
  useEffect(() => {
    if (saved.data) setOps(saved.data.ops ?? []);
  }, [saved.data]);

  const specs = useMemo(() => {
    const m: Record<string, EditOp> = {};
    (opsSchema.data ?? []).forEach((s) => { m[s.id] = s; });
    return m;
  }, [opsSchema.data]);

  const recipe: Recipe = useMemo(() => ({ ops, base_run_id: rid }), [ops, rid]);
  const recipeKey = JSON.stringify(ops);
  const [dKey] = useDebouncedValue(recipeKey, 250);
  const dRecipe: Recipe = useMemo(() => ({ ops: JSON.parse(dKey), base_run_id: rid }), [dKey, rid]);

  const previewUrl = api.editPreviewUrl(safe, rid, dRecipe);
  const hist = useQuery({
    queryKey: ["edit-hist", safe, rid, dKey],
    queryFn: () => api.getHistogram(safe, rid, dRecipe),
    enabled: !!opsSchema.data,
  });

  // --- mutations -----------------------------------------------------------
  const saveRecipe = useMutation({
    mutationFn: () => api.putRecipe(safe, rid, recipe),
    onSuccess: () => {
      notifications.show({ message: "Recipe saved", color: "teal" });
      qc.invalidateQueries({ queryKey: ["recipe", safe, rid] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const auto = useMutation({
    mutationFn: () => api.autoProcess(safe, rid),
    onSuccess: (r) => {
      setOps((r.ops ?? []).map((o) => ({ ...o, uid: o.uid || uid() })));
      notifications.show({ message: "Auto-process applied — tweak from here", color: "violet" });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const exportRun = useMutation({
    mutationFn: () => api.exportRun(safe, rid, recipe, outputName.trim() || `${safe}_edit`, tiffMode),
    onSuccess: () => {
      notifications.show({ message: "Export started — saving full-resolution image", color: "violet" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      navigate("/jobs");
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // --- op list ops ---------------------------------------------------------
  const addOp = (spec: EditOp) => {
    const op = newOp(spec);
    setOps((p) => [...p, op]);
    setSelected(op.uid);
  };
  const move = (u: string, dir: -1 | 1) => setOps((p) => {
    const i = p.findIndex((o) => o.uid === u);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= p.length) return p;
    const next = [...p];
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  });
  const toggle = (u: string) =>
    setOps((p) => p.map((o) => (o.uid === u ? { ...o, enabled: !o.enabled } : o)));
  const remove = (u: string) => {
    setOps((p) => p.filter((o) => o.uid !== u));
    setSelected((s) => (s === u ? null : s));
  };
  const setParams = (u: string, params: Record<string, unknown>) =>
    setOps((p) => p.map((o) => (o.uid === u ? { ...o, params } : o)));

  const selectedOp = ops.find((o) => o.uid === selected) ?? null;
  const grouped = useMemo(() => {
    const g: Record<string, EditOp[]> = {};
    (opsSchema.data ?? []).forEach((s) => { (g[s.group] ??= []).push(s); });
    return g;
  }, [opsSchema.data]);

  if (opsSchema.isLoading || saved.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <Group gap="xs">
          <Button component={Link} to={`/targets/${safe}/history`} variant="subtle"
            leftSection={<IconArrowLeft size={16} />}>History</Button>
          <Title order={2}>Editor — {safe}</Title>
        </Group>
        <Group gap="xs">
          <Button variant="light" color="grape" leftSection={<IconSparkles size={16} />}
            loading={auto.isPending} onClick={() => auto.mutate()}>Auto-process</Button>
          <PresetMenu currentOps={ops} onApply={(o) => setOps(o)} />
          <Button variant="default" leftSection={<IconDeviceFloppy size={16} />}
            loading={saveRecipe.isPending} onClick={() => saveRecipe.mutate()}>Save</Button>
        </Group>
      </Group>

      <Grid>
        {/* Preview + histogram */}
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Paper withBorder p="xs">
            <div style={{ position: "relative", background: "#000", borderRadius: 8 }}>
              <Image src={previewUrl} alt="preview" fallbackSrc=""
                style={{ cursor: "zoom-in", maxHeight: "62vh", objectFit: "contain" }}
                onClick={() => setLightbox(true)} />
              <Button size="xs" variant="default" leftSection={<IconZoomScan size={14} />}
                style={{ position: "absolute", right: 8, top: 8 }}
                onClick={() => setLightbox(true)}>Zoom</Button>
            </div>
            <Histogram data={hist.data} />
          </Paper>
        </Grid.Col>

        {/* Controls */}
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack>
            <Menu shadow="md" position="bottom-start" width={240}>
              <Menu.Target>
                <Button leftSection={<IconPlus size={16} />} variant="light">Add operation</Button>
              </Menu.Target>
              <Menu.Dropdown mah={400} style={{ overflowY: "auto" }}>
                {GROUP_ORDER.filter((g) => grouped[g]).map((g) => (
                  <div key={g}>
                    <Menu.Label>{GROUP_LABELS[g] ?? g}</Menu.Label>
                    {grouped[g].map((s) => (
                      <Menu.Item key={s.id} onClick={() => addOp(s)}>{s.label}</Menu.Item>
                    ))}
                  </div>
                ))}
              </Menu.Dropdown>
            </Menu>

            <Paper withBorder p="sm">
              <Text fw={600} size="sm" mb={6}>Pipeline</Text>
              <OpList ops={ops} specs={specs} selected={selected} onSelect={setSelected}
                onMove={move} onToggle={toggle} onRemove={remove} />
            </Paper>

            {selectedOp && specs[selectedOp.id] ? (
              <Paper withBorder p="sm">
                <Text fw={600} size="sm" mb={6}>{specs[selectedOp.id].label}</Text>
                {specs[selectedOp.id].help ? (
                  <Text size="xs" c="dimmed" mb="xs">{specs[selectedOp.id].help}</Text>
                ) : null}
                <OpParamPanel spec={specs[selectedOp.id]} params={selectedOp.params}
                  onChange={(p) => setParams(selectedOp.uid, p)} />
              </Paper>
            ) : null}

            <Paper withBorder p="sm">
              <Text fw={600} size="sm" mb={6}>Export full resolution</Text>
              <Group align="flex-end" gap="xs">
                <TextInput label="Output name" placeholder={`${safe}_edit`} value={outputName}
                  onChange={(e) => setOutputName(e.currentTarget.value)} style={{ flex: 1 }} />
                <Select label="TIFF" w={130} data={["linear", "autostretch"]} value={tiffMode}
                  allowDeselect={false} onChange={(v) => setTiffMode(v ?? "linear")} />
              </Group>
              <Button mt="sm" fullWidth leftSection={<IconDownload size={16} />}
                loading={exportRun.isPending} onClick={() => exportRun.mutate()}>
                Export as new image
              </Button>
              <Text size="xs" c="dimmed" mt={6}>
                Writes a new stack run (FITS/TIFF/PNG). The original is never changed.
                Heavy ops (e.g. deconvolution) are applied here at full resolution.
              </Text>
            </Paper>
          </Stack>
        </Grid.Col>
      </Grid>

      <ImageLightbox src={lightbox ? previewUrl : null}
        title={`${safe} — edited`} onClose={() => setLightbox(false)} />
    </Stack>
  );
}
