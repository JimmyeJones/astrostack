import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StackView } from "./Stack";
import * as client from "../api/client";

function renderStack() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/targets/M_42/stack"]}>
          <Routes>
            <Route path="/targets/:safe/stack" element={<StackView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("StackView", () => {
  it("renders simple fields from the schema and hides advanced behind a disclosure", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "drizzle_scale", label: "Drizzle scale", type: "float", group: "advanced",
        default: 1.5, min: 1, max: 4, step: 0.1, options: null, help: null, depends_on: "drizzle" },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true, drizzle_scale: 1.5 });

    renderStack();

    await waitFor(() => expect(screen.getByText("Sigma clipping")).toBeInTheDocument());
    // Advanced control's label exists in the DOM (inside the collapsed accordion panel).
    expect(screen.getByText("Advanced options")).toBeInTheDocument();
    expect(screen.getByText("Start stacking")).toBeInTheDocument();
  });
});
