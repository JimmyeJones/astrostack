import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SeestarView, authLine, integrationText } from "./Seestar";
import * as client from "../api/client";
import type { SeestarDevices } from "../api/client";

function renderSeestar() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><SeestarView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

const CONTROLLABLE = {
  enabled: true, control_enabled: true,
  devices: [{
    id: "192.168.1.50", ip: "192.168.1.50", device_name: "Seestar S30",
    model: "Seestar S30", firmware: "9.75", reachable: true, connected: true,
    last_seen_utc: null, error: null, telemetry: null, auth: "verified",
  }],
} as unknown as SeestarDevices;

describe("SeestarView — the controls Studio verified (slice 4)", () => {
  it.each([
    ["Pause stacking", "seestarStopStack", /Stacking paused/],
    ["Resume stacking", "seestarResume", /Stacking resumed/],
    ["Autofocus", "seestarAutofocus", /Autofocus started/],
    ["Plate solve", "seestarSolve", /Plate solve started/],
  ] as const)("%s sends its command and says so", async (label, method, notice) => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue(CONTROLLABLE);
    const spy = vi.spyOn(client.api, method).mockResolvedValue({ ok: true });
    const show = vi.spyOn(notifications, "show").mockReturnValue("");
    renderSeestar();
    fireEvent.click(await screen.findByRole("button", { name: label }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith("192.168.1.50"));
    await waitFor(() => expect(show).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringMatching(notice), color: "teal" })));
  });

  it("nudges the focus 10 steps either way and reports where it went", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue(CONTROLLABLE);
    const spy = vi.spyOn(client.api, "seestarFocus")
      .mockResolvedValue({ ok: true, result: { from: 1560, to: 1550 } });
    const show = vi.spyOn(notifications, "show").mockReturnValue("");
    renderSeestar();
    fireEvent.click(await screen.findByRole("button", { name: "Focus −10" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith("192.168.1.50", -10));
    await waitFor(() => expect(show).toHaveBeenCalledWith(
      expect.objectContaining({ message: "Focuser moved to 1550" })));
    fireEvent.click(screen.getByRole("button", { name: "Focus +10" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith("192.168.1.50", 10));
  });

  it("shows none of them while control is off", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue(
      { ...CONTROLLABLE, control_enabled: false } as SeestarDevices);
    renderSeestar();
    await screen.findByText("Seestar S30");
    for (const label of ["Pause stacking", "Resume stacking", "Autofocus", "Plate solve", "Focus −10"]) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
  });
});

describe("SeestarView", () => {
  it("prompts to enable the integration when it is off", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue({
      enabled: false, control_enabled: false, devices: [],
    } as SeestarDevices);
    renderSeestar();
    await waitFor(() => expect(screen.getByText(/Settings → Telescope/)).toBeInTheDocument());
  });

  it("makes the 'turn it on in Settings' instruction a link to the section that holds it", async () => {
    // The page is blocked and tells the user exactly what to do; now that each
    // Settings section has its own address, being told is one tap from doing.
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue({
      enabled: false, control_enabled: false, devices: [],
    } as SeestarDevices);
    renderSeestar();
    const link = await screen.findByRole("link", { name: /Settings → Telescope/ });
    expect(link).toHaveAttribute("href", "/settings/telescope");
  });

  it("links the monitoring-only note and the no-devices hint to the same section", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue({
      enabled: true, control_enabled: false, devices: [],
    } as SeestarDevices);
    renderSeestar();
    const enable = await screen.findByRole("link", { name: "Enable it in Settings" });
    expect(enable).toHaveAttribute("href", "/settings/telescope");
    expect(screen.getByRole("link", { name: /Settings → Telescope/ }))
      .toHaveAttribute("href", "/settings/telescope");
  });

  it("renders live telemetry for a connected device", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue({
      enabled: true, control_enabled: false,
      devices: [{
        id: "192.168.1.50", ip: "192.168.1.50", device_name: "Seestar S50",
        model: "Seestar S50", firmware: "4.02", reachable: true, connected: true,
        last_seen_utc: null, error: null,
        telemetry: {
          device_name: "Seestar S50", model: "Seestar S50", firmware: "4.02",
          temp_c: 40, battery_pct: 77, charging: true, charger_status: "Charging",
          free_storage_mb: 10240, total_storage_mb: 30720, mode: "star", state: "working",
          stage: "Stack", target_name: "M 42", stacked_frames: 42, dropped_frames: 1,
          ra_hours: 5.6, dec_deg: -5.4,
        },
      }],
    } as SeestarDevices);
    renderSeestar();

    await waitFor(() => expect(screen.getByText("Seestar S50")).toBeInTheDocument());
    expect(screen.getByText("77%")).toBeInTheDocument();
    expect(screen.getByText("M 42")).toBeInTheDocument();
    // Control panel hidden because control_enabled is false.
    expect(screen.queryByText("Goto & image")).not.toBeInTheDocument();
  });

  it("surfaces a retryable error instead of spinning forever on API failure", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockRejectedValue(new Error("boom"));
    render(
      <MantineProvider>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter><SeestarView /></MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText("Couldn't load this page")).toBeInTheDocument());
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });
  it("says in one line whether the scope accepted the Seestar key, and links the fix", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue({
      enabled: true, control_enabled: false,
      devices: [{
        id: "10.0.0.5", ip: "10.0.0.5", device_name: "Seestar S30", model: "Seestar S30",
        firmware: "9.75", reachable: true, connected: true, last_seen_utc: null,
        error: null, telemetry: null, auth: "key_needed",
      }],
    } as SeestarDevices);
    renderSeestar();
    await waitFor(() =>
      expect(screen.getByText(/This scope needs your Seestar key/)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "add it in Settings" }))
      .toHaveAttribute("href", "/settings/telescope");
  });

  it("maps every handshake outcome to plain words, and says nothing before one", () => {
    expect(authLine("verified")?.text).toMatch(/Key accepted/);
    expect(authLine("not_needed")?.fix).toBe(false);
    expect(authLine("rejected")?.fix).toBe(true);
    expect(authLine("failed")?.text).toMatch(/trying again/);
    expect(authLine(null)).toBeNull();
    expect(authLine(undefined)).toBeNull();
  });

  it("shows the scope's newest picture, links full size, and says idle after a stop", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue({
      enabled: true, control_enabled: false,
      devices: [{
        id: "10.0.0.5", ip: "10.0.0.5", device_name: "Seestar S30", model: "Seestar S30",
        firmware: "9.75", reachable: true, connected: true, last_seen_utc: null,
        error: null, auth: "verified",
        telemetry: {
          device_name: "Seestar S30", model: "Seestar S30", firmware: "9.75",
          temp_c: 38, battery_pct: 71, charging: false, charger_status: "Discharging",
          free_storage_mb: 35690, total_storage_mb: 51854, mode: null, state: "idle",
          stage: null, target_name: "M 42", stacked_frames: 12, dropped_frames: 0,
          ra_hours: 5.6, dec_deg: -5.4, exposure_s: 10, integration_s: 7500,
          latest_image: {
            name: "M 42", count: 12, stacked: true,
            thumb: "MyWorks/M 42/Stacked_12_thn.jpg", full: "MyWorks/M 42/Stacked_12.jpg",
          },
        },
      }],
    } as SeestarDevices);
    renderSeestar();
    const img = await screen.findByAltText(/Newest picture on the scope: M 42 · 12 frames/);
    expect(img).toHaveAttribute("src",
      "/api/seestar/10.0.0.5/image?kind=thumb&v=MyWorks%2FM%2042%2FStacked_12_thn.jpg");
    expect(img.closest("a")).toHaveAttribute("href",
      "/api/seestar/10.0.0.5/image?kind=full&v=MyWorks%2FM%2042%2FStacked_12.jpg");
    expect(screen.getByText(/2 h 05 min total \(10 s subs\)/)).toBeInTheDocument();
    expect(screen.getAllByText("idle").length).toBeGreaterThan(0);
    // A stopped view is not "working": no animated bar.
    expect(document.querySelector(".mantine-Progress-root")).toBeNull();
  });

  it("puts total integration into plain words", () => {
    expect(integrationText(40)).toBe("40 s");
    expect(integrationText(720)).toBe("12 min");
    expect(integrationText(7500)).toBe("2 h 05 min");
    expect(integrationText(0)).toBeNull();
    expect(integrationText(null)).toBeNull();
  });
});
