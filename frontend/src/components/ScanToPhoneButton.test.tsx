import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScanToPhoneButton } from "./ScanToPhoneButton";

function renderButton(props: Partial<React.ComponentProps<typeof ScanToPhoneButton>> = {}) {
  return render(
    <MantineProvider>
      <ScanToPhoneButton url="/api/targets/M_42/stack-runs/5/jpeg" {...props} />
    </MantineProvider>,
  );
}

describe("ScanToPhoneButton", () => {
  it("renders the trigger button without generating a QR up front", () => {
    renderButton();
    expect(
      screen.getByRole("button", { name: "Scan to get this picture on your phone" }),
    ).toBeInTheDocument();
    // The QR image only exists once the popover opens.
    expect(screen.queryByRole("img", { name: /QR code/i })).not.toBeInTheDocument();
  });

  it("shows a QR code when opened", async () => {
    renderButton();
    fireEvent.click(
      screen.getByRole("button", { name: "Scan to get this picture on your phone" }),
    );
    const svg = await screen.findByRole("img", { name: /QR code/i });
    expect(svg).toBeInTheDocument();
    // The QR is drawn as a filled path (the dark modules).
    const path = svg.querySelector("path");
    expect(path).not.toBeNull();
    expect(path?.getAttribute("d")?.length ?? 0).toBeGreaterThan(0);
  });

  it("renders a compact icon button in iconOnly mode", () => {
    renderButton({ iconOnly: true });
    expect(
      screen.getByRole("button", { name: "Scan to get this picture on your phone" }),
    ).toBeInTheDocument();
  });

  it("shows the plain-language caption in the popover", async () => {
    renderButton({ caption: "Point your phone here." });
    fireEvent.click(
      screen.getByRole("button", { name: "Scan to get this picture on your phone" }),
    );
    await waitFor(() =>
      expect(screen.getByText("Point your phone here.")).toBeInTheDocument(),
    );
  });
});
