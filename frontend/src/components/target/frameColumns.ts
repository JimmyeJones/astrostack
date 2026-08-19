/** The frames table's columns, and the plain-language explanation of each.
 *
 * These lived inside `Target.tsx` as the `cols` array behind the header
 * tooltips. They are lifted out for one reason: **a tooltip is invisible on a
 * phone.** Mantine's `Tooltip` opens on hover or focus, and a tap on a sortable
 * header sorts — so on the device the owner actually reads this app on, the only
 * explanation of `FWHM`, `Ecc.`, `Sky` and `Transp.` was, in practice, not
 * written at all. The `FrameColumnGuide` disclosure renders the same strings as
 * readable text.
 *
 * Sharing one array is the point: the tooltip and the guide can't drift into two
 * different explanations of the same column, and a column added later gets its
 * entry in both surfaces or in neither.
 */

export type SortKey =
  | "id" | "timestamp_utc" | "fwhm_px" | "star_count"
  | "eccentricity_median" | "sky_adu_median" | "transparency_score";

export interface FrameColumn {
  key: SortKey;
  label: string;
  /** Absent for a column that explains itself (the capture time). */
  hint?: string;
}

export const FRAME_COLUMNS: FrameColumn[] = [
  { key: "timestamp_utc", label: "Time (UTC)" },
  {
    key: "fwhm_px", label: "FWHM",
    hint: "Full-width-half-maximum: how many pixels wide the stars are. "
      + "Lower = sharper. Rises with poor seeing, focus drift or clouds.",
  },
  {
    key: "star_count", label: "Stars",
    hint: "Number of stars detected in the frame. Drops on hazy or "
      + "cloud-affected subs. Higher is generally better.",
  },
  {
    key: "eccentricity_median", label: "Ecc.",
    hint: "Median star eccentricity (elongation): 0 = perfectly round, "
      + "closer to 1 = trailed. High values flag tracking error, wind or a "
      + "mount bump on that whole sub. Lower is better.",
  },
  {
    key: "sky_adu_median", label: "Sky",
    hint: "Median sky-background level of the frame. Rises with moonlight, "
      + "light pollution or thin cloud. Lower is darker (better).",
  },
  {
    key: "transparency_score", label: "Transp.",
    hint: "Transparency: median brightness of the frame's brightest stars. "
      + "Higher = clearer sky; low values flag haze or thin cloud. Relative, "
      + "comparable across this target's frames.",
  },
];
