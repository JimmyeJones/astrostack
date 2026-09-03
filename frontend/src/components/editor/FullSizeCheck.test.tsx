import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FullSizeCheck } from "./FullSizeCheck";
import * as client from "../../api/client";
import type { LoupeInfo, Recipe } from "../../api/client";

const RECIPE: Recipe = { ops: [{ uid: "st", id: "tone.stretch", enabled: true, params: {} }] };

const AVAILABLE: LoupeInfo = {
  available: true, reason: null, proxy_scale: 4, size_px: 512,
  canvas_width: 6000, canvas_height: 4000,
};

function wrap(info: Partial<LoupeInfo> = {}) {
  vi.spyOn(client.api, "loupeInfo").mockResolvedValue({ ...AVAILABLE, ...info });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <FullSizeCheck safe="M_42" runId={7} recipe={RECIPE}
          shownSourceW={6000} shownSourceH={4000} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("FullSizeCheck", () => {
  it("offers the check when the preview is a decimated proxy", async () => {
    wrap();
    expect(await screen.findByText("Check it at full size")).toBeInTheDocument();
  });

  it("takes no line at all when there is nothing to check", async () => {
    // The editor's standing complaint is that it is too busy, so a control that
    // cannot act renders nothing — not a disabled button, not an explanation.
    wrap({ available: false, proxy_scale: 1,
           reason: "This picture is small enough that the preview already shows every pixel." });
    await waitFor(() => expect(client.api.loupeInfo).toHaveBeenCalled());
    expect(screen.queryByText("Check it at full size")).not.toBeInTheDocument();
  });

  it("stays hidden when the backend is too old to answer", async () => {
    vi.spyOn(client.api, "loupeInfo").mockRejectedValue(new Error("404"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <FullSizeCheck safe="M_42" runId={7} recipe={RECIPE} />
        </QueryClientProvider>
      </MantineProvider>,
    );
    await waitFor(() => expect(client.api.loupeInfo).toHaveBeenCalled());
    expect(screen.queryByText("Check it at full size")).not.toBeInTheDocument();
  });

  it("shows the picture's centre first, and says what it is looking at", async () => {
    wrap();
    fireEvent.click(await screen.findByTestId("full-size-check-open"));

    const img = await screen.findByTestId("full-size-check-image");
    expect(img.getAttribute("src")).toContain("/editor/loupe?");
    expect(img.getAttribute("src")).toContain("fx=0.5000&fy=0.5000&size=512");
    expect(img).toHaveAttribute("width", "512");
    // Explained in the words the reader uses — the four advisories this replaces
    // were all honest and all useless to someone who can't act on them.
    expect(screen.getByText(/512 × 512 piece of your finished picture/))
      .toBeInTheDocument();
  });

  it("moves the window when the navigator is tapped, and marks where it is", async () => {
    wrap();
    fireEvent.click(await screen.findByTestId("full-size-check-open"));
    const nav = await screen.findByTestId("full-size-check-navigator");
    vi.spyOn(nav, "getBoundingClientRect").mockReturnValue(
      { left: 0, top: 0, width: 200, height: 100 } as DOMRect);

    fireEvent.click(nav, { clientX: 50, clientY: 75 });

    await waitFor(() => expect(
      screen.getByTestId("full-size-check-image").getAttribute("src"))
      .toContain("fx=0.2500&fy=0.7500"));
    // …and the marker follows, at the window's true share of the picture
    // (512 of 6000 px wide).
    const marker = screen.getByTestId("full-size-check-marker");
    expect(marker.style.width).toMatch(/^8\.53/);
    expect(marker.style.left).toMatch(/^20\.7/);
  });
});
