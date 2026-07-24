import { Anchor, Group } from "@mantine/core";
import { IconDownload } from "@tabler/icons-react";
import { api } from "../api/client";

/**
 * "Imaging log (CSV)" — one tap to save a plain-CSV record of every finished
 * stack (date, target, subs, integration, typical star size, calibration,
 * noise, app version): a keepsake / journal a beginner can print, keep, or paste
 * into a forum post. A plain download link (the endpoint serves a
 * Content-Disposition attachment). Self-hides until at least one stack exists, so
 * a fresh install shows nothing rather than a link to an empty file.
 */
export function ImagingLogButton({ nStacks }: { nStacks: number }) {
  if (!(nStacks > 0)) return null;
  return (
    <Anchor
      href={api.imagingLogUrl()}
      download
      size="sm"
      c="violet"
      aria-label="Download your imaging log as a CSV file"
    >
      <Group gap={4} wrap="nowrap">
        <IconDownload size={15} />
        Imaging log (CSV)
      </Group>
    </Anchor>
  );
}
