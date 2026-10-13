import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutoDrizzleNote } from "./AutoDrizzleNote";
import type { AutoDrizzleCost } from "../api/client";
import * as client from "../api/client";

const COST: AutoDrizzleCost = {
  scale: 1.5,
  drizzle_seconds: 14 * 3600,
  plain_seconds: 2 * 3600,
  basis_runs: 3,
  same_engine: true,
};

function renderNote(
  cost: AutoDrizzleCost | null, { onCancel }: { onCancel?: () => void } = {},
) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <AutoDrizzleNote cost={cost} target="M_42" onCancel={onCancel} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("AutoDrizzleNote", () => {
  it("says what the drizzle it chose will cost", () => {
    renderNote(COST);
    expect(screen.getByTestId("auto-drizzle-note")).toBeTruthy();
    expect(screen.getByText(/about 14 h \(a plain stack would take about 2 h\)/))
      .toBeTruthy();
  });

  it("offers the two answers the owner asked for, and no threshold", () => {
    // (c): tell me the estimate and let it run. So: stop this one, or keep this
    // target on plain stacks — never a refusal the app made for him.
    renderNote(COST, { onCancel: () => {} });
    expect(screen.getByRole("button", { name: "Stop this stack" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Don't auto-drizzle this target" }))
      .toBeTruthy();
  });

  it("leaves out the cancel where the surface has its own", () => {
    // The Jobs row already carries a cancel beside the progress bar.
    renderNote(COST);
    expect(screen.queryByRole("button", { name: "Stop this stack" })).toBeNull();
    expect(screen.getByRole("button", { name: "Don't auto-drizzle this target" }))
      .toBeTruthy();
  });

  it("stands the target down through the per-target saved default", async () => {
    const off = vi.spyOn(client.api, "autoDrizzleOff")
      .mockResolvedValue({ drizzle: false, saved: { drizzle: false } });
    renderNote(COST);
    fireEvent.click(
      screen.getByRole("button", { name: "Don't auto-drizzle this target" }));
    await waitFor(() => expect(off).toHaveBeenCalledWith("M_42"));
    // …and it says so rather than inviting a second click.
    await waitFor(() => expect(
      screen.getByRole("button", { name: "Won't auto-drizzle this target" }),
    ).toBeTruthy());
  });

  it("renders nothing on a job that chose no drizzle", () => {
    renderNote(null);
    expect(screen.queryByTestId("auto-drizzle-note")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
