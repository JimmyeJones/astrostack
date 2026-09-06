import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IncomingCalibrationCard } from "./IncomingCalibrationCard";
import {
  folderSummaryLine, framesPhrase, offerHeadline, whatItDoes, whyWeThinkSo,
} from "./incomingCalibration";
import type { IncomingCalibrationFolder } from "../api/client";
import * as client from "../api/client";

function folder(
  over: Partial<IncomingCalibrationFolder> = {},
): IncomingCalibrationFolder {
  return {
    id: "Dark",
    name: "Dark",
    rel_path: "Dark",
    kind: "dark",
    declared: { dark: 4 },
    n_frames: 8,
    n_sampled: 4,
    exposure_s: 30,
    gain: 80,
    sensor_temp_c: -5,
    width_px: 1080,
    height_px: 1920,
    suggested_name: "Dark 30s gain 80 −5°C",
    have_master: null,
    ...over,
  };
}

function renderCard(onBuilt?: () => void) {
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={new QueryClient()}>
        <IncomingCalibrationCard onBuilt={onBuilt} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("incomingCalibration copy", () => {
  it("pluralises the frames phrase", () => {
    expect(framesPhrase("dark", 1)).toBe("1 dark frame");
    expect(framesPhrase("flat", 8)).toBe("8 flat frames");
  });

  it("leaves out what the frames never recorded rather than printing a dash", () => {
    expect(folderSummaryLine(folder())).toBe("8 dark frames · 30s · gain 80 · −5°C");
    expect(folderSummaryLine(folder({
      exposure_s: null, gain: null, sensor_temp_c: null,
    }))).toBe("8 dark frames");
  });

  it("says the frames told us, because that is what actually happened", () => {
    expect(whyWeThinkSo(folder())).toBe("4 of these frames say they are darks.");
  });

  it("echoes flat-darks as flat-darks even though they fill the dark slot", () => {
    expect(whyWeThinkSo(folder({ declared: { dark_flat: 4 } })))
      .toBe("4 of these frames say they are flat-darks.");
  });

  it("explains what each kind of master does for your picture", () => {
    expect(whatItDoes("dark")).toContain("hot pixels");
    expect(whatItDoes("flat")).toContain("dust");
    expect(whatItDoes("bias")).toContain("read-out");
  });

  it("has no headline when there is nothing to offer", () => {
    expect(offerHeadline([])).toBeNull();
    // Everything found is already built — nothing to nudge about.
    expect(offerHeadline([folder({ have_master: { id: 1, name: "Dark" } })]))
      .toBeNull();
  });

  it("names the kind when every folder is one kind, and generalises otherwise", () => {
    expect(offerHeadline([folder()])).toBe("You already have 8 dark frames");
    expect(offerHeadline([folder(), folder({ id: "b", rel_path: "b" })]))
      .toBe("You already have dark frames in 2 folders");
    expect(offerHeadline([folder(), folder({ id: "f", kind: "flat" })]))
      .toBe("You already have calibration frames in 2 folders");
  });
});

describe("IncomingCalibrationCard", () => {
  it("renders nothing when the incoming folder holds no declared calibration frames", async () => {
    vi.spyOn(client.api, "calibrationIncoming").mockResolvedValue({
      incoming_dir: "/data/incoming", folders: [],
    });

    renderCard();

    await waitFor(() =>
      expect(client.api.calibrationIncoming).toHaveBeenCalled());
    expect(screen.queryByText(/You already have/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Build master/ })).toBeNull();
  });

  it("offers the folder and builds it in one click", async () => {
    vi.spyOn(client.api, "calibrationIncoming").mockResolvedValue({
      incoming_dir: "/data/incoming", folders: [folder()],
    });
    const build = vi.spyOn(client.api, "buildMasterFromIncoming")
      .mockResolvedValue({ job_id: "j1" });
    const onBuilt = vi.fn();

    renderCard(onBuilt);

    expect(await screen.findByText("You already have 8 dark frames")).toBeTruthy();
    expect(screen.getByText(/4 of these frames say they are darks/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Build master dark/ }));

    await waitFor(() => expect(build).toHaveBeenCalledWith("Dark"));
    await waitFor(() => expect(onBuilt).toHaveBeenCalled());
  });

  it("says you already have it instead of offering a duplicate build", async () => {
    vi.spyOn(client.api, "calibrationIncoming").mockResolvedValue({
      incoming_dir: "/data/incoming",
      folders: [
        folder({ id: "a", rel_path: "Dark30",
          have_master: { id: 3, name: "Dark 30s gain 80 −5°C" } }),
        folder({ id: "b", rel_path: "Dark10", exposure_s: 10 }),
      ],
    });

    renderCard();

    expect(await screen.findByText(/Dark10/)).toBeTruthy();
    expect(screen.getByText(/You already have this one/)).toBeTruthy();
    // Exactly one build button: the covered folder doesn't get one.
    expect(screen.getAllByRole("button", { name: /Build master/ })).toHaveLength(1);
  });
});
