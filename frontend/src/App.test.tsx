import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActiveJobsBadge, GlobalJobNotifier } from "./App";
import * as client from "./api/client";
import type { Job } from "./api/client";

const NOTIFY_KEY = "astrostack.notifyOnJobFinish";

function mkJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1", kind: "stack", target: "M 42", state: "running", phase: "aligning",
    done: 3, total: 10, detail: "", created_utc: null, started_utc: null,
    finished_utc: null, error: null, result: null,
    ...overrides,
  };
}

function renderWatcher(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <GlobalJobNotifier />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function renderBadge(qc: QueryClient) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <ActiveJobsBadge />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

// The header row is `wrap="nowrap"`, so on a phone this badge is squeezed between
// the title and the Scan button — measured clipped on all 14 probed routes by a
// dogfood pass that happened to have a job running (60 px box, 63 px word).
describe("ActiveJobsBadge", () => {
  const qc = () => new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  it("says the whole phrase to a reader who isn't looking at pixels", async () => {
    // `visibleFrom` hides with `display: none`, which hides from a screen reader
    // too — so the sentence is spelled out rather than left to the visible text.
    vi.spyOn(client.api, "listJobs").mockResolvedValue([mkJob({ state: "running" })]);
    renderBadge(qc());
    const spoken = await screen.findByText("1 job running");
    expect(spoken).toBeInTheDocument();
    // …and the part a phone actually draws is hidden from it, so it is not said
    // twice.
    const badge = spoken.closest('[class*="mantine-Badge-root"]');
    expect(badge?.querySelector("[aria-hidden]")?.textContent).toContain("1");
  });

  it("puts only the word behind the phone breakpoint, never the number", async () => {
    // A queued job counts as running work too, which is why the count can be
    // plural while one of them hasn't started.
    vi.spyOn(client.api, "listJobs").mockResolvedValue(
      [mkJob({ id: "a", state: "running" }), mkJob({ id: "b", state: "queued" })]);
    renderBadge(qc());
    const spoken = await screen.findByText("2 jobs running");
    const badge = spoken.closest('[class*="mantine-Badge-root"]');
    const word = badge?.querySelector('[class*="visible-from-xs"]');
    expect(word).not.toBeNull();
    expect(word?.textContent).toBe(" running");
    // The number sits outside it, so a phone still draws the count.
    const drawn = badge?.querySelector("[aria-hidden]");
    expect(drawn?.textContent?.replace(" running", "").trim()).toBe("2");
  });

  it("says nothing at all when no job is running or queued", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([mkJob({ state: "done" })]);
    const { container } = renderBadge(qc());
    await waitFor(() => expect(client.api.listJobs).toHaveBeenCalled());
    expect(container.querySelector('[class*="mantine-Badge-root"]')).toBeNull();
  });
});

// Slice (b): the finish ping must fire from the always-mounted watcher, i.e. with
// *no route page* rendered — the whole point is that a beginner who browsed away
// from the Jobs page still gets told.
describe("GlobalJobNotifier", () => {
  it("fires a desktop notification when a job finishes, with no page mounted", async () => {
    const ctor = vi.fn();
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "granted", requestPermission: vi.fn() }));
    localStorage.setItem(NOTIFY_KEY, "1");

    const listJobs = vi.spyOn(client.api, "listJobs").mockResolvedValue([mkJob({ state: "running" })]);
    const qc = new QueryClient();
    renderWatcher(qc);

    // First poll establishes the baseline — nothing fires for an already-seen job.
    // Wait for the running snapshot to actually land (and the effect to record it)
    // before swapping the mock, so the transition is genuinely running→done.
    await waitFor(() => expect(qc.getQueryData(["jobs"])).toEqual([mkJob({ state: "running" })]));
    await new Promise((r) => setTimeout(r, 0));
    expect(ctor).not.toHaveBeenCalled();

    // Next poll: the same job is now done → one ping.
    listJobs.mockResolvedValue([mkJob({ state: "done" })]);
    await qc.invalidateQueries({ queryKey: ["jobs"] });

    await waitFor(() => expect(ctor).toHaveBeenCalledTimes(1));
    const [title, opts] = ctor.mock.calls[0] as [string, NotificationOptions];
    expect(title).toContain("finished");
    expect(opts.tag).toBe("astrostack-job-job-1");
  });

  it("stays silent while the opt-in is off, even across a finish", async () => {
    const ctor = vi.fn();
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "granted", requestPermission: vi.fn() }));
    // NOTIFY_KEY deliberately unset → disabled.

    const listJobs = vi.spyOn(client.api, "listJobs").mockResolvedValue([mkJob({ state: "running" })]);
    const qc = new QueryClient();
    renderWatcher(qc);
    await waitFor(() => expect(listJobs).toHaveBeenCalled());

    listJobs.mockResolvedValue([mkJob({ state: "done" })]);
    await qc.invalidateQueries({ queryKey: ["jobs"] });
    await new Promise((r) => setTimeout(r, 50));

    expect(ctor).not.toHaveBeenCalled();
  });
});
