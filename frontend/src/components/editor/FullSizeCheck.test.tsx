import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FullSizeCheck } from "./FullSizeCheck";
import * as client from "../../api/client";
import type { LoupeInfo, LoupeWindow, Recipe } from "../../api/client";

const RECIPE: Recipe = { ops: [{ uid: "st", id: "tone.stretch", enabled: true, params: {} }] };

const AVAILABLE: LoupeInfo = {
  available: true, reason: null, proxy_scale: 4, size_px: 512,
  canvas_width: 6000, canvas_height: 4000,
};

/** The window the server says it cut, centred in a 6000 × 4000 canvas. */
const CENTRED: LoupeWindow = {
  x: 2744, y: 1744, width: 512, height: 512,
  canvas_width: 6000, canvas_height: 4000, proxy_scale: 4,
};

/** Record the loupe requests the component makes, and answer them. Fetched (not
 *  hung off an `<img src>`) because the source rectangle only exists as a
 *  response header, so the URL is what the assertions have to read. */
let loupeCalls: string[] = [];

function mockLoupe(window_: LoupeWindow | null = CENTRED) {
  return vi.spyOn(client.api, "fetchLoupe").mockImplementation(
    async (safe, runId, recipe, fx, fy, size) => {
      loupeCalls.push(client.api.editLoupeUrl(safe, runId, recipe, fx, fy, size));
      return { url: `blob:loupe-${fx}-${fy}`, window: window_ };
    });
}

beforeEach(() => {
  loupeCalls = [];
  // jsdom has no revokeObjectURL; the component revokes every blob it shows.
  vi.stubGlobal("URL", Object.assign(URL, { revokeObjectURL: () => {} }));
});

function wrap(info: Partial<LoupeInfo> = {}) {
  vi.spyOn(client.api, "loupeInfo").mockResolvedValue({ ...AVAILABLE, ...info });
  mockLoupe();
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

    await screen.findByTestId("full-size-check-image");
    expect(loupeCalls[0]).toContain("/editor/loupe?");
    expect(loupeCalls[0]).toContain("fx=0.5000&fy=0.5000&size=512");
    expect(screen.getByTestId("full-size-check-image")).toHaveAttribute("width", "512");
    // Explained in the words the reader uses — the four advisories this replaces
    // were all honest and all useless to someone who can't act on them.
    expect(screen.getByText(/512 × 512 piece of your finished picture/))
      .toBeInTheDocument();
  });

  it("says where in the picture it is looking, from the server's own answer", async () => {
    // The click only ever reports a fraction of the *preview*; with a crop in the
    // recipe that maps somewhere the browser cannot compute. The server sends the
    // rectangle it actually cut in `X-Loupe-Window`, and this is its reader.
    wrap();
    fireEvent.click(await screen.findByTestId("full-size-check-open"));
    expect(await screen.findByTestId("full-size-check-where"))
      .toHaveTextContent("This is the middle of your picture.");
  });

  it("shows the window but no location when the backend sends no rectangle", async () => {
    // An older backend (or an unreadable header) must cost the picture nothing —
    // it just stops naming the spot rather than guessing one.
    vi.spyOn(client.api, "loupeInfo").mockResolvedValue(AVAILABLE);
    mockLoupe(null);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <FullSizeCheck safe="M_42" runId={7} recipe={RECIPE}
            shownSourceW={6000} shownSourceH={4000} />
        </QueryClientProvider>
      </MantineProvider>,
    );
    fireEvent.click(await screen.findByTestId("full-size-check-open"));
    await screen.findByTestId("full-size-check-image");
    expect(screen.queryByTestId("full-size-check-where")).not.toBeInTheDocument();
  });

  it("says so plainly when the window cannot be rendered", async () => {
    vi.spyOn(client.api, "loupeInfo").mockResolvedValue(AVAILABLE);
    vi.spyOn(client.api, "fetchLoupe").mockRejectedValue(new Error("Cropped away"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <FullSizeCheck safe="M_42" runId={7} recipe={RECIPE} />
        </QueryClientProvider>
      </MantineProvider>,
    );
    fireEvent.click(await screen.findByTestId("full-size-check-open"));
    expect(await screen.findByTestId("full-size-check-error"))
      .toHaveTextContent("Cropped away");
  });

  it("moves the window when the navigator is tapped, and marks where it is", async () => {
    wrap();
    fireEvent.click(await screen.findByTestId("full-size-check-open"));
    const nav = await screen.findByTestId("full-size-check-navigator");
    vi.spyOn(nav, "getBoundingClientRect").mockReturnValue(
      { left: 0, top: 0, width: 200, height: 100 } as DOMRect);

    fireEvent.click(nav, { clientX: 50, clientY: 75 });

    await waitFor(() => expect(loupeCalls[loupeCalls.length - 1]).toContain("fx=0.2500&fy=0.7500"));
    // …and the marker follows, at the window's true share of the picture
    // (512 of 6000 px wide).
    const marker = screen.getByTestId("full-size-check-marker");
    expect(marker.style.width).toMatch(/^8\.53/);
    expect(marker.style.left).toMatch(/^20\.7/);
  });

  it("draws the marker where the server says the window is, not where it guessed", async () => {
    // The guide re-derives the rectangle from the click and clamps it inside the
    // preview; the server reports the window it actually cut, mapped back through
    // the recipe's crop. With a crop those disagree, and the server is right.
    vi.spyOn(client.api, "loupeInfo").mockResolvedValue(AVAILABLE);
    mockLoupe({ ...CENTRED, preview_x: 0.6, preview_y: 0.1,
                preview_width: 0.25, preview_height: 0.25 });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <FullSizeCheck safe="M_42" runId={7} recipe={RECIPE}
            shownSourceW={6000} shownSourceH={4000} />
        </QueryClientProvider>
      </MantineProvider>,
    );
    fireEvent.click(await screen.findByTestId("full-size-check-open"));
    await screen.findByTestId("full-size-check-image");

    const marker = screen.getByTestId("full-size-check-marker");
    // 60 % across, a quarter wide — not the guide's 8.53 % of a 6000 px canvas.
    expect(marker.style.left).toMatch(/^60/);
    expect(marker.style.width).toMatch(/^25/);
  });

  it("keeps the client-side guide when the server sends no rectangle", async () => {
    // Both halves of the fallback matter: the marker must not vanish while the
    // render is in flight, nor on a container too old to send the fractions.
    vi.spyOn(client.api, "loupeInfo").mockResolvedValue(AVAILABLE);
    mockLoupe(CENTRED);   // no preview_* keys
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <FullSizeCheck safe="M_42" runId={7} recipe={RECIPE}
            shownSourceW={6000} shownSourceH={4000} />
        </QueryClientProvider>
      </MantineProvider>,
    );
    fireEvent.click(await screen.findByTestId("full-size-check-open"));
    await screen.findByTestId("full-size-check-image");
    expect(screen.getByTestId("full-size-check-marker").style.width)
      .toMatch(/^8\.53/);
  });
});

describe("FullSizeCheck — compare with the preview", () => {
  /** The same window, with the server's preview fractions: a quarter of the
   *  preview's width and height, six tenths across and one tenth down. */
  const WITH_FRACTIONS: LoupeWindow = {
    ...CENTRED,
    preview_x: 0.6, preview_y: 0.1, preview_width: 0.25, preview_height: 0.25,
  };

  function open(window_: LoupeWindow | null) {
    vi.spyOn(client.api, "loupeInfo").mockResolvedValue(AVAILABLE);
    mockLoupe(window_);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <FullSizeCheck safe="M_42" runId={7} recipe={RECIPE}
            shownSourceW={6000} shownSourceH={4000} />
        </QueryClientProvider>
      </MantineProvider>,
    );
    return screen.findByTestId("full-size-check-open");
  }

  it("starts off, so the window is just the window", async () => {
    fireEvent.click(await open(WITH_FRACTIONS));
    await screen.findByTestId("full-size-check-image");
    expect(screen.getByTestId("full-size-check-split-toggle")).toHaveTextContent(
      "Compare with the preview");
    expect(screen.queryByTestId("full-size-check-split-before")).not.toBeInTheDocument();
    expect(screen.queryByTestId("full-size-check-split-divider")).not.toBeInTheDocument();
  });

  it("puts the preview of the same patch under a divider, blown up to match", async () => {
    fireEvent.click(await open(WITH_FRACTIONS));
    await screen.findByTestId("full-size-check-image");
    fireEvent.click(screen.getByTestId("full-size-check-split-toggle"));

    const before = screen.getByTestId("full-size-check-split-before");
    // The left half is clipped at the divider, which starts centred.
    expect(before.style.clipPath).toBe("inset(0 50% 0 0)");
    expect(screen.getByTestId("full-size-check-split-divider").style.left).toBe("50%");
    // The preview inside it is blown up 4× (the window is a quarter of it) and
    // slid back by the window's own offset, so both halves show one patch.
    const img = before.querySelector("img") as HTMLImageElement;
    expect(img.src).toContain("/editor/preview");
    expect(img.style.width).toBe(`${512 / 0.25}px`);
    expect(img.style.left).toBe(`${-0.6 * 512 / 0.25}px`);
    expect(img.style.top).toBe(`${-0.1 * 512 / 0.25}px`);
  });

  it("says which half is which, and why the left one looks soft", async () => {
    // The whole finding *is* the softness — a caption that didn't say so would
    // read as a rendering defect in the thing the modal exists to be trusted for.
    fireEvent.click(await open(WITH_FRACTIONS));
    await screen.findByTestId("full-size-check-image");
    fireEvent.click(screen.getByTestId("full-size-check-split-toggle"));
    const caption = screen.getByTestId("full-size-check-split-caption");
    expect(caption).toHaveTextContent(/Left of the line is the preview/);
    expect(caption).toHaveTextContent(/looks soft because that is exactly what the shrunk preview was hiding/);
  });

  it("drags the divider across the window", async () => {
    fireEvent.click(await open(WITH_FRACTIONS));
    await screen.findByTestId("full-size-check-image");
    fireEvent.click(screen.getByTestId("full-size-check-split-toggle"));

    const box = screen.getByTestId("full-size-check-window");
    vi.spyOn(box, "getBoundingClientRect").mockReturnValue(
      { left: 100, top: 0, width: 512, height: 512 } as DOMRect);
    // jsdom implements no `PointerEvent`, so `fireEvent.pointerDown` silently
    // drops `clientX` — a drag test written with it passes while measuring
    // nothing. A `MouseEvent` of the same type carries the coordinate and still
    // reaches React's pointer handler, which is all this reads.
    fireEvent(box, new MouseEvent("pointerdown", {
      bubbles: true, cancelable: true, clientX: 100 + 512 * 0.75 }));

    expect(screen.getByTestId("full-size-check-split-divider").style.left).toBe("75%");
    expect(screen.getByTestId("full-size-check-split-before").style.clipPath)
      .toBe("inset(0 25% 0 0)");
  });

  it("can be turned back off", async () => {
    fireEvent.click(await open(WITH_FRACTIONS));
    await screen.findByTestId("full-size-check-image");
    fireEvent.click(screen.getByTestId("full-size-check-split-toggle"));
    expect(screen.getByTestId("full-size-check-split-toggle")).toHaveTextContent(
      "Hide the preview comparison");
    fireEvent.click(screen.getByTestId("full-size-check-split-toggle"));
    expect(screen.queryByTestId("full-size-check-split-before")).not.toBeInTheDocument();
  });

  it("offers no comparison at all when the halves could not be aligned", async () => {
    // An older container sends no preview fractions, so there is no honest way to
    // put the two on the same patch — and a misaligned split would be worse than
    // none. The window itself is unaffected.
    fireEvent.click(await open(CENTRED));
    await screen.findByTestId("full-size-check-image");
    expect(screen.queryByTestId("full-size-check-split-toggle")).not.toBeInTheDocument();
  });
});
