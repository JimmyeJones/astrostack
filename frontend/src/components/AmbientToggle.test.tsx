import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeAudioContext } from "../ambient/fakeAudio";
import { resetAmbientPlayer } from "../ambient/player";
import { AmbientSettings } from "./AmbientSettings";
import { AmbientToggle } from "./AmbientToggle";

// jsdom has no Web Audio, so install the stub as the real constructor: the
// toggle hides itself entirely when audio is unsupported, which is the
// behaviour the last test pins.
let ctx: FakeAudioContext;

beforeEach(() => {
  ctx = new FakeAudioContext();
  (window as unknown as { AudioContext: unknown }).AudioContext = function () {
    return ctx;
  };
  resetAmbientPlayer();
  localStorage.clear();
});

afterEach(() => {
  delete (window as unknown as { AudioContext?: unknown }).AudioContext;
  resetAmbientPlayer();
  localStorage.clear();
  vi.restoreAllMocks();
});

function renderToggle() {
  return render(
    <MantineProvider>
      <Notifications />
      <AmbientToggle />
    </MantineProvider>,
  );
}

describe("AmbientToggle", () => {
  it("offers to play, silent, on a fresh install", () => {
    renderToggle();
    expect(screen.getByRole("button", { name: "Play ambient sound" })).toBeInTheDocument();
    expect(ctx.resumes).toBe(0);
  });

  it("starts the sound from the click itself (the only place autoplay allows)", async () => {
    renderToggle();
    fireEvent.click(screen.getByRole("button", { name: "Play ambient sound" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Turn off ambient sound" })).toBeInTheDocument());
    expect(ctx.resumes).toBe(1);
    expect(localStorage.getItem("astrostack.ambient.enabled")).toBe("1");
  });

  it("suspends the context — not just mutes it — when switched off", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderToggle();
      fireEvent.click(screen.getByRole("button", { name: "Play ambient sound" }));
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Turn off ambient sound" })).toBeInTheDocument());
      fireEvent.click(screen.getByRole("button", { name: "Turn off ambient sound" }));
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Play ambient sound" })).toBeInTheDocument());
      // The opt-in clears immediately, before the fade finishes, so a reload
      // mid-fade still comes back silent.
      expect(localStorage.getItem("astrostack.ambient.enabled")).toBeNull();
      await vi.advanceTimersByTimeAsync(4000);
      await waitFor(() => expect(ctx.suspends).toBe(1));
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not claim to be playing when the browser blocks audio", async () => {
    ctx.resumeRejects = true;
    renderToggle();
    fireEvent.click(screen.getByRole("button", { name: "Play ambient sound" }));
    await waitFor(() => expect(screen.getByText("Couldn't start the ambient sound")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Play ambient sound" })).toBeInTheDocument();
    // …and the failed attempt is not remembered as an opt-in.
    expect(localStorage.getItem("astrostack.ambient.enabled")).toBeNull();
  });

  it("waits for a gesture before resuming a remembered opt-in after a reload", async () => {
    localStorage.setItem("astrostack.ambient.enabled", "1");
    renderToggle();
    // Nothing on mount — browsers refuse, and surprise audio is hostile.
    expect(ctx.resumes).toBe(0);
    fireEvent.pointerDown(window);
    await waitFor(() => expect(ctx.resumes).toBe(1));
  });

  it("stays silent on a gesture when the opt-in was never given", async () => {
    renderToggle();
    fireEvent.pointerDown(window);
    await new Promise((r) => setTimeout(r, 0));
    expect(ctx.resumes).toBe(0);
  });

  it("renders nothing at all where Web Audio is unavailable", () => {
    delete (window as unknown as { AudioContext?: unknown }).AudioContext;
    const { container } = renderToggle();
    expect(container.querySelector("button")).toBeNull();
  });
});

describe("AmbientSettings", () => {
  function renderSettings() {
    return render(
      <MantineProvider>
        <AmbientSettings />
      </MantineProvider>,
    );
  }

  it("explains what the sound is and that it is off by default", () => {
    renderSettings();
    expect(screen.getByText(/generated in your browser as it plays/)).toBeInTheDocument();
    expect(screen.getByText(/Off unless you turn it on/)).toBeInTheDocument();
    expect(screen.getByText(/remembered for this device only/)).toBeInTheDocument();
  });

  it("persists the volume per device as the slider moves", () => {
    renderSettings();
    const slider = screen.getByRole("slider");
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(Number(localStorage.getItem("astrostack.ambient.volume"))).toBeGreaterThan(0.4);
  });

  it("hides itself where Web Audio is unavailable", () => {
    delete (window as unknown as { AudioContext?: unknown }).AudioContext;
    renderSettings();
    expect(screen.queryByText("Ambient sound (this device)")).toBeNull();
  });
});
