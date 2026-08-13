import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import type { StackFraming } from "../../api/client";
import { FramingVerdictNote } from "./FramingVerdictNote";

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <FramingVerdictNote safe="M_42" runId={7} />
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

  it("says nothing at all when the backend has no honest answer", async () => {
    const call = vi.spyOn(client.api, "stackFraming").mockResolvedValue(null);
    renderNote();

    await waitFor(() => expect(call).toHaveBeenCalledWith("M_42", 7));
    expect(screen.queryByTestId("framing-verdict")).not.toBeInTheDocument();
  });
});
