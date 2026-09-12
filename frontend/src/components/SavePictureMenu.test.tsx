import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SavePictureMenu } from "./SavePictureMenu";
import { api, type StackRun } from "../api/client";
import type { CaptureLabel } from "../format";

/**
 * The one "Save / share" menu, shared by the Target page's hero and every
 * History run card. It exists because those two were written separately and
 * drifted — so what is pinned here is the *union* item set and the flags each
 * download carries, which is exactly what drifted.
 */

function mkRun(over: Partial<StackRun> = {}): StackRun {
  return {
    id: 9,
    timestamp_utc: "2026-01-02T03:04:05Z",
    output_basename: "M42_stack_01",
    n_frames_used: 240,
    canvas_w: 1920,
    canvas_h: 1080,
    coverage_min: 1,
    coverage_max: 1,
    has_fits: true,
    has_tiff: true,
    has_preview: true,
    notes: null,
    total_exposure_s: 2400,
    capture_night_start: "2026-01-01",
    capture_night_end: "2026-01-01",
    ...over,
  } as StackRun;
}

function renderMenu(props: Partial<Parameters<typeof SavePictureMenu>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onToPhone = vi.fn();
  const utils = render(
    <QueryClientProvider client={qc}>
      <MantineProvider>
        <SavePictureMenu
          safe="M_42"
          run={mkRun()}
          shareName="M 42"
          captureLabel={"1 Jan 2026" as CaptureLabel}
          onToPhone={onToPhone}
          {...props}
        />
      </MantineProvider>
    </QueryClientProvider>,
  );
  return { ...utils, onToPhone };
}

function open() {
  fireEvent.click(screen.getByRole("button", { name: /save \/ share/i }));
}

const item = (name: string | RegExp) =>
  screen.findByRole("menuitem", { name: typeof name === "string" ? new RegExp(`^${name}`) : name });

afterEach(() => {
  const nav = navigator as unknown as Record<string, unknown>;
  delete nav.canShare;
  delete nav.share;
});

describe("SavePictureMenu", () => {
  it("offers the union of what the two pages used to offer, in one menu", async () => {
    // Sharing files is feature-detected at mount, so the share items only exist
    // on a browser that can do it.
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    nav.share = async () => {};

    renderMenu();
    open();

    // Download — the Target hero had no FITS and no TIFF; History had them.
    for (const name of [
      "Full-res PNG", "PNG", "JPEG", "Framed keepsake", "With scale & compass",
      "With object names", "FITS", "TIFF",
    ]) {
      expect(await item(name)).toBeInTheDocument();
    }
    // Share — History had no "Share the keepsake"; the Target hero had no
    // "Copy caption".
    expect(await screen.findByRole("menuitem", { name: "Share picture" }))
      .toBeInTheDocument();
    expect(await screen.findByLabelText("Share the framed keepsake"))
      .toBeInTheDocument();
    expect(await item("To phone")).toBeInTheDocument();
    expect(await item("Copy caption")).toBeInTheDocument();
    expect(await item("Zoom clip")).toBeInTheDocument();
    // …and the wallpapers come from WallpaperMenuItems, not a copy.
    for (const aspect of ["Phone", "Desktop", "Square"]) {
      expect(await item(aspect)).toBeInTheDocument();
    }
  });

  it("hides FITS and TIFF for a run that has neither", async () => {
    renderMenu({ run: mkRun({ has_fits: false, has_tiff: false }) });
    open();

    expect(await item("PNG")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^FITS/ })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /^TIFF/ })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /^Full-res PNG/ })).toBeNull();
    // With no FITS behind it, the preview PNG *is* the best this run has, and
    // the hint says so rather than calling it a "quick preview".
    expect((await item("PNG")).textContent).toContain("the best this run has");
  });

  it("offers nothing at all for a run with no files", () => {
    renderMenu({ run: mkRun({ has_fits: false, has_tiff: false, has_preview: false }) });
    expect(screen.queryByRole("button", { name: /save \/ share/i })).toBeNull();
  });

  it("carries North-up and the nameplate into exactly the right downloads", async () => {
    // The flags are positional on `stackArtifactUrl`, and the four JPEG-family
    // items each want a different combination — the kind of thing that is easy
    // to transpose and impossible to see in a screenshot.
    renderMenu({ northUp: true, nameplate: true });
    open();

    expect((await item("Full-res PNG")).getAttribute("href"))
      .toBe(api.stackFullResPngUrl("M_42", 9, true));
    // The plain JPEG follows both toggles…
    expect((await item("JPEG")).getAttribute("href"))
      .toBe(api.stackArtifactUrl("M_42", 9, "jpeg", true, true));
    // …the keepsake follows North-up but carries its own caption, so it ignores
    // the nameplate rather than captioning the same facts twice…
    expect((await item("Framed keepsake")).getAttribute("href"))
      .toBe(api.stackArtifactUrl("M_42", 9, "jpeg", true, false, true));
    // …and the marked download adds the scale bar and compass to the same turn.
    expect((await item("With scale & compass")).getAttribute("href"))
      .toBe(api.stackArtifactUrl("M_42", 9, "jpeg", true, false, false, true));
    // …while the named download asks for the object labels *instead of* the
    // marks — the two are separate downloads, not one that grew a second flag.
    // `label_objects` is the last of five positional booleans, which is exactly
    // the transposition this test exists to catch.
    expect((await item("With object names")).getAttribute("href"))
      .toBe(api.stackArtifactUrl("M_42", 9, "jpeg", true, false, false, false, true));
    expect((await item("With object names")).getAttribute("href"))
      .toContain("label_objects=true");
    expect((await item("With object names")).getAttribute("href"))
      .not.toContain("scale=true");
    // The bare PNG has no rendering flags at all.
    expect((await item("PNG")).getAttribute("href"))
      .toBe(api.stackArtifactUrl("M_42", 9, "preview"));
  });

  it("leaves the downloads unturned when the page has no toggles", async () => {
    renderMenu();
    open();

    expect((await item("Full-res PNG")).getAttribute("href"))
      .toBe(api.stackFullResPngUrl("M_42", 9));
    expect((await item("JPEG")).getAttribute("href"))
      .toBe(api.stackArtifactUrl("M_42", 9, "jpeg"));
  });

  it("asks the page to open the phone QR, and owns no modal of its own", async () => {
    // A menu closes on click, so a popover owned by the item would be unmounted
    // with the dropdown before it could be read — the modal stays on the page.
    const { onToPhone } = renderMenu();
    open();
    fireEvent.click(await item("To phone"));

    expect(onToPhone).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("copies a caption built from the run and its catalog identity", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText }, configurable: true,
    });
    vi.spyOn(api, "stackAnnotations").mockResolvedValue(
      { objects: [], scale_bar: null } as unknown as Awaited<
        ReturnType<typeof api.stackAnnotations>>);

    renderMenu({
      identity: {
        id: "M 42", name: "Orion Nebula", type: "Nebula",
        constellation: "Orion", constellation_abbr: "Ori",
        ra_deg: 83.8, dec_deg: -5.4, matched_by: "name",
      },
    });
    open();
    fireEvent.click(await item("Copy caption"));

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const caption = writeText.mock.calls[0][0] as string;
    expect(caption).toContain("Orion Nebula");
    expect(caption).toContain("240");
  });

  it("carries the Moon disc into the marked download when the card asks for it", async () => {
    // The disc is a per-card *view* toggle, like North-up and the nameplate: the
    // file carries what the screen is showing, rather than the menu growing a
    // twentieth item. `moon` is the sixth positional boolean, which is exactly
    // the transposition this assertion exists to catch.
    renderMenu({ moon: true });
    open();
    expect((await item("With scale & compass")).getAttribute("href"))
      .toBe(api.stackArtifactUrl(
        "M_42", 9, "jpeg", false, false, false, true, false, true));
    // …and the hint says so, so the item isn't silently two different downloads.
    expect((await item("With scale & compass")).textContent)
      .toContain("full Moon for scale");
  });

  it("leaves the marked download unchanged for a surface without the toggle", async () => {
    // The Target hero passes no `moon`, so its picture is byte-for-byte the one
    // it always served.
    renderMenu();
    open();
    const href = (await item("With scale & compass")).getAttribute("href");
    expect(href).toBe(
      api.stackArtifactUrl("M_42", 9, "jpeg", false, false, false, true));
    expect(href).not.toContain("moon=");
    expect((await item("With scale & compass")).textContent)
      .not.toContain("full Moon for scale");
  });
});
