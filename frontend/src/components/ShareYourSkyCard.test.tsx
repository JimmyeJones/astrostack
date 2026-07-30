import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShareYourSkyCard } from "./ShareYourSkyCard";
import * as client from "../api/client";
import type { LibraryRecap } from "../api/client";

function recap(over: Partial<LibraryRecap> = {}): LibraryRecap {
  return {
    has_anything: true,
    caption: "12 nights under the sky · 8h 20m of light · 4 targets",
    since: "Since 14 Jan 2026",
    stats: [{ value: "8h 20m", label: "of light collected" }],
    window_months: 12,
    n_nights: 12, n_targets: 4, n_subs_kept: 1234, total_integration_s: 30000,
    top_target_name: "M 31", top_target_integration_s: 15120,
    ...over,
  };
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}><ShareYourSkyCard /></QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("ShareYourSkyCard", () => {
  it("offers the poster download and the caption", async () => {
    vi.spyOn(client.api, "getLibraryRecap").mockResolvedValue(recap());
    renderCard();
    const link = await screen.findByRole("link", { name: /Download poster/ });
    expect(link).toHaveAttribute("href", "/api/recap.jpg");
    expect(link).toHaveAttribute("download");
    expect(screen.getByText(
      "12 nights under the sky · 8h 20m of light · 4 targets",
    )).toBeInTheDocument();
    expect(screen.getByText("Since 14 Jan 2026")).toBeInTheDocument();
  });

  it("copies the caption to the clipboard", async () => {
    vi.spyOn(client.api, "getLibraryRecap").mockResolvedValue(recap());
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: /Copy caption/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      "12 nights under the sky · 8h 20m of light · 4 targets"));
  });

  it("shows the caption to copy by hand when the clipboard is blocked", async () => {
    vi.spyOn(client.api, "getLibraryRecap").mockResolvedValue(recap());
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: /Copy caption/ }));
    expect(await screen.findByText("Copy this caption")).toBeInTheDocument();
  });

  it("hides on a library that hasn't collected any light yet", async () => {
    vi.spyOn(client.api, "getLibraryRecap").mockResolvedValue(recap({
      has_anything: false, caption: "", since: "", stats: [],
      n_nights: 0, n_targets: 0, n_subs_kept: 0, total_integration_s: 0,
      top_target_name: null, top_target_integration_s: null,
    }));
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getLibraryRecap).toHaveBeenCalled());
    expect(container.querySelector("a")).toBeNull();
  });

  it("hides rather than erroring when the recap can't be fetched", async () => {
    vi.spyOn(client.api, "getLibraryRecap").mockRejectedValue(new Error("boom"));
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getLibraryRecap).toHaveBeenCalled());
    expect(screen.queryByText("Share your sky")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
  });

  it("still offers the poster when there is no caption to copy", async () => {
    vi.spyOn(client.api, "getLibraryRecap").mockResolvedValue(
      recap({ caption: "", since: "" }));
    renderCard();
    expect(await screen.findByRole("link", { name: /Download poster/ }))
      .toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copy caption/ })).toBeNull();
  });
});
