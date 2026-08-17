import { useMemo, useState } from "react";
import {
  Badge, Box, Button, Center, Group, Loader, Paper, ScrollArea, SegmentedControl,
  Stack, Switch, Text, TextInput, Title,
} from "@mantine/core";
import { IconDownload, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type LogEntry } from "../api/client";
import { QueryError } from "../components/QueryError";

const LEVEL_COLOR: Record<string, string> = {
  DEBUG: "gray",
  INFO: "blue",
  WARNING: "yellow",
  ERROR: "red",
  CRITICAL: "red",
};

export function LogsView() {
  const [level, setLevel] = useState<string>("INFO");
  const [auto, setAuto] = useState(true);
  const [search, setSearch] = useState("");

  const logs = useQuery({
    queryKey: ["logs", level, 2000],
    queryFn: () => api.getLogs(level === "ALL" ? undefined : level, 2000),
    refetchInterval: auto ? 3000 : false,
  });

  const entries = logs.data?.logs ?? [];
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) => e.message.toLowerCase().includes(q) || e.logger.toLowerCase().includes(q),
    );
  }, [entries, search]);

  const download = () => {
    const text = filtered
      .map((e) => `${e.ts} ${e.level} ${e.logger}: ${e.message}`)
      .join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `astrostack-logs-${new Date().toISOString().slice(0, 19)}.txt`;
    a.click();
    // Revoke after the browser has had a tick to start the download (revoking
    // synchronously can cancel it in some browsers).
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <Stack h="calc(100dvh - 110px)">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Group gap="sm">
          <Title order={2}>Logs</Title>
          <Badge variant="light">{filtered.length}</Badge>
        </Group>
        <Group gap="sm" wrap="wrap">
          <SegmentedControl
            size="xs" value={level} onChange={setLevel}
            data={["ALL", "INFO", "WARNING", "ERROR"]}
          />
          <Switch size="xs" label="Auto-refresh" checked={auto}
            onChange={(e) => setAuto(e.currentTarget.checked)} />
          <Button size="xs" variant="light" leftSection={<IconDownload size={14} />}
            onClick={download} disabled={filtered.length === 0}>
            Download
          </Button>
        </Group>
      </Group>

      <TextInput
        size="xs" placeholder="Filter messages…"
        leftSection={<IconSearch size={14} />}
        value={search} onChange={(e) => setSearch(e.currentTarget.value)}
      />

      <Paper withBorder style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        {logs.isError && !logs.data ? (
          <QueryError error={logs.error} onRetry={() => logs.refetch()} />
        ) : logs.isLoading ? (
          <Center h="100%"><Loader /></Center>
        ) : filtered.length === 0 ? (
          <Center h="100%"><Text c="dimmed">No log lines{search ? " match the filter" : " yet"}.</Text></Center>
        ) : (
          <ScrollArea h="100%" type="auto">
            <Box p="xs" style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12 }}>
              {filtered.map((e: LogEntry) => (
                // The row may wrap, so on a phone the message drops to its own
                // line under the stamp instead of being squeezed beside it. The
                // three prefix chips are all `flexShrink: 0` and together take
                // ~220 px of a 420 px screen; with the row pinned `nowrap` the
                // message was left ~10 px and `wordBreak: break-word` then set a
                // long path one *character* per line — a single log entry 211
                // lines tall. On a desktop row (prefix + 260 ≪ 1100) nothing
                // wraps, so this is unchanged where it was already fine.
                <Group key={e.seq} gap={8} align="flex-start"
                  style={{ padding: "2px 4px", borderBottom: "1px solid var(--mantine-color-dark-6)" }}>
                  <Group gap={8} wrap="nowrap" style={{ flexShrink: 0 }}>
                    <Text span c="dimmed">{e.ts.slice(11, 19)}</Text>
                    <Badge size="xs" color={LEVEL_COLOR[e.level] ?? "gray"} variant="light"
                      style={{ flexShrink: 0, width: 64 }}>
                      {e.level}
                    </Badge>
                    <Text span c="dimmed" style={{ maxWidth: 220 }} truncate>
                      {e.logger}
                    </Text>
                  </Group>
                  <Text span style={{
                    // Based on its own content rather than zero, so it fills a
                    // wide row but takes a line of its own before it is crushed.
                    flex: "1 1 260px", minWidth: 0,
                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                  }}>
                    {e.message}
                  </Text>
                </Group>
              ))}
            </Box>
          </ScrollArea>
        )}
      </Paper>
    </Stack>
  );
}
