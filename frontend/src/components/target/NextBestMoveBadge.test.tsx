import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NextBestMoveBadge } from "./NextBestMoveBadge";

function renderBadge(props: {
  name?: string;
  nFramesUsed?: number | null;
  integrationS?: number | null;
  nUnsolved?: number | null;
}) {
  return render(
    <MantineProvider>
      <NextBestMoveBadge
        name={props.name ?? "M31"}
        nFramesUsed={props.nFramesUsed ?? null}
        integrationS={props.integrationS ?? null}
        nUnsolved={props.nUnsolved ?? null}
      />
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

  it("renders nothing for a deep, healthy stack", () => {
    renderBadge({ nFramesUsed: 300, integrationS: 5 * 3600 });
    expect(screen.queryByText(/better|Nice work/)).toBeNull();
  });

  it("renders nothing when nothing has been stacked", () => {
    renderBadge({ nFramesUsed: null });
    expect(screen.queryByText(/better|Nice work/)).toBeNull();
  });
});
