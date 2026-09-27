import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { RefinishPicturesCard, refinishSummary } from "./RefinishPicturesCard";

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <RefinishPicturesCard />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

const t = (name: string) => ({ safe_name: name, name });

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("refinishSummary", () => {
  it("says nothing when there is nothing to give back", () => {
    expect(refinishSummary(undefined)).toBeNull();
    expect(refinishSummary({ refinish: [], left_alone: { by_hand: [t("M_42")] } })).toBeNull();
  });

  it("counts the pictures and names the hand-finished ones it leaves alone", () => {
    const s = refinishSummary({ refinish: [t("M_31"), t("M_42")], left_alone: { by_hand: [t("M_51")] } });
    expect(s?.lead).toMatch(/^2 targets are showing a flat, unedited stack/);
    expect(s?.byHand).toMatch(/^1 other flat target had a picture you finished yourself/);
  });

  it("has no hand-finished sentence when there are none", () => {
    expect(refinishSummary({ refinish: [t("M_31")], left_alone: {} })?.byHand).toBeNull();
  });
});

describe("RefinishPicturesCard", () => {
  it("renders nothing when no picture needs giving back", async () => {
    const spy = vi.spyOn(client.api, "refinishPreview").mockResolvedValue({ refinish: [], left_alone: {} });
    const { container } = renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(container.textContent).not.toMatch(/Give back pictures/);
  });

  it("starts the job only after the owner confirms", async () => {
    vi.spyOn(client.api, "refinishPreview").mockResolvedValue({ refinish: [t("M_31"), t("M_42")], left_alone: {} });
    const start = vi.spyOn(client.api, "startRefinish").mockResolvedValue({ job_id: "j1", already_running: false });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderCard();
    const button = await screen.findByRole("button", { name: /Re-finish 2 pictures/ });
    fireEvent.click(button);
    expect(start).not.toHaveBeenCalled();
    fireEvent.click(button);
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(confirm.mock.calls[0][0]).toMatch(/Anything you edited by hand is left exactly as it is/);
  });
});
