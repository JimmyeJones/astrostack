import { CSSProperties, useState } from "react";
import { Box, Button, Loader, Menu } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import {
  IconChevronDown, IconClipboardText, IconDeviceMobile, IconDownload,
  IconPhotoDown, IconVideo,
} from "@tabler/icons-react";
import { api, ObjectInfo, StackRun } from "../api/client";
import type { CaptureLabel } from "../format";
import { fullResPngHint } from "../fullres";
import { keepsakeFilename, sharePictureText } from "../share";
import { tiffDownloadHint } from "../tiffDownload";
import { storedPreviewScaleBar } from "./AnnotatedImage";
import { DownloadMenuItem } from "./DownloadMenuItem";
import { postCaption } from "./postCaption";
import { SharePictureButton } from "./SharePictureButton";
import { WallpaperMenuItems } from "./WallpaperMenu";

/**
 * One line of plain-language help under a menu item's label — the wording that
 * used to live in each button's hover tooltip, now readable without hovering
 * (which a phone can't do anyway).
 */
export const MENU_HINT: CSSProperties = {
  display: "block", fontSize: "0.72rem", opacity: 0.6, whiteSpace: "normal",
};

/**
 * "Save / share" — everything you can do *with the finished picture*, behind one
 * menu.
 *
 * This used to be written twice: once in the Target page's hero row and once in
 * every History run card. They drifted, which is the whole reason this component
 * exists — the same picture offered a different set of things to do with it
 * depending on which page you were standing on. The Target copy had no "Copy
 * caption", no FITS and no TIFF; the History copy had no "Share the keepsake";
 * the same file was named differently on each ("JPEG (smaller — best for
 * sharing)" vs "JPEG" + a hint); and every item added since had to be added
 * twice or landed on one page only.
 *
 * **Consolidation is not removal** (AGENTS.md §1): the item set here is the
 * *union* of the two, every destination stays one click away, and no page loses
 * an action. What went away is the second implementation.
 *
 * The pieces are the ones that already existed — `SharePictureButton`,
 * `DownloadMenuItem`, `WallpaperMenuItems`, `sharePictureText`,
 * `keepsakeFilename`, `fullResPngHint`, `tiffDownloadHint`, `postCaption` — so
 * this is a regrouping, not a re-derivation.
 *
 * The wording follows the History card's label-plus-hint idiom (the one
 * v0.267.0 chose when it folded the buttons into a menu): a short item name
 * with one dimmed line of help under it, rather than a parenthetical crammed
 * into the name.
 *
 * Two things the caller keeps:
 * - **The QR modal.** A menu closes on click, so a popover owned by an item
 *   would be unmounted with the dropdown before it could be read. This calls
 *   `onToPhone` and renders no modal of its own.
 * - **The North-up / nameplate toggles.** They are per-card *view* state on the
 *   History page and don't exist on the Target hero, so they arrive as props;
 *   they must reach the JPEG-family hrefs exactly as they did before.
 */
export function SavePictureMenu({
  safe,
  run,
  shareName,
  captureLabel,
  shareCaption,
  identity,
  northUp = false,
  nameplate = false,
  canNorthUp = false,
  onToPhone,
  size,
  variant = "light",
  iconSize = 16,
  ariaLabel,
  responsiveLabel = false,
  position = "bottom-start",
  withinPortal = false,
}: {
  safe: string;
  run: StackRun;
  /** The target's display name, for the share sheet's title/text/filename. */
  shareName?: string | null;
  /** The night the subs were **shot** (`formatCaptureNights`), never the day the
   *  stack ran — the share sheet says "captured <this>". */
  captureLabel?: CaptureLabel | null;
  /** A ready-made sentence to pre-fill the OS share sheet with. Optional: a
   *  surface that hasn't built one shares with `sharePictureText`'s default. */
  shareCaption?: string;
  /** The target's catalog identity, so "Copy caption" can name the object. */
  identity?: ObjectInfo | null;
  /** Bake celestial North up into the JPEG family (a per-card view toggle). */
  northUp?: boolean;
  /** Bake the acquisition-data caption over the plain JPEG. */
  nameplate?: boolean;
  /** Offer the wallpaper "North up" switch — only when the run has a real field
   *  rotation to correct. */
  canNorthUp?: boolean;
  /** Open the page-owned "to phone" QR modal. */
  onToPhone: () => void;
  size?: string;
  variant?: string;
  iconSize?: number;
  ariaLabel?: string;
  /** Shorten the trigger's label to "Save" on a phone-width screen. */
  responsiveLabel?: boolean;
  position?: "bottom-start" | "bottom-end";
  withinPortal?: boolean;
}) {
  const qc = useQueryClient();
  const [copyingCaption, setCopyingCaption] = useState(false);

  // Nothing to save and nothing to share — offer no menu at all rather than an
  // empty dropdown.
  if (!run.has_preview && !run.has_fits && !run.has_tiff) return null;

  const name = (shareName ?? "").trim();
  const shareText = sharePictureText(shareName, captureLabel);

  // "Copy caption" — one correct, friendly sentence to paste wherever the user
  // is sharing (chat, socials). Built purely from facts the app already knows:
  // the target's catalog identity, this run's frame count / integration / date,
  // and the scale bar. The scale clause needs the run's WCS (the same
  // annotations fetch Identify/Scale use), so ensure it's loaded first — reusing
  // the cached result when the user already toggled Identify/Scale — then
  // degrade gracefully (drop the scale clause) if it can't be read.
  const copyCaption = async () => {
    setCopyingCaption(true);
    try {
      // The caption describes the *stored preview* — the picture being shared —
      // so it takes that picture's own bar, not the full canvas's.
      const cached = qc.getQueryData<Awaited<ReturnType<typeof api.stackAnnotations>>>(
        ["annotations", safe, run.id]);
      let scaleBar = storedPreviewScaleBar(cached, run);
      if (run.has_fits && !cached) {
        try {
          const data = await qc.fetchQuery({
            queryKey: ["annotations", safe, run.id],
            queryFn: () => api.stackAnnotations(safe, run.id),
            staleTime: Infinity,
          });
          scaleBar = storedPreviewScaleBar(data, run);
        } catch {
          scaleBar = null;  // no WCS / read failed → caption omits the scale clause
        }
      }
      const text = postCaption({
        name: identity?.name,
        catalogId: identity?.id,
        type: identity?.type,
        nFrames: run.n_frames_used,
        integrationS: run.total_exposure_s,
        captureNightStart: run.capture_night_start,
        captureNightEnd: run.capture_night_end,
        captureNights: run.capture_nights,
        scaleBar,
        fallbackName: name || safe,
      });
      try {
        await navigator.clipboard.writeText(text);
        notifications.show({
          message: "Caption copied — paste it wherever you're sharing.", color: "teal",
        });
      } catch {
        // Clipboard blocked (insecure context / permissions) — show the caption
        // so the user can still select and copy it by hand.
        notifications.show({
          title: "Copy this caption", message: text, color: "blue", autoClose: false,
        });
      }
    } finally {
      setCopyingCaption(false);
    }
  };

  return (
    <Menu shadow="md" width={260} position={position} withinPortal={withinPortal}>
      <Menu.Target>
        <Button
          size={size} variant={variant}
          leftSection={<IconDownload size={iconSize} />}
          rightSection={<IconChevronDown size={iconSize} />}
          aria-label={ariaLabel}
        >
          {responsiveLabel ? (
            <>
              <Box visibleFrom="sm">Save / share</Box>
              <Box hiddenFrom="sm">Save</Box>
            </>
          ) : "Save / share"}
        </Button>
      </Menu.Target>
      {/* Measured in a real browser: a dozen items with a line of help each is
          taller than the space under a card halfway down a 900 px screen, and
          the dropdown flipped upwards and lost its first item off the top.
          Capping it scrolls instead of clipping, the same way the Gallery's
          preset menu does. */}
      <Menu.Dropdown mah={420} style={{ overflowY: "auto" }}>
        <Menu.Label>Download</Menu.Label>
        {run.has_fits ? (
          <Menu.Item leftSection={<IconPhotoDown size={16} />}
            component="a" href={api.stackFullResPngUrl(safe, run.id, northUp)}>
            Full-res PNG
            <span style={MENU_HINT}>{fullResPngHint(run.canvas_w, run.canvas_h)}</span>
          </Menu.Item>
        ) : null}
        {run.has_preview ? (
          <Menu.Item leftSection={<IconPhotoDown size={16} />}
            component="a" href={api.stackArtifactUrl(safe, run.id, "preview")}>
            PNG
            <span style={MENU_HINT}>
              {run.has_fits
                ? "Quick preview, up to 1024 px wide"
                : "The finished picture — up to 1024 px wide, the best this run has"}
            </span>
          </Menu.Item>
        ) : null}
        {run.has_preview ? (
          <Menu.Item leftSection={<IconPhotoDown size={16} />}
            component="a"
            href={api.stackArtifactUrl(safe, run.id, "jpeg", northUp, nameplate)}>
            JPEG
            <span style={MENU_HINT}>
              {northUp ? "North up — smaller, best for sharing" : "Smaller — best for sharing"}
            </span>
          </Menu.Item>
        ) : null}
        {/* The framed variant: the same picture matted on a dark card with its
            name, date and total exposure set *beneath* it, so the story travels
            with the file instead of living in a caption box that never leaves
            the app. It carries its own caption, so it ignores the nameplate
            toggle above rather than captioning the same facts twice. */}
        {run.has_preview ? (
          <Menu.Item leftSection={<IconPhotoDown size={16} />}
            component="a"
            href={api.stackArtifactUrl(safe, run.id, "jpeg", northUp, false, true)}>
            Framed keepsake
            <span style={MENU_HINT}>
              Its name, date and exposure printed on the picture
            </span>
          </Menu.Item>
        ) : null}
        {/* The two marks every published astrophoto carries — how big a piece of
            sky this is, and which way round it is. The app already draws them on
            screen, but a browser overlay doesn't travel with the file, so the
            downloaded picture loses both. Drawn from this run's own solve; a run
            that was never solved simply gets the plain picture back. */}
        {run.has_preview ? (
          <Menu.Item leftSection={<IconPhotoDown size={16} />}
            component="a"
            href={api.stackArtifactUrl(safe, run.id, "jpeg", northUp, false, false, true)}>
            With scale &amp; compass
            <span style={MENU_HINT}>
              How big it is and which way is North, printed on the picture
            </span>
          </Menu.Item>
        ) : null}
        {run.has_fits ? (
          <Menu.Item leftSection={<IconDownload size={16} />}
            component="a" href={api.stackArtifactUrl(safe, run.id, "fits")}>
            FITS
            <span style={MENU_HINT}>Raw data — for re-processing, not sharing</span>
          </Menu.Item>
        ) : null}
        {run.has_tiff ? (
          <Menu.Item leftSection={<IconDownload size={16} />}
            component="a" href={api.stackArtifactUrl(safe, run.id, "tiff")}>
            TIFF
            <span style={MENU_HINT}>{tiffDownloadHint(run.options)}</span>
          </Menu.Item>
        ) : null}
        {run.has_preview ? (
          <>
            <Menu.Divider />
            <Menu.Label>Share</Menu.Label>
            <SharePictureButton
              asMenuItem
              url={api.stackArtifactUrl(safe, run.id, "jpeg", northUp, nameplate)}
              {...shareText}
              {...(shareCaption ? { text: shareCaption } : {})}
            />
            {/* Share the *framed* variant. This is the one that matters on
                Instagram or a printed 6×4: a share-sheet caption doesn't travel
                with the file, so the plain share above arrives as an unlabelled
                rectangle while this one carries its own story. Same caption, but
                `filename` overrides the spread's so the two shares can't land on
                top of each other in downloads.

                It carries the *marks* too — the scale bar, the North/East rose
                and the names of the catalog objects in the field. Every one of
                them is a clean no-op server-side on a run that can't supply it
                (no solve, a reshaped preview, an empty field), so this never
                becomes a share that fails — it just carries less. */}
            <SharePictureButton
              asMenuItem
              label={<>
                Share the keepsake
                <span style={MENU_HINT}>
                  Framed, with its scale, which way is North, and what’s in it
                </span>
              </>}
              ariaLabel="Share the framed keepsake"
              url={api.stackArtifactUrl(
                safe, run.id, "jpeg", northUp, false, true, true, true)}
              {...shareText}
              {...(shareCaption ? { text: shareCaption } : {})}
              filename={keepsakeFilename(shareText.filename)}
            />
            {/* The QR opens in a modal owned by the page, not a popover owned by
                this item — a menu closes on click, which would unmount its own
                popover with it. */}
            <Menu.Item leftSection={<IconDeviceMobile size={16} />}
              onClick={onToPhone}>
              To phone
              <span style={MENU_HINT}>Scan a QR to open it on your phone</span>
            </Menu.Item>
            <Menu.Item
              leftSection={copyingCaption
                ? <Loader size={14} />
                : <IconClipboardText size={16} />}
              onClick={copyCaption}>
              Copy caption
              <span style={MENU_HINT}>A ready-to-post sentence about this picture</span>
            </Menu.Item>
            {/* Motion, for the places a still gets swiped past. Built and cached
                server-side from this run's own preview, so it costs no extra
                request to offer: every run with a picture has one. */}
            <DownloadMenuItem
              icon={<IconVideo size={16} />}
              url={api.stackZoomClipUrl(safe, run.id)}
              filename={`${run.output_basename || "stack"}_zoom.webp`}
              label="Zoom clip"
              hint="A few seconds gliding into your target — for posting"
              busyHint="Building your clip — a few seconds the first time"
              errorMessage="Couldn't build a zoom clip for this run."
              hintStyle={MENU_HINT}
            />
            <Menu.Divider />
            <WallpaperMenuItems safe={safe} runId={run.id} canNorthUp={canNorthUp} />
          </>
        ) : null}
      </Menu.Dropdown>
    </Menu>
  );
}
