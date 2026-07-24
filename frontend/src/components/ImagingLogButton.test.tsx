import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ImagingLogButton } from "./ImagingLogButton";

function renderButton(nStacks: number) {
  return render(
    <MantineProvider>
      <ImagingLogButton nStacks={nStacks} />
    </MantineProvider>,
  );
}

describe("ImagingLogButton", () => {
  it("renders a CSV download link when the library has stacks", () => {
    renderButton(3);
    const link = screen.getByRole("link", { name: /imaging log/i });
    expect(link.getAttribute("href")).toBe("/api/imaging-log.csv");
    expect(link.hasAttribute("download")).toBe(true);
  });

  it("self-hides when there are no stacks yet", () => {
    const { container } = renderButton(0);
    expect(container.querySelector("a")).toBeNull();
  });
});
