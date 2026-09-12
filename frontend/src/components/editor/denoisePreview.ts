// Pure helper: caption for "the noise-reduction preview leaves more grain than
// the export will".
//
// Noise reduction's *bilateral* method averages each pixel over a patch measured
// in full-resolution pixels, which `_denoise` correctly shrinks by proxy_scale on
// the decimated live preview so both resolutions smooth the same physical patch.
// That matches the patch and not the result: decimation is a stride rather than
// an average, so the proxy carries the full-resolution grain at full amplitude
// while the matched window reaches far fewer samples to average it with — the
// export's 2.0 px sigma gathers ~25 pixels, a step-4 proxy's 0.5 px sigma ~1.5.
// Measured at up to 2x the export's remaining grain at the strengths and mosaic
// proxy steps this owner reaches (see `_BILATERAL_ADVISORY_RATIO`).
//
// The direction is the dangerous one, which is why it is worth a sentence: a user
// who cannot see the smoothing the export will apply raises the strength until
// the preview looks clean, and saves a picture smoothed about twice as hard as
// the one they judged. Wavelet (the default) and total-variation agree with their
// export to within 3 % at every proxy step, so the backend never flags them.
// Advisory only — the backend sets `denoise_preview_understates` on the
// histogram, and nothing about the render changes.

export interface DenoisePreviewInfo {
  denoise_preview_understates?: boolean;
}

// Returns the caption string when the current preview understates the denoise, or
// null otherwise (no denoise op, another method, or a proxy fine enough to match).
export function denoiseUnderstatesCaption(
  info: DenoisePreviewInfo | undefined | null,
): string | null {
  if (!info || !info.denoise_preview_understates) return null;
  return (
    "Bilateral noise reduction previews weaker than it exports — at this size "
    + "the downscaled preview can't smooth the grain as thoroughly as the "
    + "full-resolution export will, so the saved picture comes out smoother than "
    + "this. Don't raise the strength to make the preview look clean. Wavelet "
    + "previews exactly what it saves, at any size."
  );
}
