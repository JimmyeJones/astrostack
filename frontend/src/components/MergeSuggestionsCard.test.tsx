import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MergeSuggestionsCard } from "./MergeSuggestionsCard";
import type { MergeSuggestion } from "../api/client";
import * as client from "../api/client";

function suggestion(over: Partial<MergeSuggestion> = {}): MergeSuggestion {
  return {
    object_name: "Andromeda Galaxy",
    center_ra_deg: 10.685,
    center_dec_deg: 41.269,
    max_sep_arcmin: 1.2,
    targets: [
      { safe: "m31_n2", name: "M31 night 2", n_frames_accepted: 200, total_exposure_s: 2000 },
      { safe: "m31_n1", name: "M31 night 1", n_frames_accepted: 100, total_exposure_s: 1000 },
    ],
    ...over,
  };
}

function renderCard() {
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={new QueryClient()}>
        <MergeSuggestionsCard />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("MergeSuggestionsCard", () => {
  it("shows a same-object suggestion and merges into the deepest folder", async () => {
    vi.spyOn(client.api, "mergeSuggestions").mockResolvedValue([suggestion()]);
    const merge = vi.spyOn(client.api, "mergeTargets").mockResolvedValue({} as never);
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/These 2 targets look like the same object/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Andromeda Galaxy/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Combine into one deep target"));
    await waitFor(() => expect(merge).toHaveBeenCalledWith("m31_n2", ["m31_n1"]));
  });

  it("lets a long target name wrap rather than hiding the fact beside it", async () => {
    // Measured at 420 px on a real browser: `"<name> · <N> subs · <duration>"`
    // wanted 299 px and 317 px inside a 288 px badge, so the tail — how many
    // subs, how many hours — was ellipsised away with no scroll and no tooltip
    // to reach it. A badge in a *table* gets `NO_SHRINK`; this one sits in an
    // `Alert` body that does not scroll, so it grows downwards instead.
    vi.spyOn(client.api, "mergeSuggestions").mockResolvedValue([suggestion({
      targets: [
        { safe: "a", name: "Lagoon and Trifid Nebulae mosaic_sub",
          n_frames_accepted: 583, total_exposure_s: 5830 },
        { safe: "b", name: "Lagoon and Trifid Nebulae (mosaic)",
          n_frames_accepted: 120, total_exposure_s: 1200 },
      ],
    })]);
    renderCard();

    const chip = await screen.findByText(/Lagoon and Trifid Nebulae mosaic_sub · 583 subs/);
    const root = chip.closest(".mantine-Badge-root");
    expect(root).toHaveStyle({ height: "auto" });
    expect(chip).toHaveStyle({ whiteSpace: "normal", overflow: "visible" });
  });

  it("says the pictures came too — the fine print promises nothing is deleted", async () => {
    vi.spyOn(client.api, "mergeSuggestions").mockResolvedValue([suggestion()]);
    vi.spyOn(client.api, "mergeTargets").mockResolvedValue(
      { into: "m31_n2", frames_added: 100, pictures_kept: 2 } as never);
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/keeps every sub/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/every picture you.{1,3}ve already made of it/))
      .toBeInTheDocument();

    fireEvent.click(screen.getByText("Combine into one deep target"));
    await waitFor(() =>
      expect(screen.getByText(/Your 2 existing pictures came with them/))
        .toBeInTheDocument(),
    );
  });

  it("self-hides when there are no suggestions", async () => {
    vi.spyOn(client.api, "mergeSuggestions").mockResolvedValue([]);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.mergeSuggestions).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Alert-root")).toBeNull();
  });

  it("stays dismissed after the user declines (persisted)", async () => {
    vi.spyOn(client.api, "mergeSuggestions").mockResolvedValue([suggestion()]);
    renderCard();
    await waitFor(() =>
      expect(screen.getByText(/These 2 targets/)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Not the same object"));
    await waitFor(() =>
      expect(screen.queryByText(/These 2 targets/)).not.toBeInTheDocument(),
    );
    // The dismissal is keyed by membership signature and persisted.
    expect(localStorage.getItem("astrostack.mergeSuggestions.dismissed"))
      .toContain("m31_n1|m31_n2");
  });
});
