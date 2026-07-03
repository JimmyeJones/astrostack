// Pure helper: the "your data" context chip shown in the editor header.
//
// The four data-driven suggestion buttons each quote a measured value inline
// ("FWHM 3.2px"), but there's no single place a user sees what the editor
// measured about *this* stack. A small dimmed chip near the title gives the
// data-driven buttons visible provenance and builds trust — it's shown only when
// at least one measure is available.

export interface MeasuredInputs {
  // Median star FWHM in px. The psf/sharpen/star-size suggestion queries all
  // carry it (it's the same QC measure); any non-null one is used.
  fwhm_px?: number | null;
  // Normalized background-noise σ from the denoise suggestion query.
  noise_sigma?: number | null;
}

// Coalesce a FWHM value from the several suggestion queries that expose one, so
// the caller can pass them in any order and the first finite one wins.
export function coalesceFwhm(
  ...values: (number | null | undefined)[]
): number | null {
  for (const v of values) {
    if (typeof v === "number" && Number.isFinite(v) && v > 0) return v;
  }
  return null;
}

// Builds the chip text, e.g.
//   "Measured: stars ≈ 3.2 px FWHM · background noise σ 0.021"
// Returns null when nothing was measured, so the chip is simply omitted rather
// than showing an empty "Measured:" label.
export function measuredContextText(m: MeasuredInputs): string | null {
  const parts: string[] = [];
  if (typeof m.fwhm_px === "number" && Number.isFinite(m.fwhm_px) && m.fwhm_px > 0) {
    parts.push(`stars ≈ ${m.fwhm_px.toFixed(1)} px FWHM`);
  }
  if (
    typeof m.noise_sigma === "number" &&
    Number.isFinite(m.noise_sigma) &&
    m.noise_sigma >= 0
  ) {
    parts.push(`background noise σ ${m.noise_sigma.toFixed(3)}`);
  }
  if (parts.length === 0) return null;
  return `Measured: ${parts.join(" · ")}`;
}
