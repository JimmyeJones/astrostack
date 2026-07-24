import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CleanupSuggestionsCard } from "./CleanupSuggestionsCard";
import type { CleanupSuggestion } from "../api/client";
import * as client from "../api/client";

function suggestion(over: Partial<CleanupSuggestion> = {}): CleanupSuggestion {
  return {
    safe: "m_31",
    name: "M 31",
    n_frames: 1,
    reason: "on_device_output",
    detail: "Looks like the Seestar's own single stacked image.",
    ...over,
  };
}

function renderCard() {
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={new QueryClient()}>
        <CleanupSuggestionsCard />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("CleanupSuggestionsCard", () => {
  it("lists junk targets and bulk-removes them after one confirmation", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([
      suggestion(),
      suggestion({ safe: "lunar_video", name: "Lunar_video", reason: "video" }),
    ]);
    const del = vi.spyOn(client.api, "deleteTarget").mockResolvedValue({} as never);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderCard();

    await waitFor(() =>
      expect(
        screen.getByText(/look like Seestar outputs or videos/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/M 31 · on-device output/)).toBeInTheDocument();
    expect(screen.getByText(/Lunar_video · video/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Remove these 2 targets"));
    expect(confirm).toHaveBeenCalled();
    await waitFor(() => expect(del).toHaveBeenCalledTimes(2));
    expect(del).toHaveBeenCalledWith("m_31", false);
    expect(del).toHaveBeenCalledWith("lunar_video", false);
  });

  it("does not delete anything when the confirmation is declined", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([suggestion()]);
    const del = vi.spyOn(client.api, "deleteTarget").mockResolvedValue({} as never);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderCard();

    await waitFor(() =>
      expect(screen.getByText("Remove this target")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Remove this target"));
    expect(del).not.toHaveBeenCalled();
  });

  it("self-hides when there is nothing to clean up", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([]);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.cleanupSuggestions).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Alert-root")).toBeNull();
  });

  it("stays dismissed after the user keeps them (persisted)", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([suggestion()]);
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Keep them")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Keep them"));
    await waitFor(() =>
      expect(screen.queryByText("Keep them")).not.toBeInTheDocument(),
    );
    expect(localStorage.getItem("astrostack.cleanupSuggestions.dismissed")).toBe("1");
  });
});
