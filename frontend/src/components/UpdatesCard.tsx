import { Alert, Button, Code, Collapse, Group, Modal, Paper, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type UpdatesStatus } from "../api/client";

const INSTALL_CMD = "sudo python3 scripts/update_agent.py --install";

function ago(ts: number | null | undefined, now: number): string {
  if (!ts) return "never";
  const m = Math.round((now - ts) / 60);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

export type UpdatesView = {
  kind: "setup" | "stale" | "busy" | "restarting" | "ready";
  headline: string;
  detail: string | null;
};

/** What the card says, from the helper's status. Pure, so it is tested without
 *  rendering. `restarting` is the update or rollback this page asked for and has
 *  no answer to yet — the helper cannot report it while deploy.sh has the app
 *  stopped, so only the page knows. */
export function updatesView(
  st: UpdatesStatus, restarting: "update" | "rollback" | null, now = Date.now() / 1000,
): UpdatesView {
  const on = `You're on v${st.running_version}.`;
  if (restarting) {
    return {
      kind: "restarting",
      headline: restarting === "update"
        ? "Updating — the app is backing up your data and rebuilding."
        : "Going back — the app is restarting on the earlier version.",
      detail: "This takes a few minutes and the app is unavailable meanwhile. "
        + "This page reconnects and reloads by itself.",
    };
  }
  if (st.helper === "missing") {
    return {
      kind: "setup",
      headline: on,
      detail: "One-click updates need a small helper on your NAS, set up once.",
    };
  }
  if (st.helper === "stale") {
    return {
      kind: "stale",
      headline: on,
      detail: `The update helper on your NAS last checked in ${ago(st.helper_seen_at, now)}. `
        + "Is its cron job still switched on (System → Advanced Settings → Cron Jobs)?",
    };
  }
  const action = st.pending?.action ?? (st.state !== "idle" ? st.job?.action : null);
  if (action) {
    const what = action === "check" ? "Checking for updates…"
      : action === "update" ? "Updating…" : "Rolling back…";
    return {
      kind: "busy",
      headline: what,
      detail: st.pending ? "Waiting for the helper on your NAS to pick this up (within a minute)." : null,
    };
  }
  if (st.update_available && st.available?.version) {
    return {
      kind: "ready",
      headline: `${on} Version ${st.available.version} is ready to install.`,
      detail: "It has been on the main line for at least three days with every test passing. "
        + "Updating stops the app for a few minutes, backs up your databases and settings "
        + "first, and never touches your subs in incoming/.",
    };
  }
  return {
    kind: "ready",
    headline: on,
    detail: st.checked_at
      ? `That's the newest tested version (checked ${ago(st.checked_at, now)}).`
      : "Press Check for updates to see whether a newer tested version is out.",
  };
}

/** Settings → Maintenance → App updates. */
export function UpdatesCard() {
  const qc = useQueryClient();
  // The request this page sent and is waiting on. It is resolved when the helper
  // reports a result carrying the same id; until then an update or rollback reads
  // as "restarting", including while the app itself is down.
  const [asked, setAsked] = useState<{ id: string; action: string } | null>(null);
  const [showLog, setShowLog] = useState(false);
  const [rollbackOpen, setRollbackOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const loadedVersion = useRef<string | null>(null);

  const q = useQuery({
    queryKey: ["updates"],
    queryFn: api.getUpdates,
    retry: false,
    refetchInterval: (query) => {
      const d = query.state.data;
      const waiting = !!asked && d?.last_result?.id !== asked.id;
      const busy = waiting || !!d?.pending || (d != null && d.state !== "idle");
      return busy ? 3000 : false;
    },
  });
  const st = q.data;
  const answered = !!asked && st?.last_result?.id === asked.id;
  const restarting = asked && asked.action !== "check" && !answered
    ? (asked.action === "rollback" ? "rollback" as const : "update" as const) : null;
  if (st && loadedVersion.current === null) loadedVersion.current = st.running_version;

  // A new version answering means the update finished: reload so the browser
  // runs the new app's own page rather than this one.
  const newVersion = st && loadedVersion.current !== null && st.running_version !== loadedVersion.current;
  useEffect(() => {
    if (!newVersion) return;
    const t = window.setTimeout(() => window.location.reload(), 2500);
    return () => window.clearTimeout(t);
  }, [newVersion]);

  const onDone = (res: { id: string; action: string }) => {
    setAsked(res);
    void qc.invalidateQueries({ queryKey: ["updates"] });
  };
  const onError = (e: Error) => notifications.show({ color: "red", title: "Couldn't ask for that", message: e.message });
  const check = useMutation({ mutationFn: api.checkUpdates, onSuccess: onDone, onError });
  const apply = useMutation({ mutationFn: api.applyUpdate, onSuccess: onDone, onError });
  const rollback = useMutation({
    mutationFn: (restore: boolean) => api.rollbackUpdate(restore),
    onSuccess: (res) => { setRollbackOpen(false); setTyped(""); onDone(res); },
    onError,
  });

  if (!st) {
    return (
      <Paper withBorder p="lg">
        <Stack gap="xs">
          <Text fw={600}>App updates</Text>
          <Text size="sm" c="dimmed">{q.isError ? (restarting ? "The app is restarting…" : "Couldn't read the update status.") : "Loading…"}</Text>
        </Stack>
      </Paper>
    );
  }

  const view = newVersion
    ? { kind: "restarting" as const, headline: `Updated to v${st.running_version}. Reloading…`, detail: null }
    : updatesView(st, restarting, Date.now() / 1000);
  const last = st.last_result;
  const failed = !!last && !last.ok && restarting === null;
  const rb = st.rollback;
  const idle = view.kind === "ready";

  const onUpdate = () => {
    if (window.confirm(
      `Update to v${st.available?.version}?\n\nThe app stops for a few minutes while it backs up your `
      + "databases and settings and rebuilds. Your subs in incoming/ are not touched, and you can go "
      + "back with \"Go back\" on this card if anything looks wrong.",
    )) apply.mutate();
  };

  return (
    <Paper withBorder p="lg">
      <Stack gap="xs">
        <Text fw={600}>App updates</Text>
        <Text size="sm">{view.headline}</Text>
        {view.detail && <Text size="sm" c="dimmed">{view.detail}</Text>}

        {view.kind === "setup" && (
          <Stack gap={4}>
            <Text size="sm">
              1. On the NAS, in the folder you installed AstroStack from, run:
            </Text>
            <Code block>{INSTALL_CMD}</Code>
            <Text size="sm">
              2. It prints one line to add under <b>System → Advanced Settings → Cron Jobs</b>.
              Add it, and this card comes alive within a minute.
            </Text>
            <Text size="xs" c="dimmed">
              Why a helper: the app runs inside the container an update rebuilds, so it can only
              ask. The helper does the update the same way <Code>sudo scripts/deploy.sh</Code> does,
              and only reaches the internet when you press Check or Update here.
            </Text>
          </Stack>
        )}

        {failed && (
          <Alert color="red" variant="light" title={last.action === "check" ? "The check didn't work" : "That didn't finish"}>
            <Text size="sm">{last.message}</Text>
            {last.log_tail.length > 0 && (
              <>
                <Button variant="subtle" size="compact-xs" onClick={() => setShowLog((v) => !v)}>
                  {showLog ? "Hide details" : "Show details"}
                </Button>
                <Collapse in={showLog}>
                  <Code block>{last.log_tail.join("\n")}</Code>
                </Collapse>
              </>
            )}
          </Alert>
        )}

        {idle && (
          <Group>
            {st.update_available && st.available?.version ? (
              <Button onClick={onUpdate} loading={apply.isPending}>
                Update to v{st.available.version}
              </Button>
            ) : null}
            <Button variant={st.update_available ? "default" : "filled"} onClick={() => check.mutate()} loading={check.isPending}>
              Check for updates
            </Button>
            {rb?.to_version && (
              <Button variant="subtle" color="gray" onClick={() => setRollbackOpen(true)}>
                Go back to v{rb.to_version}
              </Button>
            )}
          </Group>
        )}
      </Stack>

      <Modal opened={rollbackOpen} onClose={() => { setRollbackOpen(false); setTyped(""); }}
        title={`Go back to v${rb?.to_version ?? ""}?`}>
        <Stack gap="sm">
          {rb?.needs_restore_data ? (
            <>
              <Text size="sm">
                v{rb.to_version} can't read the newer database format, so going back also puts back
                the backup taken just before the update. <b>Anything the app did since then is lost</b> —
                new stacks, edits, and newly imported frames' records (they come back on the next scan).
              </Text>
              <Text size="sm">Your subs in incoming/ are not touched either way.</Text>
              <TextInput label="Type RESTORE to confirm" value={typed}
                onChange={(e) => setTyped(e.currentTarget.value)} autoComplete="off" />
            </>
          ) : (
            <Text size="sm">
              The app restarts on v{rb?.to_version}. Your data stays as it is — that version can read it.
            </Text>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => { setRollbackOpen(false); setTyped(""); }}>Cancel</Button>
            <Button color="red" loading={rollback.isPending}
              disabled={!!rb?.needs_restore_data && typed !== "RESTORE"}
              onClick={() => rollback.mutate(!!rb?.needs_restore_data)}>
              Go back
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  );
}
