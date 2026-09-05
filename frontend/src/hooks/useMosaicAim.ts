import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { MosaicDepthMap } from "../api/client";

/** How long a fetched map stays fresh. A panel's depth changes when a night's
 *  worth of subs lands, not minute to minute, so this only needs to be short
 *  enough that a scan during the session is picked up. */
export const MOSAIC_AIM_STALE_MS = 10 * 60 * 1000;

/** The "…and here's the corner to aim at" clause for one target, or null (pure).
 *
 * A "worth more time" recommendation answers *which target*. On a mosaic that is
 * half the question: a 3×3 whose total looks healthy can still have one corner
 * at a fifth of the others, and pointing at the mosaic again spreads the night
 * evenly over panels that don't need it equally. The §1 owner is a heavy mosaic
 * user, so this is their common case, not an edge one.
 *
 * The sentence comes from the backend (`seestack.mosaicmap.aim_hint`) and is
 * never rebuilt here: "thinnest at the bottom-right" and "about 40 min" are the
 * app's shared vocabulary for where a panel sits and how long an integration is,
 * and a second spelling per surface is how two screens end up naming different
 * corners. So a backend too old to send the clause shows nothing rather than a
 * locally invented one — the same silence as a single-field target (no map at
 * all) or an even mosaic (a map with nothing to point at).
 */
export function mosaicAimLine(map: MosaicDepthMap | null | undefined): string | null {
  const hint = map?.aim_hint;
  return typeof hint === "string" && hint.trim() ? hint : null;
}

/**
 * The aim clause for the target a card is actually recommending, or null.
 *
 * Shared by both "worth more time" surfaces — the Dashboard's "Point here right
 * now" card and the Tonight page's list — so the two cannot drift on any of the
 * three decisions that matter: they read the *same* cache entry as the Target
 * page's own map card (`["mosaic-map", safe]`), so no surface costs a second
 * request and none can quote a different panel; they ask only for the **lead**
 * pick, because annotating rows nobody is being told to shoot is a project read
 * with no reader; and they treat a rejected request as silence, because an older
 * backend 404s the endpoint and that is a quiet no-op, not an error to retry.
 *
 * Pass `null`/`undefined` when there is nothing to recommend and no request is
 * made at all.
 */
export function useMosaicAim(safe: string | null | undefined): string | null {
  const q = useQuery({
    queryKey: ["mosaic-map", safe ?? null],
    queryFn: () => api.mosaicMap(safe as string),
    enabled: !!safe,
    staleTime: MOSAIC_AIM_STALE_MS,
    retry: false,
  });
  return mosaicAimLine(q.data);
}
