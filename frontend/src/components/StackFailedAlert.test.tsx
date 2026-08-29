import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { StackFailure } from "../api/client";
import { StackFailedAlert } from "./StackFailedAlert";
import { StackFailuresNote } from "./dashboard/StackFailuresNote";
import { StackFailedNote } from "./target/StackFailedNote";

const MEMORY_MSG =
  "stack output canvas 8000x6000 ×1.5 drizzle needs ~9.4 GB of working memory, "
  + "over the ~6.0 GB budget. To fit, switch Canvas mode to 'reference' (~5.1 GB), "
  + "or raise ASTROSTACK_MAX_STACK_GB to override.";

const FAILURE: StackFailure = {
  safe: "M_31", name: "M 31", message: MEMORY_MSG, kind: "memory_budget",
  when_utc: "2026-08-29T02:00:00Z", unattended: true,
};

function renderIn(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>{node}</MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

describe("StackFailedAlert", () => {
  it("keeps the engine's own numbers, not just the friendly summary", () => {
    // The translation says *what* happened; only the raw line says how far off
    // you are, which is what makes the fix actionable.
    renderIn(<StackFailedAlert failure={FAILURE} />);
    expect(screen.getByText(/9\.4 GB of working memory/)).toBeTruthy();
    expect(screen.getByText(/needs more memory than the budget allows/)).toBeTruthy();
  });

  it("links to the setting instead of offering to change it", () => {
    // Every lever here changes the picture, which is exactly why the engine
    // declined to take it silently.
    renderIn(<StackFailedAlert failure={FAILURE} />);
    const link = screen.getByRole("link", { name: /Settings → Stacking/ });
    expect(link.getAttribute("href")).toContain("/settings/stacking");
    expect(screen.queryByRole("button", { name: /fix|apply/i })).toBeNull();
  });

  it("says when nobody was watching", () => {
    renderIn(<StackFailedAlert failure={FAILURE} />);
    expect(screen.getByText(/tried to stack on its own and stopped/)).toBeTruthy();
  });

  it("words a manual failure differently", () => {
    renderIn(<StackFailedAlert failure={{ ...FAILURE, unattended: false }} />);
    expect(screen.getByText(/last stack stopped before it ran/)).toBeTruthy();
  });

  it("shows an unrecognised message verbatim rather than hiding it", () => {
    renderIn(<StackFailedAlert failure={{
      ...FAILURE, kind: null, message: "gremlins in the mount",
    }} />);
    expect(screen.getAllByText(/gremlins in the mount/).length).toBeGreaterThan(0);
  });

  it("names the target on the library-wide mount", () => {
    renderIn(<StackFailedAlert failure={FAILURE} showTargetName />);
    expect(screen.getByText(/M 31 didn't stack/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open M 31/ }).getAttribute("href"))
      .toBe("/targets/M_31");
  });
});

describe("StackFailuresNote (Dashboard)", () => {
  it("says nothing on a healthy install", async () => {
    const spy = vi.spyOn(client.api, "getStackFailures")
      .mockResolvedValue({ failures: [] });
    const { container } = renderIn(<StackFailuresNote />);
    // Wait for the fetch to actually have resolved, so "nothing rendered" is a
    // real result rather than the component simply not having loaded yet.
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(container.querySelector("[data-testid='stack-failures-note']")).toBeNull();
  });

  it("names the first two and summarises the rest", async () => {
    vi.spyOn(client.api, "getStackFailures").mockResolvedValue({
      failures: [
        FAILURE,
        { ...FAILURE, safe: "M_42", name: "M 42" },
        { ...FAILURE, safe: "M_13", name: "M 13" },
        { ...FAILURE, safe: "M_57", name: "M 57" },
      ],
    });
    renderIn(<StackFailuresNote />);
    expect(await screen.findByText(/M 31 didn't stack/)).toBeTruthy();
    expect(screen.getByText(/M 42 didn't stack/)).toBeTruthy();
    expect(screen.queryByText(/M 13 didn't stack/)).toBeNull();
    // The rest are *named*, not counted — "2 more targets" would leave the
    // reader hunting through a library for which two.
    expect(screen.getByRole("link", { name: "M 13" }).getAttribute("href"))
      .toBe("/targets/M_13");
    expect(screen.getByRole("link", { name: "M 57" })).toBeTruthy();
    expect(screen.getByText(/didn't stack either/)).toBeTruthy();
  });
});

describe("StackFailedNote (Target page)", () => {
  it("shows only this target's failure", async () => {
    vi.spyOn(client.api, "getStackFailures").mockResolvedValue({
      failures: [FAILURE, { ...FAILURE, safe: "M_42", name: "M 42" }],
    });
    renderIn(<StackFailedNote safe="M_42" />);
    expect(await screen.findByTestId("stack-failed-note")).toBeTruthy();
    // The per-target mount doesn't repeat the target's own name at it.
    expect(screen.getByText(/Your last stack didn't run/)).toBeTruthy();
  });

  it("stays silent for a target that is fine", async () => {
    const spy = vi.spyOn(client.api, "getStackFailures")
      .mockResolvedValue({ failures: [FAILURE] });
    const { container } = renderIn(<StackFailedNote safe="NGC_7000" />);
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(container.querySelector("[data-testid='stack-failed-note']")).toBeNull();
  });
});
