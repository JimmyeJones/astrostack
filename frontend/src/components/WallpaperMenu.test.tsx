import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Menu } from "@mantine/core";
import { WallpaperMenu, WallpaperMenuItems } from "./WallpaperMenu";
import { api } from "../api/client";

function renderMenu(props: { canNorthUp?: boolean } = {}) {
  return render(
    <MantineProvider>
      <WallpaperMenu safe="m31" runId={7} {...props} />
    </MantineProvider>,
  );
}

describe("WallpaperMenu", () => {
  it("offers phone / desktop / square wallpaper downloads with the right URLs", async () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: /wallpaper/i }));

    const phone = (await screen.findByText("Phone")).closest("a");
    const desktop = (await screen.findByText("Desktop")).closest("a");
    const square = (await screen.findByText("Square")).closest("a");

    expect(phone).toHaveAttribute("href", api.stackWallpaperUrl("m31", 7, "phone"));
    expect(desktop).toHaveAttribute("href", api.stackWallpaperUrl("m31", 7, "desktop"));
    expect(square).toHaveAttribute("href", api.stackWallpaperUrl("m31", 7, "square"));
    // Each item downloads rather than navigating.
    expect(phone).toHaveAttribute("download");
  });

  it("builds the aspect (and optional north_up) into the wallpaper URL", () => {
    expect(api.stackWallpaperUrl("m31", 7, "phone")).toBe(
      "/api/targets/m31/stack-runs/7/wallpaper?aspect=phone",
    );
    expect(api.stackWallpaperUrl("ngc7000", 3, "desktop")).toBe(
      "/api/targets/ngc7000/stack-runs/3/wallpaper?aspect=desktop",
    );
    expect(api.stackWallpaperUrl("m31", 7, "square", true)).toBe(
      "/api/targets/m31/stack-runs/7/wallpaper?aspect=square&north_up=true",
    );
  });

  it("hides the North-up toggle unless the run can be oriented", async () => {
    renderMenu();
    fireEvent.click(screen.getByRole("button", { name: /wallpaper/i }));
    await screen.findByText("Phone");
    expect(screen.queryByLabelText(/orient wallpaper north up/i)).toBeNull();
  });

  it("offers a North-up toggle that rewrites the download links when on", async () => {
    renderMenu({ canNorthUp: true });
    fireEvent.click(screen.getByRole("button", { name: /wallpaper/i }));
    await screen.findByText("Phone");

    const toggle = screen.getByLabelText(/orient wallpaper north up/i);
    fireEvent.click(toggle);

    const phone = screen.getByText("Phone").closest("a");
    expect(phone).toHaveAttribute(
      "href", api.stackWallpaperUrl("m31", 7, "phone", true),
    );
  });
});

describe("WallpaperMenuItems", () => {
  it("offers the same three downloads inside someone else's menu", async () => {
    // The History card folds the wallpapers into its own "Save / share" menu
    // rather than keeping a second menu button beside it — same items, one
    // implementation.
    render(
      <MantineProvider>
        <Menu opened>
          <Menu.Dropdown>
            <WallpaperMenuItems safe="m31" runId={7} />
          </Menu.Dropdown>
        </Menu>
      </MantineProvider>,
    );
    expect((await screen.findByText("Phone")).closest("a"))
      .toHaveAttribute("href", api.stackWallpaperUrl("m31", 7, "phone"));
    expect(screen.getByText("Desktop").closest("a"))
      .toHaveAttribute("href", api.stackWallpaperUrl("m31", 7, "desktop"));
    expect(screen.getByText("Square").closest("a"))
      .toHaveAttribute("href", api.stackWallpaperUrl("m31", 7, "square"));
  });

  it("can be rendered without its own heading", async () => {
    render(
      <MantineProvider>
        <Menu opened>
          <Menu.Dropdown>
            <WallpaperMenuItems safe="m31" runId={7} withLabel={false} />
          </Menu.Dropdown>
        </Menu>
      </MantineProvider>,
    );
    await screen.findByText("Phone");
    expect(screen.queryByText("Make it your wallpaper")).not.toBeInTheDocument();
  });
});
