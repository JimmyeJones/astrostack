import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import type { StackFraming } from "../../api/client";
import { FramingVerdictNote } from "./FramingVerdictNote";

function renderNote(qc: QueryClient = new QueryClient()) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
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

/** A saved editor recipe, optionally carrying the ops that matter here. */
const recipe = (ops: client.OpInstance[]): client.Recipe => ({ version: 1, ops });

const cropOp = (over: Partial<client.OpInstance> = {}): client.OpInstance => ({
  uid: "c1", id: "geometry.crop", enabled: true,
  params: { x0: 0.2, y0: 0.2, x1: 0.8, y1: 0.8 }, ...over,
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
    vi.spyOn(client.api, "getRecipe").mockResolvedValue(recipe([]));
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

describe("FramingVerdictNote — the offer tells the truth", () => {
  const offCentre = (over: Partial<StackFraming> = {}) => verdict({
    level: "off_centre",
    off_centre: 0.5,
    text: "is all in frame, but sits well off to one side.",
    recentre: { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9, kept: 0.64 },
    ...over,
  });

  it("doesn't offer to re-centre a picture the user already cropped", async () => {
    // The verdict is measured from the *stack*, which can't see the editor's saved
    // crop — so it kept offering to fix what the user fixed an hour ago.
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(offCentre());
    vi.spyOn(client.api, "getRecipe").mockResolvedValue(recipe([cropOp()]));
    renderNote();

    const already = await screen.findByTestId("framing-already-cropped");
    expect(already).toHaveTextContent("already cropped this picture");
    expect(screen.getByRole("link", { name: "open the editor" }))
      .toHaveAttribute("href", "/targets/M_42/edit/7");
    expect(screen.queryByTestId("framing-recentre")).not.toBeInTheDocument();
    // The verdict itself is untouched — it describes what the stack caught.
    expect(screen.getByText(/^Orion Nebula is all in frame/)).toBeInTheDocument();
  });

  it("still offers when the recipe's crop is switched off", async () => {
    // A disabled crop op isn't shrinking anything, so there is nothing to notice.
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(offCentre());
    vi.spyOn(client.api, "getRecipe")
      .mockResolvedValue(recipe([cropOp({ enabled: false })]));
    renderNote();

    expect(await screen.findByTestId("framing-recentre")).toBeInTheDocument();
    expect(screen.queryByTestId("framing-already-cropped")).not.toBeInTheDocument();
  });

  it("keeps offering when the saved recipe can't be read", async () => {
    // Withholding a good offer on a failed request would be the worse error.
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(offCentre());
    vi.spyOn(client.api, "getRecipe").mockRejectedValue(new Error("nope"));
    renderNote(new QueryClient({ defaultOptions: { queries: { retry: false } } }));

    expect(await screen.findByTestId("framing-recentre")).toBeInTheDocument();
  });

  it("never asks for the recipe when there is no offer to make", async () => {
    vi.spyOn(client.api, "stackFraming")
      .mockResolvedValue(offCentre({ recentre: null }));
    const rq = vi.spyOn(client.api, "getRecipe").mockResolvedValue(recipe([]));
    renderNote();

    await screen.findByText("It landed off to one side");
    expect(rq).not.toHaveBeenCalled();
  });

  it("says why not when the picture is too far off-centre to rescue", async () => {
    // The case the app used to go quiet on: no crop, and previously no words —
    // so the worst-framed picture got less help than a mildly off-centre one.
    vi.spyOn(client.api, "stackFraming").mockResolvedValue(offCentre({
      off_centre: 0.8,
      recentre: null,
      recentre_refused: { reason: "too_destructive", kept: 0.19 },
    }));
    renderNote();

    const line = await screen.findByTestId("framing-recentre-refused");
    expect(line).toHaveTextContent(
      "Cropping Orion Nebula back to the middle would leave only about a fifth "
      + "of the picture, so it's better to re-point next session than to crop this one.");
  });

  it("stays quiet about the refusals that need no words", async () => {
    // "Already centred" needs nothing said, and "no room around it" would just be
    // noise next to the verdict — only the destructive case is worth explaining.
    for (const reason of ["centred", "cramped", "unknown_size", "degenerate"]) {
      vi.spyOn(client.api, "stackFraming").mockResolvedValue(offCentre({
        recentre: null, recentre_refused: { reason, kept: null },
      }));
      const { unmount } = renderNote();
      await screen.findByText("It landed off to one side");
      expect(screen.queryByTestId("framing-recentre-refused")).not.toBeInTheDocument();
      unmount();
      vi.restoreAllMocks();
    }
  });
});
