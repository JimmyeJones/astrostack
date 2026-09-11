# AstroStack Glossary

Plain-language explanations of every term used in the AstroStack interface. The
app serves this page at **/glossary**, and every entry has its own link — so a
screen that uses a word can point straight at the word, and nobody has to leave
the app to understand something on screen.

If a term you saw isn't here, it belongs here: this list is meant to cover
everything the interface says out loud.

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

## Integration time

The total amount of light that went into a picture — the number of subs that were
stacked times how long each one was exposed. Two hours of integration means two
hours' worth of photons, however many nights that took to collect. It is the
single best predictor of how clean a picture will look.

On a **mosaic** the honest figure is smaller than the total, because the subs are
spread across the raster rather than piled on one patch of sky — see *Panel depth*.

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
all push FWHM up. AstroStack uses median FWHM as a quality score and can reject
the worst frames.

## Star count

How many stars AstroStack detected in the frame. A sudden drop is a strong cloud
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

## Seeing

How steady the air was. Turbulence high in the atmosphere smears a star into a
fuzzy blob that wanders about; the steadier the air, the tighter the star. You
can't control it — it's tonight's weather, not your equipment — and it is what
*FWHM* is mostly measuring.

## Auto-grade

AstroStack's automatic "which subs are worth keeping?" pass. It compares every
sub against the typical sub of that target and sets aside the ones that are
clearly worse — much softer stars, a much brighter sky, a big drop in star count.
It never deletes anything: a set-aside sub is still on disk and you can accept it
again with one click.

On a **mosaic** the comparison is made panel by panel, because a panel aimed at
an emptier patch of sky genuinely shows fewer, fainter stars — that's the sky,
not a bad sub.

## Plate solving

Identifying exactly where in the sky a frame is pointing — the precise RA / Dec /
rotation / scale — by matching its star pattern against a catalogue. AstroStack
uses ASTAP for this. Once a frame is plate-solved, alignment becomes a simple
coordinate transform instead of a feature-matching guess.

## ASTAP

A free, fast, local plate solver from H.N. Sky. It runs entirely on your own
machine — nothing is sent anywhere. The AstroStack container ships with ASTAP and
its star database already installed, so there is normally nothing to set up; the
Settings page tells you if it can't find it.

## WCS (World Coordinate System)

The mathematical mapping between pixel positions on a frame and sky coordinates
(RA / Dec). Plate solving produces a WCS for each frame, which AstroStack stores
in the project database.

## Alignment / registration

Shifting and rotating each frame so the stars line up with a reference frame
before stacking. With WCS-based alignment (the default in AstroStack), this is
exact and works even on frames with wildly different rotations or partial overlap.

## Reprojection

Resampling a frame from its own pixel grid onto a target pixel grid (the output
canvas) using the WCS. This is how aligned frames get into the stack accumulator.

## Dithering

Nudging the telescope by a few pixels between subs, so a given sensor defect
lands on a different part of the sky each time. It means fixed patterns (hot
pixels, sensor rows) average away instead of printing themselves into the stack,
and it is what makes *Drizzle* possible. The Seestar dithers naturally, because
its tracking wanders slightly.

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

## Min/max rejection

The simpler cousin of sigma clipping, for when a pixel has only a handful of subs
on it: throw away the brightest and darkest few values per pixel and average the
rest. It needs fewer frames to be safe, but it can only ever remove a fixed
number of outliers per pixel — and below three subs on a pixel there is no
brightest and darkest it can spare, so such a pixel isn't protected at all. Turn
on **Auto outlier removal** and AstroStack picks between the two from how deep
your subs actually are; the finished picture's health notes say which it used and
what it could reach.

## Coverage map / weight map

A 2D map, the same size as the output, that records how many frames contributed
to each output pixel. Critical for mosaics and partial-overlap stacks: dividing
the sum by the coverage map (instead of the frame count) keeps brightness
consistent everywhere, with no bright patches where more frames overlap.

## Panel depth

On a **mosaic**, how many subs one *pixel* of the finished picture actually got —
as opposed to how many subs the target has in total. Nine subs over a 3×3 raster
is one sub everywhere, not nine. Almost everything the app tells you about a
picture (how clean it will look, whether more time still pays, whether rejection
could work) is a claim about a pixel, so this is the number those sentences use.
On a single field the two are the same, because every sub covers the whole frame.

## Background flattening / gradient removal

Real frames usually have a sky-glow gradient — the sky is brighter on one side of
the frame than the other (light pollution, moonglow, even airglow at dark sites).
AstroStack fits a low-order surface to the sky background of each frame and
subtracts it before stacking, so gradients don't accumulate into the final image.

## Streak rejection

Detecting frames that contain satellite trails, aircraft lights, or meteors so
they can be excluded or down-weighted. AstroStack uses two layers: a per-frame
streak detector that flags whole frames, and pixel-level rejection during
stacking that catches what slips through.

## Stretching

The final image off the stacker is linear — faint things look invisible because
the bright stars span most of the brightness range. Stretching applies a
non-linear curve (asinh or screen-transfer-function) to compress bright parts and
reveal faint detail. This is purely cosmetic — it doesn't change the underlying
data.

## Linear / display-space

A **linear** image still holds the raw brightness numbers the sensor measured, in
proportion — which is what you want for measuring and for editing, and which
looks almost black on screen. A **display-space** image has had a stretch baked
in so it looks the way you want it to look. AstroStack keeps the linear master
and applies your edits on top of it, so nothing is ever baked in irreversibly.

## Recipe / non-destructive editing

The list of adjustments you've made in the editor — stretch, colour, denoise,
crop and so on — saved as a *recipe* rather than as changed pixels. The stacked
master is never overwritten: every preview and every export re-applies the recipe
to the original data, so any step can be changed or removed later, in any order.

## Colour calibration

Setting the white balance from the actual colours of stars in the image rather
than guessing from sky averages: AstroStack finds stars that ought to be neutral
and balances the channels until they are. It runs entirely offline on your own
data. This is one of the things that separates an amateur stack from a good one.

## SCNR (green cast removal)

One-shot-colour sensors have twice as many green pixels as red or blue, so a
stretched stack often ends up with a faint green cast in the sky. SCNR gently
pulls green pixels back toward the average of red and blue where green is
clearly winning — which removes the cast without draining the colour out of
genuinely green things. It's part of the one-click Auto edit.

## Master dark / flat / bias

Calibration frames, each built by stacking many shots of one thing:

- a **dark** is shot with the lens capped, at the same exposure and temperature
  as your subs, and records the sensor's own glow and hot pixels;
- a **flat** is shot against an evenly lit surface and records dust shadows and
  the corners being dimmer than the middle;
- a **bias** is the shortest possible exposure and records the sensor's read-out
  offset.

Subtracting a dark and dividing by a flat removes those fixed patterns before
stacking. They are optional — a Seestar stack is perfectly good without them —
but they clean up gradients and speckle that no amount of extra subs will.

## Hot pixel

A single sensor pixel that reads much brighter than its neighbours regardless of
what it's pointed at. Because the scope dithers, it lands on a different part of
the sky in each sub, so it never lines up with itself when the frames are aligned
— which is how rejection and calibration between them mostly erase it. The editor
has a cleanup step for whatever survives.

## Noise σ (sigma)

The app's one-number answer to "how grainy is this picture?" — the typical
pixel-to-pixel wobble in an empty patch of sky, measured on the finished stack.
Lower is cleaner. It's useful mainly as a *comparison*: the same target stacked
with twice the integration should measure noticeably lower.

## Mosaic

A panorama of the sky built from multiple panels, each itself a stack. The
Seestar app supports mosaic capture mode. AstroStack auto-detects mosaic frames
from their sky positions and builds the seamless joined output using the coverage
map.

## Mean vs. median stacking

**Mean** averages all surviving values per pixel. **Median** picks the middle
value. Median naturally rejects outliers but is much slower and doesn't scale
well past a few thousand frames. AstroStack uses sigma-clipped mean by default,
which gives median-like outlier rejection at much lower cost.

## Auto-stack / walk-away

Leave the app running and it will do the whole chain by itself as frames arrive —
bring them in, measure them, locate them, and stack them — so you can go to bed
and find a finished picture. It waits until a night has stopped growing before
stacking, won't publish a result thinner than the one you already have, and never
touches your raw files. Turn it on in Settings.

## Cache (Stage 1 / Stage 2)

Stage 1 is an optional local copy of your raw frames, so the pipeline doesn't
re-read them across the network on every pass. Stage 2 is the aligned, warped
version written during a stack so the second pass doesn't have to redo the
alignment. Both are working files: you can clear either from the **Storage**
page, and nothing is lost — your originals and your project database are
untouched, the work is simply redone next time.

## Incoming folder

The folder AstroStack watches for new subs. It is **read-only** to the app: it
reads your frames where they are and never writes, moves, renames or deletes
anything inside it. That also means the app keeps no copy of its own unless
Stage 1 caching is on — so the subs in there are the only copy there is, and are
worth backing up somewhere else.
