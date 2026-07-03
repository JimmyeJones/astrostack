import { Badge, Tooltip } from "@mantine/core";

// A stack records which calibration masters were actually applied to its lights
// as a compact "calstat" string ("dark+flat", "bias+flat", "flat", …). This
// mirrors the CALSTAT FITS card the engine stamps, but comes from the run
// record so a card can show it without re-reading the FITS.

// Turn "dark+flat" into a friendly one-liner for the tooltip.
export function calibrationLabel(calstat?: string | null): string | null {
  if (!calstat) return null;
  const names: Record<string, string> = {
    dark: "master dark",
    bias: "master bias",
    flat: "master flat",
  };
  const parts = calstat.split("+").map((p) => names[p] ?? p);
  if (parts.length === 0) return null;
  if (parts.length === 1) return parts[0];
  return parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
}

// Small green "dark+flat" chip for History / Gallery cards. Renders nothing when
// the run was uncalibrated (calstat null/empty) or recorded before the column
// existed, so it's safe to drop in unconditionally.
export function CalibrationBadge({
  calstat,
  size = "xs",
}: {
  calstat?: string | null;
  size?: string;
}) {
  const label = calibrationLabel(calstat);
  if (!label) return null;
  return (
    <Tooltip
      label={`Calibrated with a ${label} — this stack had its calibration masters applied.`}
      multiline
      w={260}
    >
      <Badge color="teal" variant="light" size={size}>
        {calstat}
      </Badge>
    </Tooltip>
  );
}
