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
      suggestion({
        safe: "scenery_photo",
        name: "Scenery_photo",
        n_frames: 40,
        reason: "photo",
      }),
    ]);
    const del = vi.spyOn(client.api, "deleteTarget").mockResolvedValue({} as never);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderCard();

    await waitFor(() =>
      expect(
        screen.getByText(/look like Seestar outputs, videos or photos/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/M 31 · on-device output/)).toBeInTheDocument();
    expect(screen.getByText(/Lunar_video · video/)).toBeInTheDocument();
    // A "_photo" capture folder belongs in the same group, labelled as itself
    // rather than borrowing the "video" wording.
    expect(screen.getByText(/Scenery_photo · photo/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Remove these 3 targets"));
    expect(confirm).toHaveBeenCalled();
    await waitFor(() => expect(del).toHaveBeenCalledTimes(3));
    expect(del).toHaveBeenCalledWith("m_31", false);
    expect(del).toHaveBeenCalledWith("lunar_video", false);
    expect(del).toHaveBeenCalledWith("scenery_photo", false);
  });

  it("puts another program's temp folder in the same not-raw-subs group", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([
      suggestion({
        safe: "batch_stack_tmp",
        name: "batch_stack_tmp",
        n_frames: 30,
        reason: "temp_folder",
        detail: "a working folder another stacking program leaves behind",
      }),
    ]);
    const del = vi.spyOn(client.api, "deleteTarget").mockResolvedValue({} as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderCard();

    await waitFor(() =>
      expect(
        screen.getByText(/look like Seestar outputs, videos or photos/i),
      ).toBeInTheDocument(),
    );
    // Labelled as itself, not borrowed from the on-device-output wording.
    expect(screen.getByText(/batch_stack_tmp · temp folder/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Remove this target"));
    await waitFor(() => expect(del).toHaveBeenCalledWith("batch_stack_tmp", false));
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

  it("shows the duplicate group in its own alert with distinct copy", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([
      suggestion({ safe: "m_31", name: "M 31", reason: "on_device_output" }),
      suggestion({
        safe: "m_31_sub",
        name: "M 31_sub",
        n_frames: 6,
        reason: "duplicate_sub",
        detail: "already in your “M 31” target",
      }),
    ]);
    renderCard();

    // Both groups render as separate alerts.
    await waitFor(() =>
      expect(screen.getByText(/are duplicates left by an older scan/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/look like Seestar outputs, videos or photos/i)).toBeInTheDocument();
    const chip = screen.getByText(/M 31_sub · duplicate/);
    expect(chip).toBeInTheDocument();
    // The chip grows downwards rather than ellipsising its own reason away: a
    // long folder name plus " · duplicate" is wider than this Alert's body on a
    // phone, and an Alert does not scroll (`badgeFit.WRAPPING_BADGE`).
    expect(chip.closest(".mantine-Badge-root")).toHaveStyle({ height: "auto" });
    expect(chip).toHaveStyle({ whiteSpace: "normal" });
  });

  it("removes only the duplicate group when its own Remove is clicked", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([
      suggestion({
        safe: "m_31_sub",
        name: "M 31_sub",
        n_frames: 6,
        reason: "duplicate_sub",
      }),
    ]);
    const del = vi.spyOn(client.api, "deleteTarget").mockResolvedValue({} as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/are duplicates left by an older scan/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Remove this target"));
    await waitFor(() => expect(del).toHaveBeenCalledWith("m_31_sub", false));
  });

  it("dismisses the two groups independently", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([
      suggestion({ safe: "m_31", name: "M 31", reason: "on_device_output" }),
      suggestion({ safe: "m_31_sub", name: "M 31_sub", reason: "duplicate_sub" }),
    ]);
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/are duplicates left by an older scan/i)).toBeInTheDocument(),
    );
    // Dismiss only the junk group via its "Keep them" button (first one).
    fireEvent.click(screen.getAllByText("Keep them")[0]);
    await waitFor(() =>
      expect(screen.queryByText(/look like Seestar outputs or videos/i)).not.toBeInTheDocument(),
    );
    // The duplicate group is still shown.
    expect(screen.getByText(/are duplicates left by an older scan/i)).toBeInTheDocument();
  });

  it("shows a legacy mixed-drop target in its own third group", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([
      suggestion({
        safe: "myworks",
        name: "MyWorks",
        n_frames: 42,
        reason: "legacy_mixed_drop",
        detail: "lumped a whole Seestar card into one target",
      }),
    ]);
    const del = vi.spyOn(client.api, "deleteTarget").mockResolvedValue({} as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderCard();

    await waitFor(() =>
      expect(
        screen.getByText(/whole Seestar card dropped in at once/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/MyWorks · mixed drop/)).toBeInTheDocument();
    // It is not lumped in with the outputs/videos group.
    expect(
      screen.queryByText(/look like Seestar outputs or videos/i),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Remove this target"));
    await waitFor(() => expect(del).toHaveBeenCalledWith("myworks", false));
  });

  it("offers the combine — not a remove — for a duplicate that holds pictures", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([
      suggestion({
        safe: "m_44_mosaic_sub",
        name: "M 44_mosaic_sub",
        n_frames: 812,
        reason: "duplicate_sub_merge",
        detail: "also holds pictures you have already stacked from it",
        merge_into_safe: "m_44_mosaic-328c48ae",
        merge_into_name: "M 44 (mosaic)",
      }),
    ]);
    const merge = vi.spyOn(client.api, "mergeTargets").mockResolvedValue({} as never);
    const del = vi.spyOn(client.api, "deleteTarget").mockResolvedValue({} as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderCard();

    await waitFor(() =>
      expect(
        screen.getByText(/also hold pictures you've already made/i),
      ).toBeInTheDocument(),
    );
    // The chip names where it is going, not just what it is.
    expect(
      screen.getByText("M 44_mosaic_sub → M 44 (mosaic)"),
    ).toBeInTheDocument();
    // It is not lumped in with the removable duplicates.
    expect(
      screen.queryByText(/are duplicates left by an older scan/i),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Combine it into the main target"));
    await waitFor(() =>
      expect(merge).toHaveBeenCalledWith("m_44_mosaic-328c48ae", [
        "m_44_mosaic_sub",
      ]),
    );
    // The one thing this group must never do: delete the target that holds the
    // only copy of those pictures.
    expect(del).not.toHaveBeenCalled();
  });

  it("does not offer a combine without a destination", async () => {
    vi.spyOn(client.api, "cleanupSuggestions").mockResolvedValue([
      suggestion({
        safe: "m_44_mosaic_sub",
        name: "M 44_mosaic_sub",
        reason: "duplicate_sub_merge",
        merge_into_safe: null,
        merge_into_name: null,
      }),
    ]);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.cleanupSuggestions).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Alert-root")).toBeNull();
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
