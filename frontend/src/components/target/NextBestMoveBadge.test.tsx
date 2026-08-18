import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { NextBestMoveBadge } from "./NextBestMoveBadge";

function renderBadge(props: {
  name?: string;
  nFramesUsed?: number | null;
  integrationS?: number | null;
  nUnsolved?: number | null;
  runs?: { stack_fwhm_px?: number | null }[] | null;
}) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <NextBestMoveBadge
          name={props.name ?? "M31"}
          nFramesUsed={props.nFramesUsed ?? null}
          integrationS={props.integrationS ?? null}
          nUnsolved={props.nUnsolved ?? null}
          runs={props.runs ?? null}
        />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("NextBestMoveBadge", () => {
  it("shows the plate-solve tip, naming the target", () => {
    renderBadge({ nFramesUsed: 30, nUnsolved: 30, integrationS: 5 * 3600 });
    expect(screen.getByText(/To make your M31 even better/)).toBeInTheDocument();
    expect(screen.getByText(/couldn't be plate-solved/)).toBeInTheDocument();
  });

  it("shows the encouraging note with a 'nice work' heading for a good result", () => {
    renderBadge({ nFramesUsed: 120, integrationS: 2 * 3600 });
    expect(screen.getByText(/Nice work on M31/)).toBeInTheDocument();
    expect(screen.getByText(/solid result/i)).toBeInTheDocument();
  });

  it("shows the refocus tip when this target's stars came out softer than usual", () => {
    // Healthy count + soft stars vs the target's own history (median ~3.0 px,
    // newest 4.5 px) → the soft rung fires with a refocus nudge.
    renderBadge({
      nFramesUsed: 40,
      integrationS: 2 * 3600,
      runs: [{ stack_fwhm_px: 4.5 }, { stack_fwhm_px: 3.0 }, { stack_fwhm_px: 3.0 }],
    });
    expect(screen.getByText(/To make your M31 even better/)).toBeInTheDocument();
    expect(screen.getByText(/refocus/i)).toBeInTheDocument();
  });

  it("does not show a refocus tip when the stars are in the normal band", () => {
    renderBadge({
      nFramesUsed: 40,
      integrationS: 2 * 3600,
      runs: [{ stack_fwhm_px: 3.1 }, { stack_fwhm_px: 3.0 }, { stack_fwhm_px: 3.0 }],
    });
    expect(screen.queryByText(/refocus/i)).toBeNull();
    // Falls through to the good/encouraging note instead.
    expect(screen.getByText(/Nice work on M31/)).toBeInTheDocument();
  });

  it("renders nothing for a deep, healthy stack", () => {
    renderBadge({ nFramesUsed: 300, integrationS: 5 * 3600 });
    expect(screen.queryByText(/better|Nice work/)).toBeNull();
  });

  it("renders nothing when nothing has been stacked", () => {
    renderBadge({ nFramesUsed: null });
    expect(screen.queryByText(/better|Nice work/)).toBeNull();
  });

  it("makes \"in Settings\" a link to the section that holds the star database", () => {
    renderBadge({ nFramesUsed: 30, nUnsolved: 30, integrationS: 5 * 3600 });
    expect(screen.getByRole("link", { name: /star database in Settings/ }))
      .toHaveAttribute("href", "/settings/plate-solving");
  });

  it("adds no link to a tip that doesn't send you anywhere", () => {
    renderBadge({ nFramesUsed: 3, nUnsolved: 0, integrationS: 120 });
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
