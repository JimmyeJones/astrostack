import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import {
  finishUneditedSummary, RefinishPicturesCard, refinishSummary, withoutCovered,
} from "./RefinishPicturesCard";

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

beforeEach(() => {
  // Nothing unedited unless a test says otherwise, so the repair's own tests
  // see the card exactly as they did before the second half existed.
  vi.spyOn(client.api, "finishUneditedPreview").mockResolvedValue({ finish: [], left_alone: {} });
});

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

describe("finishUneditedSummary", () => {
  it("says nothing when every picture has been edited", () => {
    expect(finishUneditedSummary(undefined)).toBeNull();
    expect(finishUneditedSummary({ finish: [], left_alone: { has_edit: [t("M_42")] } })).toBeNull();
  });

  it("counts the pictures and names what it leaves alone, by reason", () => {
    const s = finishUneditedSummary({
      finish: [t("M_31"), t("M_42")],
      left_alone: { has_edit: [t("M_51")], cover_pinned: [t("M_8"), t("M_20")] },
    });
    expect(s?.lead).toMatch(/^2 pictures have never been edited/);
    expect(s?.leftAlone).toBe("Left alone: 1 with an edit you saved, 2 you pinned as the cover.");
    expect(finishUneditedSummary({ finish: [t("M_31")], left_alone: {} })?.leftAlone).toBeNull();
  });
});

describe("withoutCovered", () => {
  it("drops the repair's targets the unedited finish already reaches", () => {
    const p = { refinish: [t("M_31"), t("M_42")], left_alone: {} };
    expect(withoutCovered(p, { finish: [t("M_42")], left_alone: {} })?.refinish).toEqual([t("M_31")]);
    expect(withoutCovered(p, undefined)).toBe(p);
  });
});

describe("RefinishPicturesCard — Finish my unedited pictures", () => {
  it("offers one button, not two, when the unedited finish covers the repair", async () => {
    vi.spyOn(client.api, "refinishPreview").mockResolvedValue({ refinish: [t("M_31")], left_alone: {} });
    vi.spyOn(client.api, "finishUneditedPreview").mockResolvedValue({ finish: [t("M_31"), t("M_42")], left_alone: {} });
    renderCard();
    expect(await screen.findByRole("button", { name: /Finish 2 pictures/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Re-finish/ })).toBeNull();
  });

  it("starts the job only after the owner confirms", async () => {
    vi.spyOn(client.api, "refinishPreview").mockResolvedValue({ refinish: [], left_alone: {} });
    vi.spyOn(client.api, "finishUneditedPreview").mockResolvedValue({ finish: [t("M_31")], left_alone: {} });
    const start = vi.spyOn(client.api, "startFinishUnedited").mockResolvedValue({ job_id: "j2", already_running: false });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderCard();
    const button = await screen.findByRole("button", { name: /Finish 1 picture/ });
    fireEvent.click(button);
    expect(start).not.toHaveBeenCalled();
    fireEvent.click(button);
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(confirm.mock.calls[0][0]).toMatch(/Only pictures with no saved edit are touched/);
  });
});
