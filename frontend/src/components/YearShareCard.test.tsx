import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { YearShareCard } from "./YearShareCard";

function renderCard(props: React.ComponentProps<typeof YearShareCard>) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <YearShareCard {...props} />
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("YearShareCard", () => {
  it("offers this year's poster, not last year's", () => {
    renderCard({ year: 2024, caption: "2024 under the stars · 12 nights out" });
    const link = screen.getByRole("link", { name: /Download poster/ });
    expect(link).toHaveAttribute("href", "/api/recap/year/2024.jpg");
    expect(link).toHaveAttribute("download");
  });

  it("shows the caption so it can be read before it is posted", () => {
    renderCard({ year: 2026, caption: "2026 under the stars · 31 nights out" });
    expect(screen.getByText(/2026 under the stars · 31 nights out/))
      .toBeInTheDocument();
  });

  it("copies the caption to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderCard({ year: 2026, caption: "2026 under the stars" });
    fireEvent.click(screen.getByRole("button", { name: /Copy caption/ }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith("2026 under the stars"));
  });

  it("offers the poster alone when there is no caption to copy", () => {
    // An older backend sends no caption; the poster still renders server-side,
    // so the download must not be gated on it.
    renderCard({ year: 2026 });
    expect(screen.getByRole("link", { name: /Download poster/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copy caption/ })).toBeNull();
  });

  it("leads with the year's own best picture and links to it", () => {
    renderCard({
      year: 2026, caption: "2026 under the stars",
      hero: {
        name: "M 31", safe: "M_31",
        thumbnail_url: "/api/targets/M_31/thumbnail", note: "",
      },
    });
    expect(screen.getByAltText("Your picture of M 31")).toHaveAttribute(
      "src", "/api/targets/M_31/thumbnail");
    expect(screen.getByRole("link", { name: /Your picture of M 31/ }))
      .toHaveAttribute("href", "/targets/M_31");
    // The year owns it outright, so the page says so rather than caveating.
    expect(screen.getByText("Everything you shot of it was in 2026."))
      .toBeInTheDocument();
  });

  it("passes on the backend's caveat when the picture may span years", () => {
    const note = "Your newest picture of it — it may include light from other "
      + "years too.";
    renderCard({
      year: 2026, caption: "2026 under the stars",
      hero: {
        name: "M 31", safe: "M_31",
        thumbnail_url: "/api/targets/M_31/thumbnail", note,
      },
    });
    expect(screen.getByText(note)).toBeInTheDocument();
    expect(screen.queryByText(/Everything you shot of it was in/)).toBeNull();
  });

  it("still offers the poster when no picture exists yet", () => {
    renderCard({ year: 2026, caption: "2026 under the stars", hero: null });
    expect(screen.queryByTestId("year-hero")).toBeNull();
    expect(screen.getByRole("link", { name: /Download poster/ })).toBeInTheDocument();
  });
});
