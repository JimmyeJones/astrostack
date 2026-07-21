import { Menu, Button } from "@mantine/core";
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
}: {
  safe: string;
  runId: number;
  size?: string;
  variant?: string;
}) {
  return (
    <Menu shadow="md" width={220} position="bottom-start">
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
            href={api.stackWallpaperUrl(safe, runId, aspect)}
            // `download` hints the browser to save rather than navigate.
            download
          >
            {label}
            <span style={{ display: "block", fontSize: "0.72rem", opacity: 0.6 }}>{hint}</span>
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
