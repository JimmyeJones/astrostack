import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PreviewToolGuide } from "./PreviewToolGuide";
import { PREVIEW_TOOLS, visiblePreviewTools } from "./previewTools";

function renderGuide(opts = { isMosaic: false, cropDrag: false }) {
  return render(
    <MantineProvider>
      <PreviewToolGuide tools={visiblePreviewTools(opts)} />
    </MantineProvider>,
  );
}

describe("PreviewToolGuide", () => {
  it("costs one line until it's asked for", () => {
    renderGuide();
    expect(screen.getByText("What do these buttons do? →")).toBeInTheDocument();
    // The standing complaint about this app is that its pages are too tall, and
    // the editor page is the tallest thing a beginner opens. Static text, so it
    // is simply not on the page until asked for.
    expect(screen.queryByText(PREVIEW_TOOLS.mask.hint)).not.toBeInTheDocument();
  });

  it("explains every button in the row, in one tap", () => {
    renderGuide({ isMosaic: true, cropDrag: true });
    fireEvent.click(screen.getByText("What do these buttons do? →"));
    // Not a hand-written list: whatever the row offers is what has to be
    // explained, so a tool added later can't arrive with a phone-invisible
    // tooltip and nothing else.
    for (const t of visiblePreviewTools({ isMosaic: true, cropDrag: true })) {
      expect(screen.getByText(t.label)).toBeVisible();
      expect(screen.getByText(t.hint)).toBeVisible();
    }
  });

  it("never explains a button that isn't on the screen", () => {
    // The coverage heatmap is mosaic-only and the crop handles belong to a
    // selected Crop op — an ordinary single-field stack has neither button, and
    // naming them would send a beginner hunting for controls that don't exist.
    renderGuide();
    fireEvent.click(screen.getByText("What do these buttons do? →"));
    expect(screen.queryByText(PREVIEW_TOOLS.coverage.hint)).not.toBeInTheDocument();
    expect(screen.queryByText(PREVIEW_TOOLS.cropDrag.hint)).not.toBeInTheDocument();
    expect(screen.getByText(PREVIEW_TOOLS.mask.hint)).toBeVisible();
    expect(screen.getByText(PREVIEW_TOOLS.split.hint)).toBeVisible();
  });

  it("closes again, and says so while it's open", () => {
    renderGuide();
    fireEvent.click(screen.getByText("What do these buttons do? →"));
    const toggle = screen.getByTestId("preview-tool-guide-toggle");
    expect(toggle).toHaveTextContent("Hide what these buttons do");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(toggle);
    expect(toggle).toHaveTextContent("What do these buttons do? →");
    expect(screen.queryByText(PREVIEW_TOOLS.mask.hint)).not.toBeInTheDocument();
  });

  it("renders nothing at all when there is no toolbar to explain", () => {
    render(
      <MantineProvider>
        <PreviewToolGuide tools={[]} />
      </MantineProvider>,
    );
    expect(screen.queryByText("What do these buttons do? →")).not.toBeInTheDocument();
  });
});
