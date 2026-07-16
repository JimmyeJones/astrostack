import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { notifications } from "@mantine/notifications";
import { SharePictureButton } from "./SharePictureButton";

function stubShare(opts: {
  canShare?: (data?: ShareData) => boolean;
  share?: (data?: ShareData) => Promise<void>;
}) {
  const nav = navigator as unknown as Record<string, unknown>;
  nav.canShare = opts.canShare;
  nav.share = opts.share;
  return () => { delete nav.canShare; delete nav.share; };
}

function renderButton(props: Partial<React.ComponentProps<typeof SharePictureButton>> = {}) {
  return render(
    <MantineProvider>
      <SharePictureButton url="/api/run/1/jpeg" filename="m31.jpg" title="M31" {...props} />
    </MantineProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SharePictureButton", () => {
  it("renders nothing on a browser that can't share files", () => {
    const restore = stubShare({ canShare: () => false, share: async () => {} });
    renderButton();
    expect(screen.queryByRole("button", { name: "Share picture" })).not.toBeInTheDocument();
    restore();
  });

  it("shares the picture through the OS sheet on click", async () => {
    const share = vi.fn(async (_d?: ShareData) => {});
    const restore = stubShare({ canShare: () => true, share });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: "image/jpeg" }),
    })));

    renderButton();
    const btn = await screen.findByRole("button", { name: "Share picture" });
    fireEvent.click(btn);

    await waitFor(() => expect(share).toHaveBeenCalledTimes(1));
    const data = share.mock.calls[0][0] as ShareData;
    expect(data.title).toBe("M31");
    expect(data.files?.[0].name).toBe("m31.jpg");
    restore();
  });

  it("shows a message when sharing genuinely fails (but not on cancel)", async () => {
    const showSpy = vi.spyOn(notifications, "show").mockImplementation(() => "");
    const restore = stubShare({
      canShare: () => true,
      share: async () => { throw new Error("platform failure"); },
    });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob([new Uint8Array([1])], { type: "image/jpeg" }),
    })));

    renderButton();
    fireEvent.click(await screen.findByRole("button", { name: "Share picture" }));

    await waitFor(() => expect(showSpy).toHaveBeenCalledTimes(1));
    expect(showSpy.mock.calls[0][0]).toMatchObject({ color: "red" });
    restore();
  });

  it("stays silent when the user cancels the share sheet", async () => {
    const showSpy = vi.spyOn(notifications, "show").mockImplementation(() => "");
    const abort = Object.assign(new Error("cancel"), { name: "AbortError" });
    const restore = stubShare({ canShare: () => true, share: async () => { throw abort; } });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob([new Uint8Array([1])], { type: "image/jpeg" }),
    })));

    renderButton();
    const btn = await screen.findByRole("button", { name: "Share picture" });
    fireEvent.click(btn);

    // Give the async share a tick to settle, then assert no notification fired.
    await waitFor(() => expect(btn).not.toBeDisabled());
    expect(showSpy).not.toHaveBeenCalled();
    restore();
  });
});
