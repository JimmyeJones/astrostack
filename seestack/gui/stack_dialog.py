"""
Stack options dialog.

Opens before a stack run. Exposes the user-facing knobs from
``StackOptions`` with plain-language labels and a "Why?" expandable for each.
Presets at the top map to common combinations:

  - **Conservative** : sigma=3.5, keeps almost everything.
  - **Balanced**     : sigma=3.0 (default).
  - **Aggressive**   : sigma=2.5, throws away anything noisy.
  - **No clipping**  : just a weighted mean. Fast, but doesn't reject streaks.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from PySide6.QtWidgets import QInputDialog, QMessageBox

from seestack.core.xp import GPU_AVAILABLE, device_summary
from seestack.gui.templates import (
    delete_template, list_templates, load_template, save_template,
)
from seestack.stack.stacker import StackOptions

PRESETS = {
    "Balanced (recommended)": dict(sigma_clip=True, sigma_kappa=3.0),
    "Conservative (keeps more)": dict(sigma_clip=True, sigma_kappa=3.5),
    "Aggressive (rejects more)": dict(sigma_clip=True, sigma_kappa=2.5),
    "No clipping (weighted mean)": dict(sigma_clip=False, sigma_kappa=3.0),
}


class StackOptionsDialog(QDialog):
    """Configure a stack run."""

    def __init__(self, parent=None, n_frames: int = 0, default_name: str = "master") -> None:
        super().__init__(parent)
        self.setWindowTitle("Stack")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"<b>{n_frames}</b> accepted, plate-solved frames will be stacked."
        ))

        form = QFormLayout()

        # Preset
        self._preset_combo = QComboBox()
        for name in PRESETS:
            self._preset_combo.addItem(name)
        self._preset_combo.currentIndexChanged.connect(self._apply_preset)
        form.addRow("Preset:", self._preset_combo)

        # User-saved templates
        template_row = QHBoxLayout()
        self._template_combo = QComboBox()
        self._refresh_template_list()
        self._template_combo.setToolTip(
            "User-saved templates. Save the current settings with the button "
            "to the right; load any saved template with this dropdown."
        )
        self._template_combo.currentIndexChanged.connect(self._on_load_template)
        save_btn = QPushButton("Save…")
        save_btn.setToolTip("Save current options as a named template.")
        save_btn.clicked.connect(self._on_save_template)
        del_btn = QPushButton("Delete")
        del_btn.setToolTip("Delete the currently-selected template.")
        del_btn.clicked.connect(self._on_delete_template)
        template_row.addWidget(self._template_combo, 1)
        template_row.addWidget(save_btn)
        template_row.addWidget(del_btn)
        form.addRow("Templates:", template_row)

        # Sigma clipping toggle
        self._sigma_toggle = QCheckBox("Enable sigma clipping (recommended)")
        self._sigma_toggle.setChecked(True)
        self._sigma_toggle.setToolTip(
            "Sigma clipping rejects outlier pixels per location during stacking. "
            "It removes satellite trails, aircraft, cosmic rays, and other "
            "single-frame artefacts that would otherwise leak into the output."
        )
        self._sigma_toggle.toggled.connect(self._on_sigma_toggle)
        form.addRow("", self._sigma_toggle)

        # Sigma kappa
        self._sigma_kappa = QDoubleSpinBox()
        self._sigma_kappa.setRange(1.5, 5.0)
        self._sigma_kappa.setSingleStep(0.1)
        self._sigma_kappa.setValue(3.0)
        self._sigma_kappa.setToolTip(
            "How aggressive the clipping is, in standard deviations. Lower "
            "values reject more pixels (good for noisy data with lots of "
            "satellites), higher values keep more (good when you have few "
            "frames). Typical: 2.5–3.5."
        )
        form.addRow("Sigma (κ):", self._sigma_kappa)

        # Drizzle
        self._drizzle = QCheckBox("Drizzle (super-resolution)")
        self._drizzle.setChecked(False)
        self._drizzle.setToolTip(
            "<b>Drizzle</b> is the algorithm Hubble uses for stacking dithered "
            "frames. Each input pixel is dropped onto the output canvas as a "
            "smaller footprint (controlled by pixfrac), and an output canvas "
            "finer than the input recovers detail beyond the input's pixel "
            "scale.\n\n"
            "<b>When to enable:</b> 200+ frames AND you want extra resolution. "
            "The Seestar's natural tracking jitter provides plenty of dither.\n\n"
            "<b>Trade-offs:</b> slower than the standard path; CPU-only "
            "(no GPU); and incompatible with sigma-clipping (drizzle is one-pass). "
            "Frame-level streak rejection (the QC step) still applies."
        )
        self._drizzle.toggled.connect(self._on_drizzle_toggle)
        form.addRow("", self._drizzle)

        self._drizzle_pixfrac = QDoubleSpinBox()
        self._drizzle_pixfrac.setRange(0.1, 1.0)
        self._drizzle_pixfrac.setSingleStep(0.05)
        self._drizzle_pixfrac.setValue(0.8)
        self._drizzle_pixfrac.setToolTip(
            "Drop size relative to one input pixel. Smaller = sharper output "
            "but noisier; larger = smoother but less resolved. 0.7–0.8 is a "
            "common compromise."
        )
        form.addRow("Pixfrac:", self._drizzle_pixfrac)

        self._drizzle_scale = QDoubleSpinBox()
        self._drizzle_scale.setRange(1.0, 4.0)
        self._drizzle_scale.setSingleStep(0.25)
        self._drizzle_scale.setValue(1.5)
        self._drizzle_scale.setToolTip(
            "Output pixel scale, in units of input pixels. 1.0 = same size as "
            "the reference frame. 1.5 = 1.5× more pixels per side (≈2.25× area, "
            "with sharper detail if your data is dithered well). 2.0 = full "
            "super-res; only worth it with hundreds of frames."
        )
        form.addRow("Output scale:", self._drizzle_scale)

        # Output canvas / mosaic
        self._mosaic_canvas = QComboBox()
        self._mosaic_canvas.addItem("Auto — union canvas for mosaics", userData="auto")
        self._mosaic_canvas.addItem("Always union of all footprints", userData="union")
        self._mosaic_canvas.addItem("Reference frame only (crop)", userData="reference")
        self._mosaic_canvas.setToolTip(
            "<b>How big the output image is.</b><br><br>"
            "<b>Auto</b> (recommended): when your frames span more than one "
            "Seestar field — i.e. you shot a mosaic — the output canvas is "
            "the union of every frame's footprint, so all panels land "
            "side-by-side. For a normal single-target stack it just uses the "
            "reference frame's footprint.<br><br>"
            "<b>Always union</b>: force the union canvas even for single-target "
            "stacks (handy if dithering pushed some frames past the edge and "
            "you don't want any cropping).<br><br>"
            "<b>Reference frame only</b>: crop everything to the reference "
            "frame — the old behaviour. Mosaics will NOT stitch correctly "
            "with this setting."
        )
        form.addRow("Output canvas:", self._mosaic_canvas)

        # Background flatten
        self._bg_mode = QComboBox()
        self._bg_mode.addItem("Per-channel — star fields, galaxies (default)", userData="per_channel")
        self._bg_mode.addItem("Luminance-linked — moderate emission nebulas", userData="luminance")
        self._bg_mode.addItem("Off — ONLY for huge nebulas (M42 core, Lagoon)", userData="off")
        self._bg_mode.setToolTip(
            "<b>How to remove the sky gradient from each frame before stacking. "
            "Leave this ON for almost everything — including any mosaic.</b>"
            "<br><br>"
            "<b>Per-channel</b> (default) fits separate R/G/B models. Best for "
            "star fields and small targets where most of the frame is sky. "
            "<b>Required for mosaics</b> — without it, every frame keeps its "
            "native sky level and you'll see step changes at every frame "
            "boundary in the stacked output.<br><br>"
            "<b>Luminance-linked</b> fits ONE gradient model from the brightness "
            "channel and subtracts the same shape from R/G/B. Use for emission "
            "nebulas where per-channel mode would create cyan/red colour "
            "artefacts in the bright regions.<br><br>"
            "<b>Off</b> is ONLY right when your target genuinely fills almost "
            "the whole frame (M42 core, Lagoon Nebula, etc.) — any tile-based "
            "fit would eat the object. For everything else (mosaics, "
            "star fields, faint diffuse backgrounds) this setting will "
            "introduce visible frame-boundary steps."
        )
        form.addRow("Sky gradient removal:", self._bg_mode)

        self._bg_box_size = QSpinBox()
        self._bg_box_size.setRange(16, 512)
        self._bg_box_size.setValue(128)
        self._bg_box_size.setSingleStep(16)
        self._bg_box_size.setToolTip(
            "Tile size in pixels for the sky-sample grid. Each tile must be "
            "*smaller* than the gradient features you want to remove, but "
            "*larger* than the brightest non-sky structure you want to keep. "
            "128 is a good default. Increase to 256+ for extended targets."
        )
        form.addRow("Background tile size:", self._bg_box_size)

        # GPU
        self._gpu_combo = QComboBox()
        self._gpu_combo.addItem("Auto (use GPU if available)", userData=None)
        self._gpu_combo.addItem("Force CPU", userData=False)
        self._gpu_combo.addItem("Force GPU", userData=True)
        gpu_status = device_summary()
        if not GPU_AVAILABLE:
            self._gpu_combo.setEnabled(False)
            self._gpu_combo.setToolTip(
                f"Active backend: {gpu_status}\n\n"
                "GPU acceleration requires CuPy (CUDA) and an NVIDIA card.\n"
                "Install with: pip install cupy-cuda12x"
            )
        else:
            self._gpu_combo.setToolTip(
                f"Active backend: {gpu_status}\n\n"
                "Auto: use GPU when frames are large enough to be worth the "
                "host↔device transfer (typical for full Seestar frames)."
            )
        form.addRow("Compute:", self._gpu_combo)

        # Workers
        import os as _os
        self._workers = QSpinBox()
        self._workers.setRange(1, 64)
        self._workers.setValue(max(1, (_os.cpu_count() or 4)))
        self._workers.setToolTip(
            "Number of parallel worker threads. Default is your CPU core count. "
            "Lower it if your machine becomes unresponsive during stacking."
        )
        form.addRow("Worker threads:", self._workers)

        # Output name
        self._name = QLineEdit(default_name)
        self._name.setToolTip(
            "Base name for output files (master.fits, master.tif, etc.). "
            "Existing files with the same name are renamed with a timestamp."
        )
        form.addRow("Output name:", self._name)

        # ---- Advanced options ----
        # Hot pixel suppression
        self._hot_pixel = QCheckBox("Suppress hot / cold pixels")
        self._hot_pixel.setChecked(True)
        self._hot_pixel.setToolTip(
            "Per-frame median-residual filter that catches CCD defects and "
            "single-frame transients (cosmic rays) that survive sigma-clip. "
            "Cheap (~10 ms/frame). Almost always worth leaving on."
        )
        form.addRow("", self._hot_pixel)

        # Quality weighting
        self._quality_weight = QCheckBox("Weight frames by quality")
        self._quality_weight.setChecked(False)
        self._quality_weight.setToolTip(
            "Each frame's contribution scales with its FWHM, star count, and "
            "sky background. Better frames pull harder; worse frames still "
            "contribute, just less. Improves SNR-per-time when frame quality "
            "varies through the night."
        )
        form.addRow("", self._quality_weight)

        # Lucky imaging
        self._lucky_fraction = QDoubleSpinBox()
        self._lucky_fraction.setRange(0.05, 1.0)
        self._lucky_fraction.setSingleStep(0.05)
        self._lucky_fraction.setValue(1.0)
        self._lucky_fraction.setSuffix(" of frames kept")
        self._lucky_fraction.setToolTip(
            "Lucky imaging: keep only the sharpest fraction of frames (by "
            "FWHM). 1.0 = use everything (default). 0.5 = top half. 0.2 = "
            "top 20% — only for unusually steady atmospheric conditions."
        )
        form.addRow("Lucky imaging:", self._lucky_fraction)

        # Sub-pixel refine
        self._subpixel = QCheckBox("Sub-pixel alignment refinement")
        self._subpixel.setChecked(False)
        self._subpixel.setToolTip(
            "After WCS reproject, do a final centroid-based shift per frame "
            "via phase correlation against the reference. Tightens alignment "
            "from ~0.3 px to ~0.05 px. Adds ~50 ms/frame; mostly visible at "
            "high drizzle scales or with already-sharp data."
        )
        form.addRow("", self._subpixel)

        # Final gradient removal
        self._final_grad = QCheckBox("Final-stack gradient removal")
        self._final_grad.setChecked(False)
        self._final_grad.setToolTip(
            "After stacking, detect bright structure on the output, mask it, "
            "fit a residual sky gradient through the unmasked pixels, and "
            "subtract. Different from per-frame bg flatten — this one runs "
            "on the final stack with proper object masking. Use this for "
            "M42-style frames where per-frame bg flatten can't help."
        )
        form.addRow("", self._final_grad)

        # Color calibration
        self._color_cal = QComboBox()
        self._color_cal.addItem("Off", userData=None)
        self._color_cal.addItem("Gray-star (offline)", userData="gray_star")
        self._color_cal.addItem("Gaia catalog (online)", userData="gaia")
        self._color_cal.setToolTip(
            "Photometric color calibration applied to the final stack.\n\n"
            "<b>Gray-star</b>: assumes the average star in the field is "
            "neutral white. Works offline; good for dense star fields.\n\n"
            "<b>Gaia</b>: cross-matches detected stars to the Gaia catalog "
            "and uses each star's published colour to predict the correct "
            "R/G/B ratio. Requires internet. Most accurate."
        )
        form.addRow("Color calibration:", self._color_cal)

        # TIFF mode
        self._tiff_mode = QComboBox()
        self._tiff_mode.addItem("Linear (like DSS / Siril)", userData="linear")
        self._tiff_mode.addItem("Auto-stretched (ready to view)", userData="autostretch")
        self._tiff_mode.setToolTip(
            "<b>Linear</b>: 16-bit TIFF preserves the raw stack data with no "
            "curve applied. The file looks dark on its own — open it in "
            "PixInsight, Siril, GIMP, etc. and apply your own stretch. This "
            "is what serious astrophoto workflows expect, and it's what DSS "
            "does by default.\n\n"
            "<b>Auto-stretched</b>: applies a gentle Screen Transfer Function "
            "stretch so the file is viewable directly in Windows Photos / "
            "browsers. Convenient but commits to a particular look.\n\n"
            "Both modes always produce the same untouched 32-bit FITS — only "
            "the TIFF differs."
        )
        form.addRow("TIFF format:", self._tiff_mode)

        layout.addLayout(form)

        # Help text
        help_text = QLabel(
            "<small><i>Stack outputs go to <code>output/</code> in your project "
            "folder: a 32-bit FITS file (the data), a 16-bit autostretched TIFF, "
            "and a small PNG preview.</i></small>"
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        # Buttons. The OK button becomes the prominent "Stack" CTA — flag it
        # as primary so the theme's accent colour highlights it.
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("  ★  Stack")
        ok_btn.setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._apply_preset()
        # Drizzle controls start disabled (drizzle is off by default).
        self._on_drizzle_toggle(False)

    # ---- presets ------------------------------------------------------

    def _apply_preset(self) -> None:
        cfg = PRESETS[self._preset_combo.currentText()]
        self._sigma_toggle.setChecked(cfg["sigma_clip"])
        self._sigma_kappa.setValue(cfg["sigma_kappa"])
        # Note: background-flatten mode is target-type-specific (set by the
        # user in the dedicated combo), so presets deliberately leave it alone.

    def _on_sigma_toggle(self, on: bool) -> None:
        self._sigma_kappa.setEnabled(on)

    # ---- templates ---------------------------------------------------

    def _refresh_template_list(self) -> None:
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        self._template_combo.addItem("(no template)", userData=None)
        for name in list_templates():
            self._template_combo.addItem(name, userData=name)
        self._template_combo.blockSignals(False)

    def _on_save_template(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Save template", "Template name:",
            text=self._name.text().strip() or "",
        )
        if not ok or not name.strip():
            return
        try:
            save_template(name.strip(), self.options())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._refresh_template_list()
        # Select the just-saved one.
        idx = self._template_combo.findText(name.strip())
        if idx >= 0:
            self._template_combo.setCurrentIndex(idx)

    def _on_delete_template(self) -> None:
        name = self._template_combo.currentData()
        if not name:
            return
        if QMessageBox.question(
            self, "Delete template", f"Delete template '{name}'?",
        ) != QMessageBox.StandardButton.Yes:
            return
        delete_template(name)
        self._refresh_template_list()

    def _on_load_template(self, _idx: int) -> None:
        name = self._template_combo.currentData()
        if not name:
            return
        try:
            opts = load_template(name)
        except FileNotFoundError:
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not load template", str(exc))
            return
        self._apply_options(opts)

    def _apply_options(self, opts: StackOptions) -> None:
        """Push values from a StackOptions back into all the widgets."""
        self._sigma_toggle.setChecked(opts.sigma_clip)
        self._sigma_kappa.setValue(opts.sigma_kappa)
        self._drizzle.setChecked(opts.drizzle)
        self._drizzle_pixfrac.setValue(opts.drizzle_pixfrac)
        self._drizzle_scale.setValue(opts.drizzle_scale)
        idx = self._mosaic_canvas.findData(opts.mosaic_canvas)
        if idx >= 0:
            self._mosaic_canvas.setCurrentIndex(idx)
        # Bg mode dropdown
        idx = self._bg_mode.findData(opts.background_mode if opts.background_flatten else "off")
        if idx >= 0:
            self._bg_mode.setCurrentIndex(idx)
        self._bg_box_size.setValue(opts.background_box_size)
        self._hot_pixel.setChecked(opts.suppress_hot_pixels)
        self._quality_weight.setChecked(opts.quality_weighted)
        self._lucky_fraction.setValue(opts.lucky_fraction)
        self._subpixel.setChecked(opts.subpixel_refine)
        self._final_grad.setChecked(opts.final_gradient_removal)
        cc_data = opts.color_calibration_mode if opts.color_calibration else None
        idx = self._color_cal.findData(cc_data)
        if idx >= 0:
            self._color_cal.setCurrentIndex(idx)
        idx = self._tiff_mode.findData(opts.tiff_mode)
        if idx >= 0:
            self._tiff_mode.setCurrentIndex(idx)
        self._name.setText(opts.output_name)

    def _on_drizzle_toggle(self, on: bool) -> None:
        self._drizzle_pixfrac.setEnabled(on)
        self._drizzle_scale.setEnabled(on)
        # Drizzle is one-pass; sigma clipping doesn't apply.
        if on:
            self._sigma_toggle.setChecked(False)
        self._sigma_toggle.setEnabled(not on)
        self._sigma_kappa.setEnabled(self._sigma_toggle.isChecked())

    # ---- result -------------------------------------------------------

    def options(self) -> StackOptions:
        bg_mode = self._bg_mode.currentData()
        cc_mode = self._color_cal.currentData()
        return StackOptions(
            sigma_clip=self._sigma_toggle.isChecked(),
            sigma_kappa=float(self._sigma_kappa.value()),
            background_flatten=(bg_mode != "off"),
            background_mode=bg_mode if bg_mode != "off" else "per_channel",
            background_box_size=int(self._bg_box_size.value()),
            suppress_hot_pixels=self._hot_pixel.isChecked(),
            quality_weighted=self._quality_weight.isChecked(),
            lucky_fraction=float(self._lucky_fraction.value()),
            subpixel_refine=self._subpixel.isChecked(),
            final_gradient_removal=self._final_grad.isChecked(),
            color_calibration=(cc_mode is not None),
            color_calibration_mode=cc_mode or "gray_star",
            max_workers=int(self._workers.value()),
            output_name=self._name.text().strip() or "master",
            use_gpu=self._gpu_combo.currentData(),
            tiff_mode=self._tiff_mode.currentData(),
            drizzle=self._drizzle.isChecked(),
            drizzle_pixfrac=float(self._drizzle_pixfrac.value()),
            drizzle_scale=float(self._drizzle_scale.value()),
            mosaic_canvas=self._mosaic_canvas.currentData(),
        )
