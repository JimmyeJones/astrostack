# Seestack Glossary

Plain-language explanations of every term used in the Seestack interface. The GUI
links into this file from the "Why?" panels next to each option.

If a term you saw isn't here, file an issue — the goal is that nobody has to leave
the app to understand any setting.

---

## Sub / sub-frame / light frame

One single exposure from the telescope. A Seestar typically takes 10-second subs.
A "stack" is what you get when you average many subs together to reduce noise and
reveal faint detail.

## Stacking

Combining many sub-frames into one final image. Because random noise differs
frame-to-frame but the actual signal (stars, nebulosity) is consistent, averaging
makes the signal stand out and the noise fade. Doubling the number of frames
roughly improves the signal-to-noise ratio by √2.

## FITS (`.fit` / `.fits`)

The standard astronomy image file format. Seestar raw subs are FITS files. Unlike
JPEG, they store the full sensor data with no compression loss, which is what you
want for stacking.

## Bayer pattern / debayering

Color cameras like the Seestar's use a colour filter grid (red, green, green,
blue) over a monochrome sensor — each pixel actually only captures one colour.
*Debayering* reconstructs the missing two colours per pixel by interpolating from
neighbours. The Seestar uses an **RGGB** pattern.

## FWHM (full width at half maximum)

A measure of how sharp a star looks. Smaller is sharper. It's the diameter, in
pixels, of a star at half its peak brightness. Bad seeing, focus drift, or wind
all push FWHM up. Seestack uses median FWHM as a quality score and rejects the
worst frames.

## Star count

How many stars Seestack detected in the frame. A sudden drop is a strong cloud
signal — it doesn't matter what the camera was pointed at, if half the stars
disappeared it was clouded over.

## Sky background / sky ADU

How bright the empty sky is in the frame, measured in ADU (analog-to-digital
units — the camera's raw pixel values). High sky background means light pollution,
moonlight, or thin clouds. Frames with much higher background than the rest of
the session are usually worth rejecting.

## Eccentricity

How round vs. elongated stars are, on average. Round stars (eccentricity near 0)
mean good tracking. Elongated stars (eccentricity near 1) mean tracking errors,
wind, or a polar alignment drift. High eccentricity is reason to reject.

## Transparency

How clear the atmosphere was, derived from the brightness of the brightest matched
stars compared to a reference frame. Lower transparency = haze, thin cloud,
moisture.

## Plate solving

Identifying exactly where in the sky a frame is pointing — the precise RA / Dec /
rotation / scale — by matching its star pattern against a catalogue. Seestack
uses ASTAP for this. Once a frame is plate-solved, alignment becomes a simple
coordinate transform instead of a feature-matching guess.

## ASTAP

A free, fast, local plate solver from H.N. Sky. Seestack requires it to be
installed; download from https://www.hnsky.org/astap.htm and install the H17 (or
larger) star database alongside it.

## WCS (World Coordinate System)

The mathematical mapping between pixel positions on a frame and sky coordinates
(RA / Dec). Plate solving produces a WCS for each frame, which Seestack stores
in the project database.

## Alignment / registration

Shifting and rotating each frame so the stars line up with a reference frame
before stacking. With WCS-based alignment (the default in Seestack), this is
exact and works even on frames with wildly different rotations or partial overlap.

## Reprojection

Resampling a frame from its own pixel grid onto a target pixel grid (the output
canvas) using the WCS. This is how aligned frames get into the stack accumulator.

## Drizzle

An advanced stacking method (originally developed for the Hubble Space Telescope)
that can produce a higher-resolution output than the input frames, *if* the
frames are slightly offset from each other ("dithered"). The Seestar dithers
naturally because of small tracking variations. Drizzle is more compute-heavy and
only helps if you have lots of frames — typical recommendation: enable it once
you have 200+ aligned frames.

## Sigma clipping

A pixel-rejection method during stacking. For each output pixel, look at all the
input frames' values for that pixel: compute mean and standard deviation, then
discard values more than k standard deviations from the mean (k is "sigma" or
"kappa"). This is what removes satellite trails, aircraft, cosmic ray hits, and
other one-frame outliers without you having to find them by hand. Lower sigma =
more aggressive rejection. Typical: 2.5 to 3.5.

## Coverage map / weight map

A 2D map, the same size as the output, that records how many frames contributed
to each output pixel. Critical for mosaics and partial-overlap stacks: dividing
the sum by the coverage map (instead of the frame count) keeps brightness
consistent everywhere, with no bright patches where more frames overlap.

## Background flattening / gradient removal

Real frames usually have a sky-glow gradient — the sky is brighter on one side of
the frame than the other (light pollution, moonglow, even airglow at dark sites).
Seestack fits a low-order surface to the sky background of each frame and
subtracts it before stacking, so gradients don't accumulate into the final image.

## Streak rejection

Detecting frames that contain satellite trails, aircraft lights, or meteors so
they can be excluded or down-weighted. Seestack uses two layers: a per-frame
streak detector (`astride`) that flags whole frames, and pixel-level sigma
clipping during stacking that catches what slips through.

## Stretching

The final image off the stacker is linear — faint things look invisible because
the bright stars span most of the brightness range. Stretching applies a
non-linear curve (asinh or screen-transfer-function) to compress bright parts and
reveal faint detail. This is purely cosmetic — it doesn't change the underlying
data.

## Photometric color calibration

Setting the white balance based on the actual colours of stars in the image
(measured against the Gaia star catalog), instead of guessing from sky averages.
This produces scientifically defensible colours and is one of the things that
separates amateur stacks from "good" stacks.

## Mosaic

A panorama of the sky built from multiple panels, each itself a stack. The
Seestar app supports mosaic capture mode. Seestack auto-detects mosaic frames
from their sky positions and builds the seamless joined output using the coverage
map.

## Mean vs. median stacking

**Mean** averages all surviving values per pixel. **Median** picks the middle
value. Median naturally rejects outliers but is much slower and doesn't scale
well past a few thousand frames. Seestack uses sigma-clipped mean by default,
which gives median-like outlier rejection at much lower cost.

## Cache (Stage 1 / Stage 2)

Seestack copies your raw frames from the NAS to local disk (Stage 1) so the
pipeline doesn't re-read them over the network on every pass. After alignment, a
warped float16 version is written (Stage 2) so the second pass of sigma clipping
doesn't have to redo alignment. You can clear either cache from the GUI; the
project database is unaffected.

## Conservative / Balanced / Aggressive presets

- **Conservative** keeps almost everything, rejects only obvious failures. Use
  if you have few frames and want maximum integration time.
- **Balanced** is the default and what most users want.
- **Aggressive** rejects more frames in the name of sharpness. Use if you have
  thousands of frames and can afford to throw the worst quarter away.
