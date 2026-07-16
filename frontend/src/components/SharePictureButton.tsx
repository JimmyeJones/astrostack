import { useState } from "react";
import { ActionIcon, Button, Tooltip } from "@mantine/core";
import type { ButtonProps, MantineSize } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconShare } from "@tabler/icons-react";
import { canSharePictureFiles, sharePicture } from "../share";

/**
 * "Share this picture" control — opens the OS share sheet with the run's JPEG so
 * a beginner can post their result straight to Instagram/Messages/WhatsApp,
 * instead of download → find in files → open app → attach.
 *
 * Progressive enhancement: renders **nothing** unless this browser supports
 * sharing files (checked once at mount), so desktop browsers without file-share
 * simply keep the existing download menu and never see a dead button. A user
 * cancel is silent; only a genuine fetch/share failure shows a message.
 */
export function SharePictureButton({
  url,
  filename,
  title,
  text,
  size = "xs",
  variant = "light",
  iconOnly = false,
  label = "Share",
  tooltip = "Share this picture to another app",
  ariaLabel = "Share picture",
  errorMessage = "Couldn't share this picture — try downloading it instead.",
}: {
  /** The picture to share — the small, share-friendly JPEG artifact URL. */
  url: string;
  /** Filename the shared file carries (e.g. "m31.jpg"). */
  filename: string;
  /** Optional caption title (target name + date) pre-filled in the share sheet. */
  title?: string;
  /** Optional caption text. */
  text?: string;
  size?: MantineSize;
  variant?: ButtonProps["variant"];
  /** Render a compact icon button (for the lightbox toolbar) instead of a labelled button. */
  iconOnly?: boolean;
  label?: string;
  /** Tooltip copy — override for non-picture shares (e.g. a clip). */
  tooltip?: string;
  /** Accessible label — override for non-picture shares. */
  ariaLabel?: string;
  /** Notification shown on a genuine share failure — override per content type. */
  errorMessage?: string;
}) {
  // Feature-detect once at mount (stable per browser); render nothing if files
  // can't be shared here.
  const [supported] = useState(() => canSharePictureFiles());
  const [busy, setBusy] = useState(false);
  if (!supported) return null;

  const doShare = async () => {
    setBusy(true);
    const outcome = await sharePicture({ url, filename, title, text });
    setBusy(false);
    if (outcome === "error") {
      notifications.show({ message: errorMessage, color: "red" });
    }
    // "shared" / "cancelled" / "unsupported" → stay quiet (success or user cancel).
  };

  if (iconOnly) {
    return (
      <Tooltip label={tooltip}>
        <ActionIcon
          size="lg"
          variant="subtle"
          color="gray"
          loading={busy}
          onClick={doShare}
          aria-label={ariaLabel}
        >
          <IconShare size={20} />
        </ActionIcon>
      </Tooltip>
    );
  }

  return (
    <Tooltip label={tooltip}>
      <Button
        size={size}
        variant={variant}
        leftSection={<IconShare size={size === "xs" ? 14 : 16} />}
        loading={busy}
        onClick={doShare}
        aria-label={ariaLabel}
      >
        {label}
      </Button>
    </Tooltip>
  );
}
