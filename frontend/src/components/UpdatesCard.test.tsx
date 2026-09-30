import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { UpdatesStatus } from "../api/client";
import { UpdatesCard, updatesView } from "./UpdatesCard";

const NOW = 1_800_000_000;

function status(over: Partial<UpdatesStatus> = {}): UpdatesStatus {
  return {
    running_version: "0.455.7", helper: "ok", helper_seen_at: NOW - 20, state: "idle",
    job: null, pending: null, checked_at: null, available: null, update_available: false,
    rollback: null, last_result: null, ...over,
  };
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <UpdatesCard />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("updatesView", () => {
  it("asks for the one-time setup when no helper has ever reported", () => {
    const v = updatesView(status({ helper: "missing" }), null, NOW);
    expect(v.kind).toBe("setup");
    expect(v.headline).toBe("You're on v0.455.7.");
  });

  it("points at the cron job when the helper went quiet", () => {
    const v = updatesView(status({ helper: "stale", helper_seen_at: NOW - 3 * 3600 }), null, NOW);
    expect(v.kind).toBe("stale");
    expect(v.detail).toMatch(/last checked in 3 h ago/);
  });

  it("offers the tested version when a check found a newer one", () => {
    const v = updatesView(status({ update_available: true, available: { version: "0.490.0" } }), null, NOW);
    expect(v.headline).toBe("You're on v0.455.7. Version 0.490.0 is ready to install.");
    expect(v.detail).toMatch(/never touches your subs in incoming\//);
  });

  it("says up to date only once something was actually checked", () => {
    expect(updatesView(status(), null, NOW).detail).toMatch(/Press Check for updates/);
    expect(updatesView(status({ checked_at: NOW - 120 }), null, NOW).detail)
      .toBe("That's the newest tested version (checked 2 min ago).");
  });

  it("reads a queued or running request as busy", () => {
    expect(updatesView(status({ pending: { id: "a", action: "check" } }), null, NOW).headline)
      .toBe("Checking for updates…");
    expect(updatesView(status({ state: "rolling_back", job: { id: "a", action: "rollback", started_at: NOW } }), null, NOW).headline)
      .toBe("Rolling back…");
  });

  it("says the app is restarting while its own update is unanswered", () => {
    expect(updatesView(status(), "update", NOW).kind).toBe("restarting");
    expect(updatesView(status(), "rollback", NOW).headline).toMatch(/^Going back/);
  });
});

describe("UpdatesCard", () => {
  it("shows the install command when the helper is missing, and no buttons", async () => {
    vi.spyOn(client.api, "getUpdates").mockResolvedValue(status({ helper: "missing" }));
    renderCard();
    expect(await screen.findByText("sudo python3 scripts/update_agent.py --install")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Check for updates/ })).toBeNull();
  });

  it("updates only after the owner confirms", async () => {
    vi.spyOn(client.api, "getUpdates").mockResolvedValue(
      status({ update_available: true, available: { version: "0.490.0" } }));
    const apply = vi.spyOn(client.api, "applyUpdate").mockResolvedValue({ id: "r1", action: "update" });
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderCard();
    const btn = await screen.findByRole("button", { name: "Update to v0.490.0" });
    fireEvent.click(btn);
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(btn);
    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Updating — the app is backing up your data/)).toBeTruthy();
  });

  it("a data-restoring rollback stays disabled until RESTORE is typed", async () => {
    vi.spyOn(client.api, "getUpdates").mockResolvedValue(
      status({ rollback: { to_version: "0.455.7", needs_restore_data: true, backup: "snapshot" } }));
    const rb = vi.spyOn(client.api, "rollbackUpdate").mockResolvedValue({ id: "r2", action: "rollback" });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "Go back to v0.455.7" }));
    const go = await screen.findByRole("button", { name: "Go back" });
    expect((go as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Type RESTORE to confirm"), { target: { value: "restore" } });
    expect((go as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Type RESTORE to confirm"), { target: { value: "RESTORE" } });
    expect((go as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(go);
    await waitFor(() => expect(rb).toHaveBeenCalledWith(true));
  });

  it("shows why the last attempt failed, with its log behind a toggle", async () => {
    vi.spyOn(client.api, "getUpdates").mockResolvedValue(status({
      last_result: { id: "r1", action: "update", ok: false, message: "The update did not finish.",
        finished_at: NOW, log_tail: ["ERROR: this clone has local edits"] },
    }));
    renderCard();
    expect(await screen.findByText("The update did not finish.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText("ERROR: this clone has local edits")).toBeTruthy();
  });
});
