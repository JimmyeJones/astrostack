import { useMemo, useState } from "react";
import {
  ActionIcon,
  Box,
  Button,
  Modal,
  Popover,
  Stack,
  Text,
  Tooltip,
} from "@mantine/core";
import type { ButtonProps, MantineSize } from "@mantine/core";
import { IconDeviceMobile } from "@tabler/icons-react";
import { absoluteLanUrl, qrMatrix } from "../qr";

/** Quiet-zone width in modules (the QR spec's minimum is 4). */
const MARGIN = 4;

/** Build a single SVG path covering every dark module of the matrix. */
function darkModulesPath(url: string): { path: string; extent: number } {
  const m = qrMatrix(url);
  const parts: string[] = [];
  for (let r = 0; r < m.size; r++) {
    for (let c = 0; c < m.size; c++) {
      if (m.isDark(r, c)) parts.push(`M${c + MARGIN} ${r + MARGIN}h1v1h-1z`);
    }
  }
  return { path: parts.join(""), extent: m.size + MARGIN * 2 };
}

/**
 * The QR itself plus its one-line explanation — the body shared by the popover
 * form below and the modal form used when the control lives inside a menu
 * (a menu closes on click, so its own popover would be unmounted with it).
 */
export function ScanToPhoneQr({
  url,
  caption = "Point your phone camera at this code to open the picture and save it.",
}: {
  url: string;
  caption?: string;
}) {
  const absolute = useMemo(() => absoluteLanUrl(url), [url]);
  const qr = useMemo(() => darkModulesPath(absolute), [absolute]);
  return (
    <Stack gap="xs" align="center" maw={220} mx="auto">
      <Box p="xs" style={{ background: "#fff", borderRadius: 8, lineHeight: 0 }}>
        <svg
          viewBox={`0 0 ${qr.extent} ${qr.extent}`}
          width={176}
          height={176}
          role="img"
          aria-label="QR code linking to this picture"
          shapeRendering="crispEdges"
        >
          <path d={qr.path} fill="#000" />
        </svg>
      </Box>
      <Text size="xs" c="dimmed" ta="center">
        {caption}
      </Text>
    </Stack>
  );
}

/**
 * The same QR in a modal, for callers that open it from a menu item. The QR is
 * built only while the modal is open, so an unopened one costs nothing.
 */
export function ScanToPhoneModal({
  url,
  caption,
  opened,
  onClose,
  title = "Scan to get it on your phone",
}: {
  url: string;
  caption?: string;
  opened: boolean;
  onClose: () => void;
  title?: string;
}) {
  return (
    <Modal opened={opened} onClose={onClose} title={title} centered size="sm">
      {opened ? <ScanToPhoneQr url={url} caption={caption} /> : null}
    </Modal>
  );
}

/**
 * "Scan to get it on your phone" — a QR code, popped from a small button, that a
 * beginner's phone camera reads to open the finished picture's download URL
 * directly. Closes the single most common post-success friction ("how do I get
 * this onto my phone?") with zero typing and no account.
 *
 * The QR encodes the **absolute LAN URL** of the download endpoint, resolved
 * from `window.location` (the address the user already typed) so it works behind
 * Docker/reverse-proxy without the server guessing its own hostname. Generation
 * is entirely client-side — nothing leaves the LAN. On a phone browser (which
 * would just scan its own screen) this is redundant with the OS share sheet, but
 * it costs nothing and is genuinely useful on the common laptop-on-LAN case.
 *
 * The QR is always drawn dark-on-white with a white quiet zone so it scans in
 * either light or dark UI theme.
 */
export function ScanToPhoneButton({
  url,
  caption = "Point your phone camera at this code to open the picture and save it.",
  size = "xs",
  variant = "default",
  iconOnly = false,
  label = "To phone",
  tooltip = "Scan to get this picture on your phone",
  ariaLabel = "Scan to get this picture on your phone",
}: {
  /** The picture download URL — a relative API path or an absolute URL. */
  url: string;
  /** Plain-language help shown under the QR. */
  caption?: string;
  size?: MantineSize;
  variant?: ButtonProps["variant"];
  /** Render a compact icon button (for the lightbox toolbar) instead of a labelled one. */
  iconOnly?: boolean;
  label?: string;
  tooltip?: string;
  ariaLabel?: string;
}) {
  const [opened, setOpened] = useState(false);

  const trigger = iconOnly ? (
    <Tooltip label={tooltip}>
      <ActionIcon
        size="lg"
        variant="subtle"
        color="gray"
        onClick={() => setOpened((o) => !o)}
        aria-label={ariaLabel}
      >
        <IconDeviceMobile size={20} />
      </ActionIcon>
    </Tooltip>
  ) : (
    <Button
      size={size}
      variant={variant}
      leftSection={<IconDeviceMobile size={size === "xs" ? 14 : 16} />}
      onClick={() => setOpened((o) => !o)}
      aria-label={ariaLabel}
    >
      {label}
    </Button>
  );

  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="bottom"
      withArrow
      shadow="md"
      trapFocus
    >
      <Popover.Target>{trigger}</Popover.Target>
      <Popover.Dropdown>
        {/* Built only once the popover is open, so an off-screen button costs
            nothing. */}
        {opened ? <ScanToPhoneQr url={url} caption={caption} /> : null}
      </Popover.Dropdown>
    </Popover>
  );
}
