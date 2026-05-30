import { useEffect, useRef, useState } from "react";
import { Alert, Center, Loader, Stack, Text } from "@mantine/core";
import { sortOldestFirst, type SkyImage } from "../sky/projection";

// Real-sky background (CDS HiPS). Needs the browser to reach the internet.
const SURVEY = "P/DSS2/color";

/**
 * "Real sky" viewer backed by Aladin Lite (CDS). Renders a true sky atlas and
 * overlays each stacked image at its plate-solved WCS, oldest-added-first so the
 * newest sits on top of overlaps. Requires internet (for the sky tiles) and
 * WebGL2; on failure it surfaces a message and the user can switch to the
 * offline star viewer.
 */
export function AladinSky({ images }: { images: SkyImage[] }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    let cancelled = false;
    const host = hostRef.current;

    (async () => {
      try {
        const A = (await import("aladin-lite")).default;
        await A.init; // throws if WebGL2 is unavailable
        if (cancelled || !host) return;

        const ordered = sortOldestFirst(images);
        const focus = ordered[ordered.length - 1]; // newest → center here
        const aladin = A.aladin(host, {
          survey: SURVEY,
          cooFrame: "ICRS",
          fov: focus ? Math.max(focus.width_deg * 6, 1.5) : 60,
          target: focus ? `${focus.ra_deg} ${focus.dec_deg}` : "0 +0",
          showReticle: false,
          showZoomControl: true,
          showFullscreenControl: true,
          showLayersControl: false,
          showGotoControl: false,
          showSimbadPointerControl: false,
          showCooGrid: false,
        });

        // Oldest first → newest added last → drawn on top of overlapping fields.
        for (const im of ordered) {
          if (!im.wcs) continue;
          const layerName = `${im.safe}-${im.run_id}`;
          const layer = A.image(im.preview_url, {
            name: layerName,
            wcs: im.wcs,
            successCallback: () => {},
            errorCallback: () => {},
          });
          aladin.setOverlayImageLayer(layer, layerName);
        }
        if (!cancelled) setStatus("ready");
      } catch (e) {
        if (!cancelled) {
          setErrorMsg(e instanceof Error ? e.message : String(e));
          setStatus("error");
        }
      }
    })();

    return () => {
      cancelled = true;
      if (host) host.innerHTML = ""; // Aladin has no clean destroy; clear the node
    };
  }, [images]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={hostRef} style={{ width: "100%", height: "100%" }} />
      {status === "loading" ? (
        <Center style={{ position: "absolute", inset: 0 }}>
          <Stack align="center" gap={6}>
            <Loader />
            <Text size="sm" c="dimmed">Loading real-sky atlas…</Text>
          </Stack>
        </Center>
      ) : null}
      {status === "error" ? (
        <Center style={{ position: "absolute", inset: 0, padding: 24 }}>
          <Alert color="yellow" title="Couldn’t load the real-sky atlas" maw={460}>
            <Text size="sm">
              The online sky map needs internet access (and WebGL2) in your browser.
              Switch to <b>Stars (offline)</b> above to use the built-in viewer.
            </Text>
            {errorMsg ? <Text size="xs" c="dimmed" mt={6}>{errorMsg}</Text> : null}
          </Alert>
        </Center>
      ) : null}
    </div>
  );
}
