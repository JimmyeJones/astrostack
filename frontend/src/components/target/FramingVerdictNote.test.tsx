import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import type { StackFraming } from "../../api/client";
import { FramingVerdictNote } from "./FramingVerdictNote";

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <FramingVerdictNote safe="M_42" runId={7} />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

const verdict = (over: Partial<StackFraming> = {}): StackFraming => ({
  level: "centred",
  text: "is nicely centred and completely inside the frame — well framed.",
  coverage: 1,
  off_centre: 0.02,
  object_name: "Orion Nebula",
  size_arcmin: 85,
  ...over,
});

afterEach(() => vi.restoreAllMocks());

describe("FramingVerdictNote", () => {
  it("names the object and says how it landed", async () => {
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(verdict());
    renderNote();

    expect(await screen.findByText("Nicely framed")).toBeInTheDocument();
    expect(
      screen.getByText(/^Orion Nebula is nicely centred/),
    ).toBeInTheDocument();
    // The catalogue size it judged against is shown, so the verdict is checkable.
    expect(screen.getByText(/about 85′ across/)).toBeInTheDocument();
  });

  it("tells the user what to do differently when it ran off an edge", async () => {
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(
      verdict({
        level: "clipped",
        coverage: 0.68,
        text: "runs off the edge of the frame — about 70% of it made it in. It "
          + "would fit whole, so just re-centre it next session.",
      }),
    );
    renderNote();

    expect(
      await screen.findByText("Part of it is outside the frame"),
    ).toBeInTheDocument();
    expect(screen.getByText(/re-centre it next session/)).toBeInTheDocument();
  });

  it("offers a one-click re-centring crop when one would help", async () => {
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(
      verdict({
        level: "off_centre",
        off_centre: 0.5,
        text: "is all in frame, but sits well off to one side.",
        recentre: { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9, kept: 0.64 },
      }),
    );
    renderNote();

    const link = await screen.findByTestId("framing-recentre");
    // Straight into the editor with the proposal already up — and it says what
    // the crop costs before the user takes it.
    expect(link).toHaveAttribute("href", "/targets/M_42/edit/7?recentre=1");
    expect(screen.getByText(/keeps 64% of the picture/)).toBeInTheDocument();
  });

  it("offers no crop when the backend didn't propose one", async () => {
    // Off-centre, but re-centring it would cost more than it's worth — and an
    // older backend that has no such field at all reads the same way.
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(
      verdict({ level: "off_centre", off_centre: 0.8, recentre: null }),
    );
    renderNote();

    expect(await screen.findByText("It landed off to one side")).toBeInTheDocument();
    expect(screen.queryByTestId("framing-recentre")).not.toBeInTheDocument();
  });

  it("never offers a crop on a verdict cropping cannot fix", async () => {
    // The endpoint only proposes on `off_centre`; this pins that the note doesn't
    // invent one for a clipped picture (cropping can't un-clip it).
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(
      verdict({ level: "clipped", coverage: 0.68 }),
    );
    renderNote();

    expect(
      await screen.findByText("Part of it is outside the frame"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("framing-recentre")).not.toBeInTheDocument();
  });

  it("says nothing at all when the backend has no honest answer", async () => {
    const call = vi.spyOn(client.api, "stackFraming").mockResolvedValue(null);
    renderNote();

    await waitFor(() => expect(call).toHaveBeenCalledWith("M_42", 7));
    expect(screen.queryByTestId("framing-verdict")).not.toBeInTheDocument();
  });
});
