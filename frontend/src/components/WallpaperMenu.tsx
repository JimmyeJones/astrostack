import { useState } from "react";
import { Menu, Button, Switch } from "@mantine/core";
import { IconDeviceMobile, IconDeviceDesktop, IconSquare, IconWallpaper } from "@tabler/icons-react";
import { api } from "../api/client";

/**
 * "Make it your wallpaper" — one-tap download of the finished stack cropped and
 * sized to a phone, desktop, or square background, auto-centred on the target.
 *
 * The native Seestar field of view is roughly square, so a straight download
 * letterboxes badly as a lock-screen; each menu item hits the server-side
 * `wallpaper` endpoint, which crops to the chosen aspect (centred on the
 * plate-solved target when known) and returns a ready-to-set JPEG. Pure links —
 * the browser downloads the file, no client-side image work.
 *
 * An optional "North up" switch (shown only when the run's WCS carries a
 * more-than-trivial field rotation) rotates the picture so celestial North points
 * up — like every reference photo of the object — before cropping; the crop
 * re-centres on the rotated target so nothing is cut off.
 */
const ASPECTS: {
  aspect: "phone" | "desktop" | "square";
  label: string;
  hint: string;
  icon: typeof IconDeviceMobile;
}[] = [
  { aspect: "phone", label: "Phone", hint: "Tall — lock screen", icon: IconDeviceMobile },
  { aspect: "desktop", label: "Desktop", hint: "Wide — 16:9", icon: IconDeviceDesktop },
  { aspect: "square", label: "Square", hint: "1:1 — socials", icon: IconSquare },
];

export function WallpaperMenu({
  safe,
  runId,
  size = "xs",
  variant = "light",
  canNorthUp = false,
}: {
  safe: string;
  runId: number;
  size?: string;
  variant?: string;
  /** Offer the "North up" toggle — only when the run has a real field rotation
   * to correct (e.g. `render-suggestion`'s `north_up_deg` is non-null). */
  canNorthUp?: boolean;
}) {
  const [northUp, setNorthUp] = useState(false);
  return (
    <Menu shadow="md" width={220} position="bottom-start" closeOnItemClick={false}>
      <Menu.Target>
        <Button
          size={size as never}
          variant={variant}
          leftSection={<IconWallpaper size={14} />}
        >
          Wallpaper
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Make it your wallpaper</Menu.Label>
        {ASPECTS.map(({ aspect, label, hint, icon: Icon }) => (
          <Menu.Item
            key={aspect}
            leftSection={<Icon size={16} />}
            component="a"
            href={api.stackWallpaperUrl(safe, runId, aspect, northUp)}
            // `download` hints the browser to save rather than navigate.
            download
          >
            {label}
            <span style={{ display: "block", fontSize: "0.72rem", opacity: 0.6 }}>{hint}</span>
          </Menu.Item>
        ))}
        {canNorthUp ? (
          <>
            <Menu.Divider />
            <div style={{ padding: "6px 12px" }}>
              <Switch
                size="xs"
                label="North up"
                checked={northUp}
                onChange={(e) => setNorthUp(e.currentTarget.checked)}
                aria-label="Orient wallpaper North up"
              />
            </div>
          </>
        ) : null}
      </Menu.Dropdown>
    </Menu>
  );
}
