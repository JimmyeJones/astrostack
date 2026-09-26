import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NoiseDeltaStrip } from "./NoiseDeltaStrip";
import * as client from "../api/client";

function renderStrip() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient({
        defaultOptions: { queries: { retry: false } },
      })}>
        <NoiseDeltaStrip safe="M_42" newestId={9} previousId={7}
          newestLabel="18 Nov 2026" previousLabel="12 Nov 2026" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("NoiseDeltaStrip", () => {
  it("asks the backend nothing until the picture is wanted", async () => {
    const spy = vi.spyOn(client.api, "noiseDeltaInfo");
    renderStrip();
    expect(screen.getByTestId("noise-delta-show")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("shows the two crops, says which side is which, and reports the gain", async () => {
    vi.spyOn(client.api, "noiseDeltaInfo").mockResolvedValue({
      available: true, patch_px: 320, pixel_exact: true, noise_ratio: 1.6,
    });
    renderStrip();
    fireEvent.click(screen.getByTestId("noise-delta-show"));
    await waitFor(() =>
      expect(screen.getByTestId("noise-delta-strip")).toBeInTheDocument());
    const img = document.querySelector("img");
    expect(img).toHaveAttribute("src", "/api/targets/M_42/noise-delta?a=9&b=7");
    expect(screen.getByTestId("noise-delta-strip"))
      .toHaveTextContent(/Left: last time \(12 Nov 2026\)/);
    expect(screen.getByTestId("noise-delta-strip"))
      .toHaveTextContent(/Right: now \(18 Nov 2026\)/);
    expect(screen.getByTestId("noise-delta-verdict"))
      .toHaveTextContent(/1\.6× finer/);
  });

  it("draws the picture but no number when the two crops had to be resized", async () => {
    // pixel_exact false means one side was resampled to be shown beside the
    // other, which lowers its grain for reasons that are not stacking. The
    // picture is still a fair comparison; the number would not be.
    vi.spyOn(client.api, "noiseDeltaInfo").mockResolvedValue({
      available: true, patch_px: 320, pixel_exact: false, noise_ratio: null,
    });
    renderStrip();
    fireEvent.click(screen.getByTestId("noise-delta-show"));
    await waitFor(() =>
      expect(screen.getByTestId("noise-delta-strip")).toBeInTheDocument());
    expect(screen.queryByTestId("noise-delta-verdict")).toBeNull();
  });

  it("renders nothing at all when there is no honest patch to show", async () => {
    // An editor export on either side, a canvas too small for a patch, or no
    // patch of sky covered in both — `available: false`, never an error.
    vi.spyOn(client.api, "noiseDeltaInfo").mockResolvedValue({ available: false });
    const { container } = renderStrip();
    fireEvent.click(screen.getByTestId("noise-delta-show"));
    await waitFor(() => expect(client.api.noiseDeltaInfo).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector("img")).toBeNull());
    expect(screen.queryByTestId("noise-delta-strip")).toBeNull();
    expect(screen.queryByTestId("noise-delta-show")).toBeNull();
  });

  it("stays silent when the request itself fails", async () => {
    // A best-effort read: an older backend has no such endpoint, and a card on
    // the busiest page in the app must not turn that into a red error.
    vi.spyOn(client.api, "noiseDeltaInfo").mockRejectedValue(new Error("404"));
    const { container } = renderStrip();
    fireEvent.click(screen.getByTestId("noise-delta-show"));
    await waitFor(() => expect(client.api.noiseDeltaInfo).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector("img")).toBeNull());
    expect(screen.queryByTestId("noise-delta-strip")).toBeNull();
  });
});
