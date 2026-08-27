import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GrainierDefaultNote } from "./GrainierDefaultNote";
import * as client from "../api/client";
import type { GrainierDefault } from "../api/client";

const HIT: GrainierDefault = {
  run_id: 7,
  newest_run_id: 12,
  noise_sigma: 0.030,
  best_noise_sigma: 0.020,
  percent_grainier: 50,
  n_frames_used: 40,
  best_n_frames_used: 120,
  timestamp_utc: "2026-05-20T02:00:00Z",
  best_timestamp_utc: "2026-05-14T02:00:00Z",
};

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <GrainierDefaultNote safe="m_42" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("GrainierDefaultNote", () => {
  it("names the silent regression in plain language, dated, with its numbers", async () => {
    vi.spyOn(client.api, "grainierDefault").mockResolvedValue(HIT);
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("grainier-default-note")).toBeInTheDocument());
    const text = screen.getByTestId("grainier-default-note").textContent ?? "";
    expect(text).toMatch(/about 50% more background grain than your 14 May one/);
    expect(text).toMatch(/combined 40 subs against 120/);
    // Why it happened, in a beginner's terms — never "you did something wrong".
    expect(text).toMatch(/hazier night left more of them unusable/);
    // And the reassurance: nothing was lost and nothing changed by itself.
    expect(text).toMatch(/Both pictures are safe/);
    expect(text).toMatch(/Nothing is pinned/);
  });

  it("states a very large gap as a multiple, where a percentage would read as a bug", async () => {
    // A manual restack of a handful of subs against a 500-sub master. "about
    // 2400% more grain" is arithmetically right and reads as broken.
    vi.spyOn(client.api, "grainierDefault").mockResolvedValue({
      ...HIT, noise_sigma: 0.2, best_noise_sigma: 0.008, percent_grainier: 2400,
    });
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("grainier-default-note")).toBeInTheDocument());
    const text = screen.getByTestId("grainier-default-note").textContent ?? "";
    expect(text).toMatch(/about 25\.0× as much background grain as your 14 May one/);
    expect(text).not.toMatch(/2400%/);
    // …and the ordinary band still reads as a percentage.
    expect(HIT.percent_grainier).toBeLessThanOrEqual(200);
  });

  it("blames the sky, not the sub count, when the grainier stack isn't thinner", async () => {
    // Same subs, worse sky: the frame counts explain nothing, so don't quote them.
    vi.spyOn(client.api, "grainierDefault").mockResolvedValue({
      ...HIT, n_frames_used: 120, best_n_frames_used: 120,
    });
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("grainier-default-note")).toBeInTheDocument());
    const text = screen.getByTestId("grainier-default-note").textContent ?? "";
    expect(text).toMatch(/the sky was worse that night/);
    expect(text).not.toMatch(/subs against/);
  });

  it("still reads sensibly when the better run's date can't be parsed", async () => {
    vi.spyOn(client.api, "grainierDefault").mockResolvedValue({
      ...HIT, best_timestamp_utc: "",
    });
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("grainier-default-note")).toBeInTheDocument());
    const text = screen.getByTestId("grainier-default-note").textContent ?? "";
    expect(text).toMatch(/more background grain than an earlier one/);
    expect(text).not.toMatch(/your  one/);
  });

  it("pins the better run through the same set-cover path History uses", async () => {
    vi.spyOn(client.api, "grainierDefault").mockResolvedValue(HIT);
    const setCover = vi.spyOn(client.api, "setTargetCover")
      .mockResolvedValue({} as never);
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("grainier-default-note")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Show the cleaner picture/ }));
    // The *better* run, not the newest one it is offering to replace.
    await waitFor(() => expect(setCover).toHaveBeenCalledWith("m_42", 7));
  });

  it("says nothing on an ordinary night", async () => {
    const spy = vi.spyOn(client.api, "grainierDefault").mockResolvedValue(null);
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("grainier-default-note")).toBeNull();
  });

  it("stays silent on an older backend or a failed fetch", async () => {
    const spy = vi.spyOn(client.api, "grainierDefault")
      .mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("grainier-default-note")).toBeNull();
  });
});
