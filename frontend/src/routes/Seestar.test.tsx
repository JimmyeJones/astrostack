import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SeestarView } from "./Seestar";
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

describe("SeestarView", () => {
  it("prompts to enable the integration when it is off", async () => {
    vi.spyOn(client.api, "getSeestarDevices").mockResolvedValue({
      enabled: false, control_enabled: false, devices: [],
    } as SeestarDevices);
    renderSeestar();
    await waitFor(() => expect(screen.getByText(/Settings → Telescope/)).toBeInTheDocument());
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
});
