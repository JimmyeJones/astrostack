import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PresetMenu } from "./PresetMenu";
import * as client from "../../api/client";
import type { OpInstance } from "../../api/client";

function wrap(currentOps: OpInstance[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <PresetMenu currentOps={currentOps} onApply={() => {}} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

const OPS: OpInstance[] = [
  { uid: "a", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
];

afterEach(() => vi.restoreAllMocks());

describe("PresetMenu default recipe", () => {
  it("saves the current ops as the user's default via 'Set current as my default'", async () => {
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getDefaultRecipe").mockResolvedValue({ ops: [], count: 0 });
    const put = vi.spyOn(client.api, "putDefaultRecipe")
      .mockResolvedValue({ ops: OPS.map((o) => ({ ...o })), count: 1 });

    wrap(OPS);
    fireEvent.click(await screen.findByRole("button", { name: /Presets/ }));
    fireEvent.click(await screen.findByText("Set current as my default"));

    await waitFor(() => expect(put).toHaveBeenCalledWith(OPS));
  });

  it("offers 'Clear my default edit' only once a default exists", async () => {
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getDefaultRecipe").mockResolvedValue({ ops: OPS, count: 1 });
    const del = vi.spyOn(client.api, "deleteDefaultRecipe")
      .mockResolvedValue({ ops: [], count: 0 });

    wrap(OPS);
    fireEvent.click(await screen.findByRole("button", { name: /Presets/ }));
    fireEvent.click(await screen.findByText("Clear my default edit"));

    await waitFor(() => expect(del).toHaveBeenCalled());
  });

  it("hides 'Clear my default edit' when no default is set", async () => {
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getDefaultRecipe").mockResolvedValue({ ops: [], count: 0 });

    wrap(OPS);
    fireEvent.click(await screen.findByRole("button", { name: /Presets/ }));
    // The menu is open (Set is present) but Clear is not offered.
    await screen.findByText("Set current as my default");
    expect(screen.queryByText("Clear my default edit")).toBeNull();
  });
});

describe("PresetMenu deleting a saved preset", () => {
  const MINE = { id: "u1", label: "My nebula look", ops: [] } as unknown as client.Preset;

  async function clickTrash() {
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [MINE] });
    vi.spyOn(client.api, "getDefaultRecipe").mockResolvedValue({ ops: [], count: 0 });
    wrap(OPS);
    fireEvent.click(await screen.findByRole("button", { name: /Presets/ }));
    fireEvent.click(await screen.findByLabelText("Delete preset My nebula look"));
  }

  it("asks first, and keeps the preset when the answer is no", async () => {
    const del = vi.spyOn(client.api, "deletePreset").mockResolvedValue({ deleted: "u1" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await clickTrash();
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("My nebula look"));
    // Give a would-be mutation a tick to fire before asserting it did not.
    await new Promise((r) => setTimeout(r, 0));
    expect(del).not.toHaveBeenCalled();
  });

  it("deletes it once confirmed", async () => {
    const del = vi.spyOn(client.api, "deletePreset").mockResolvedValue({ deleted: "u1" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await clickTrash();
    await waitFor(() => expect(del).toHaveBeenCalledWith("u1"));
  });
});

describe("PresetMenu save dialog", () => {
  it("saves on Enter in the name field", async () => {
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getDefaultRecipe").mockResolvedValue({ ops: [], count: 0 });
    const create = vi.spyOn(client.api, "createPreset")
      .mockResolvedValue({ id: "u2", label: "Mine", ops: [] } as unknown as client.Preset);
    wrap(OPS);
    fireEvent.click(await screen.findByRole("button", { name: /Presets/ }));
    fireEvent.click(await screen.findByText("Save current as preset…"));
    const field = await screen.findByLabelText("Preset name");
    fireEvent.change(field, { target: { value: "Mine" } });
    fireEvent.keyDown(field, { key: "Enter" });
    await waitFor(() => expect(create).toHaveBeenCalledWith("Mine", OPS));
  });
});
