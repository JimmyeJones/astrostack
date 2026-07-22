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
