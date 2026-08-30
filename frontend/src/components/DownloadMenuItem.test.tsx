import { MantineProvider, Menu } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DownloadMenuItem, filenameFromDisposition } from "./DownloadMenuItem";

function renderItem(props: Partial<Parameters<typeof DownloadMenuItem>[0]> = {}) {
  return render(
    <MantineProvider>
      <Notifications />
      <Menu opened>
        <Menu.Target><button>open</button></Menu.Target>
        <Menu.Dropdown>
          <DownloadMenuItem
            url="/api/clip"
            filename="fallback.webp"
            icon={<span data-testid="icon" />}
            label="Zoom clip"
            hint="A few seconds gliding into your target"
            busyHint="Building your clip"
            {...props}
          />
        </Menu.Dropdown>
      </Menu>
    </MantineProvider>,
  );
}

/** jsdom has no `URL.createObjectURL`, which is exactly the "old browser"
 * fallback path — install one (and a fetch) to exercise the blob path. */
function withBlobSupport(response: Partial<Response>) {
  const url = URL as unknown as {
    createObjectURL?: (b: Blob) => string;
    revokeObjectURL?: (u: string) => void;
  };
  url.createObjectURL = vi.fn(() => "blob:mock");
  url.revokeObjectURL = vi.fn();
  const fetchMock = vi.fn(async () => ({
    ok: true,
    headers: new Headers(),
    blob: async () => new Blob(["x"]),
    ...response,
  } as unknown as Response));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  const url = URL as unknown as Record<string, unknown>;
  delete url.createObjectURL;
  delete url.revokeObjectURL;
  vi.restoreAllMocks();
});

describe("filenameFromDisposition", () => {
  it("falls back when the server didn't name the file", () => {
    expect(filenameFromDisposition(null, "fallback.webp")).toBe("fallback.webp");
    expect(filenameFromDisposition("attachment", "fallback.webp")).toBe("fallback.webp");
  });

  it("takes the plain filename the server sent", () => {
    expect(filenameFromDisposition('attachment; filename="M42_zoom.png"', "f.webp"))
      .toBe("M42_zoom.png");
  });

  it("prefers the RFC 5987 encoded name, and decodes it", () => {
    expect(filenameFromDisposition(
      "attachment; filename=\"fallback\"; filename*=UTF-8''M%2042_zoom.webp", "f.webp",
    )).toBe("M 42_zoom.webp");
  });

  it("survives a malformed encoding rather than failing the download", () => {
    expect(filenameFromDisposition("attachment; filename*=UTF-8''%E0%A4%A", "f.webp"))
      .toBe("f.webp");
  });
});

describe("DownloadMenuItem", () => {
  it("renders a plain download link where blobs aren't available", async () => {
    // jsdom's default: no URL.createObjectURL. Nothing is taken away — the item
    // is exactly the <a download> it has always been.
    renderItem();
    const item = await screen.findByRole("menuitem", { name: /Zoom clip/ });
    expect(item.getAttribute("href")).toBe("/api/clip");
    expect(item.hasAttribute("download")).toBe(true);
  });

  it("shows the building line while the server builds the file", async () => {
    let release: (() => void) | null = null;
    const gate = new Promise<void>((r) => { release = r; });
    const fetchMock = withBlobSupport({});
    // jsdom tries to navigate on a real anchor click; the save itself is covered
    // by its own tests below.
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    fetchMock.mockImplementation(async () => {
      await gate;
      return {
        ok: true, headers: new Headers(),
        blob: async () => new Blob(["x"]),
      } as unknown as Response;
    });

    renderItem();
    const item = await screen.findByRole("menuitem", { name: /Zoom clip/ });
    // The plain link is gone — a blob fetch can report progress, a link can't.
    expect(item.hasAttribute("href")).toBe(false);
    fireEvent.click(item);

    await waitFor(() => expect(screen.getByText("Building your clip")).toBeInTheDocument());
    // …and the menu is still open, or the spinner would have unmounted with it.
    expect(screen.getByRole("menuitem", { name: /Zoom clip/ })).toBeInTheDocument();

    release!();
    await waitFor(() =>
      expect(screen.queryByText("Building your clip")).toBeNull());
    expect(fetchMock).toHaveBeenCalledWith("/api/clip");
  });

  it("saves the file under the name the server gave it", async () => {
    withBlobSupport({
      headers: new Headers({ "content-disposition": 'attachment; filename="M42_zoom.png"' }),
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    renderItem();
    fireEvent.click(await screen.findByRole("menuitem", { name: /Zoom clip/ }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    const anchor = click.mock.instances[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("M42_zoom.png");
    expect(anchor.href).toContain("blob:mock");
  });

  it("falls back to the given filename when the server names nothing", async () => {
    withBlobSupport({});
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    renderItem();
    fireEvent.click(await screen.findByRole("menuitem", { name: /Zoom clip/ }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe("fallback.webp");
  });

  it("explains a failed build instead of leaving the spinner spinning", async () => {
    const fetchMock = withBlobSupport({});
    fetchMock.mockResolvedValue({ ok: false, status: 404 } as unknown as Response);
    renderItem({ errorMessage: "Couldn't build a zoom clip for this run." });
    fireEvent.click(await screen.findByRole("menuitem", { name: /Zoom clip/ }));

    await waitFor(() => expect(
      screen.getByText("Couldn't build a zoom clip for this run.")).toBeInTheDocument());
    expect(screen.queryByText("Building your clip")).toBeNull();
  });
});
