import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FrameColumnGuide } from "./FrameColumnGuide";
import { FRAME_COLUMNS } from "./frameColumns";

function renderGuide() {
  return render(
    <MantineProvider>
      <FrameColumnGuide />
    </MantineProvider>,
  );
}

describe("FrameColumnGuide", () => {
  it("costs one line until it's asked for", () => {
    renderGuide();
    expect(screen.getByText("What do these numbers mean? →")).toBeInTheDocument();
    // The standing complaint about this app is that its pages are too tall, so
    // the explanations must take no height until asked for — and, being static
    // text with nothing to refetch, they are simply not on the page until then.
    expect(screen.queryByText(/Full-width-half-maximum/)).not.toBeInTheDocument();
  });

  it("explains every column whose heading is jargon, in one tap", () => {
    renderGuide();
    fireEvent.click(screen.getByText("What do these numbers mean? →"));
    // Not a hand-written list: whatever the table's own columns say they need
    // explaining is what has to appear, so a column added later can't quietly
    // arrive with a phone-invisible tooltip and nothing else.
    const explained = FRAME_COLUMNS.filter((c) => c.hint);
    expect(explained.length).toBeGreaterThanOrEqual(4);
    for (const c of explained) {
      expect(screen.getByText(c.label)).toBeVisible();
      expect(screen.getByText(c.hint as string)).toBeVisible();
    }
    // The one column that explains itself doesn't get a redundant entry.
    expect(screen.queryByText("Time (UTC)")).not.toBeInTheDocument();
  });

  it("uses the tooltips' own words, so the two can't drift apart", () => {
    renderGuide();
    fireEvent.click(screen.getByText("What do these numbers mean? →"));
    const fwhm = FRAME_COLUMNS.find((c) => c.key === "fwhm_px");
    expect(fwhm?.hint).toContain("Full-width-half-maximum");
    expect(screen.getByText(fwhm?.hint as string)).toBeInTheDocument();
  });

  it("closes again, and says so while it's open", () => {
    renderGuide();
    fireEvent.click(screen.getByText("What do these numbers mean? →"));
    const toggle = screen.getByTestId("frame-column-guide-toggle");
    expect(toggle).toHaveTextContent("Hide what these numbers mean");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(toggle);
    expect(toggle).toHaveTextContent("What do these numbers mean? →");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Full-width-half-maximum/)).not.toBeInTheDocument();
  });

  it("hugs its own text rather than stretching across the column", () => {
    // Same trap as DarksGuide: a `component="button"` anchor is a real <button>,
    // and a Stack stretches its children, which would centre its text.
    renderGuide();
    expect(screen.getByTestId("frame-column-guide-toggle"))
      .toHaveStyle({ alignSelf: "flex-start" });
  });
});
