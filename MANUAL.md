# NegConvert User Manual

This is a walkthrough of every screen and control in NegConvert. For installation instructions, see [README.md](README.md).

## Contents

- [NegConvert User Manual](#negconvert-user-manual)
  - [Contents](#contents)
  - [Overview](#overview)
  - [Opening images](#opening-images)
  - [The main window](#the-main-window)
  - [Typical workflow](#typical-workflow)
  - [Colors tab](#colors-tab)
  - [Adjustments tab](#adjustments-tab)
  - [Crop tab](#crop-tab)
  - [Export tab](#export-tab)
  - [Canvas interactions](#canvas-interactions)
  - [Batch processing multiple frames](#batch-processing-multiple-frames)
  - [Keyboard shortcuts](#keyboard-shortcuts)
  - [Tips](#tips)

## Overview

NegConvert turns scanned film negatives and slides into positive images. It works in linear light using a density (log) model of how film actually responds to exposure, rather than a simple color invert, so color balance stays accurate across shadows and highlights.

It supports three film modes:

- **C-41** – color negative film. Has an orange base mask that needs to be neutralized before conversion.
- **B&W** – black & white negative film. No color cast to correct; the Color Balance and Film Base controls are hidden since they'd have no effect.
- **E-6** – color slide/reversal film. Already a positive image, so it's handled differently: exposure is corrected without inverting, and there's no orange mask, just an optional color-cast correction.

## Opening images

Use the toolbar at the top of the window:

- **Open Negative…** – opens a single scan or camera/scanner RAW file.
- **Open Folder…** – opens every supported image in a folder at once, loading them into the filmstrip along the bottom of the window so you can step through a whole roll.

Supported formats: JPEG, PNG, TIFF, BMP, and scanner/camera RAW files (DNG, CR2/CR3, NEF/NRW, ARW/SRF/SR2, RAF, ORF, RW2, PEF, RAW/RWL, 3FR).

When an image loads, NegConvert automatically estimates the film base color (for C-41/E-6) and computes a starting exposure/contrast/gamma so the preview looks reasonable immediately — you don't have to set everything from a blank slate.

## The main window

- **Toolbar** (top) – Open Negative, Open Folder, Auto Base Color, Reset Adjustments.
- **Canvas** (center) – the live preview of the converted positive.
- **Sidebar** (right) – Histogram, then four tabs: **Colors**, **Adjustments**, **Crop**, **Export**.
- **Filmstrip** (bottom) – thumbnails of every loaded image; click to switch between them. Each photo remembers its own settings (color balance, crop, rotation) independently.
- **Status bar** (bottom edge) – current file name, position within a folder, and pixel dimensions.

## Typical workflow

1. **Open Folder…** to load a whole roll, or **Open Negative…** for a single scan.
2. On the **Colors** tab, confirm the **Film Type** and sample the **Film Base** if the automatic guess looks off.
3. Fine-tune **Color Balance** and exposure/contrast on the **Adjustments** tab.
4. Straighten and crop on the **Crop** tab if needed.
5. Pick a format and color profile on the **Export** tab and save — either one image at a time, or several at once via batch export.
6. Use the filmstrip to move to the next frame; each frame keeps its own adjustments.

## Colors tab

**Film Type** — choose C-41, B&W, or E-6. Switching modes re-estimates the film base color and recalculates auto exposure/contrast/gamma for the new mode.

**Color Balance** (hidden for B&W) — three sliders, Red/Green/Blue, each ±0.5 stops. These shift density per-channel to correct color casts (e.g. push Blue up to counteract a yellow cast). Double-click any slider to reset it to zero.

**Film Base** (hidden for B&W) — the swatch shows the currently sampled base color, used to neutralize the orange mask (C-41) or a slide's color cast (E-6):

1. Click the pipette button to arm it (cursor becomes a crosshair).
2. Click a spot on the image:
   - **C-41**: click anywhere on unexposed film (e.g. the frame edge/sprocket area) to sample the orange mask.
   - **E-6**: click a clear, unexposed edge of the slide.
3. The swatch and RGB readout update, and exposure/contrast/gamma are automatically recalculated for the new base color.

The **Auto Base Color** toolbar button does the same sampling automatically across the whole frame instead of a manual click — useful as a first pass or to reset after a bad manual sample. It's a no-op on B&W scans (there's no color cast to correct), and the status bar will say so if you click it in that mode.

## Adjustments tab

All sliders can be reset individually by double-clicking them (this returns them to their default value, not necessarily zero — Exposure/Contrast/Gamma default to the auto-calculated values for the current image).

| Slider | Range | What it does |
|---|---|---|
| Exposure (EV) | −8 to 8 | Shifts the whole density image in stops — the main brightness control. |
| Density | −4 to 4 | An additional stops shift applied after Contrast (unlike Exposure, not scaled by it). |
| Shadow Density | −2 to 2 | Adds density only in shadow tones. |
| Highlight Density | −2 to 2 | Adds density only in highlight tones. |
| Contrast | 0.5 to 2.5 | Scales the density spread around the midtone pivot. |
| Gamma | 0.3 to 2.5 | A display gamma trim applied after tone-mapping. |
| Saturation | 0 to 2 | Scales color intensity (chroma) around luma; 1.0 is neutral. |
| Denoise | 0 to 2 | Median-filter grain reduction, applied before Sharpening. |
| Sharpening | 0 to 2 | Unsharp-mask sharpening, applied last on the final image. |

The **Reset Adjustments** toolbar button zeroes out Density, Shadow/Highlight Density, Saturation (back to 1.0), Denoise, Sharpening, and the Color Balance sliders, then recomputes Exposure/Contrast/Gamma from scratch for the current film base — it's a full reset back to the automatic starting point, not to literal zero on every control.

## Crop tab

- **Aspect Ratio** — choose Free, or a preset (1:1 square, 3:2 / 2:3 35mm, 4:3 / 3:4 645, 16:9 / 9:16, 5:4 / 4:5 large format). Changing this reshapes the current crop box to match.
- While this tab is open, drag directly on the image:
  - Drag a **corner handle** to resize the crop box (constrained to the chosen aspect ratio, if any).
  - Drag **inside the box** to move it without resizing.
- **Apply Crop** — leaves crop mode and shows the cropped result on the other tabs.
- **Redo Crop** — re-enters crop mode to adjust the box again.
- **Reset Crop** — clears the crop back to the full frame and resets rotation/straighten to zero.
- **Rotate Left / Rotate Right** — rotate the image 90° at a time (resets the crop box).
- **Straighten (°)** — rotates the image by an arbitrary angle, −45° to 45°, with red guide lines shown while dragging to help level horizons. NegConvert automatically shrinks the crop box as needed so straightening doesn't leave transparent corners in the export.

Switch to another tab to preview the cropped image without the crop overlay.

## Export tab

**Format** — TIFF, PNG, JPEG, or Linear DNG.

- Linear DNG exports the converted positive as raw scene-linear data with no gamma encoding and no embedded color profile — meant for further processing in raw-capable software rather than direct viewing.
- TIFF/PNG/JPEG export a standard gamma-encoded positive with an embedded ICC profile.

**Color Profile** — sRGB, Adobe RGB, or ProPhoto RGB (disabled for Linear DNG, since raw data has no profile to embed).

**Save As…** — saves the current photo, with its current crop applied, to a file you choose. The default filename is `<original name>_positive.<ext>`.

## Canvas interactions

- **Double-click** the image to cycle zoom: fit-to-window → 50% → 100% → back to fit. Double-clicking re-centers the zoom on the point you clicked.
- **Right-click** the image to change the surrounding frame/mat color (White, Middle Grey, or Dark Grey) — this is just a display aid and has no effect on the exported image.
- While the pipette is armed (Colors tab), **left-click** the image to sample the film base color at that point instead of zooming or panning.

## Batch processing multiple frames

1. Load a folder of scans with **Open Folder…**.
2. Adjust each frame individually by clicking through the filmstrip — settings are kept per-photo.
3. Ctrl+click frames in the filmstrip to mark several (marked thumbnails are highlighted).
4. On the **Export** tab, pick a format and profile, then click **Export Selected…** and choose a destination folder. Each marked photo is converted with its own saved settings and written as `<name>_positive.<ext>` into that folder.

### Copying color settings to other frames

If a whole roll was shot and scanned under consistent lighting, you can dial in the film mode, film base sample, exposure/density/contrast/gamma, color balance, saturation, denoise, and sharpening on one frame, then apply that exact same conversion to others instead of re-tuning each one by hand — using a right-click, copy/apply workflow on the filmstrip:

1. Right-click the frame whose settings you want to reuse and choose **Copy Settings**.
2. Select the frame(s) to apply it to:
   - For one frame, just right-click that frame.
   - For several, Ctrl+click to mark them first, then right-click any marked frame.
3. Choose **Apply Settings** (only enabled once something has been copied).

This overwrites the target frame(s)' color/adjustment settings with the copied ones. Crop and rotation are left untouched, since those are framing choices rather than part of the color conversion. It's a one-time copy, not a live link — adjusting the source frame afterward doesn't affect frames you already applied it to; right-click and **Copy Settings** again to update what's on the clipboard.

## Remembering settings between sessions

Every photo's settings - film mode, film base sample, exposure/density/contrast/gamma, color balance, saturation, denoise, sharpening, crop, and rotation - are saved automatically to a small sidecar file next to it, named `<original filename>.negconvert.json` (e.g. `frame12.jpg.negconvert.json`). It's written whenever you move to another frame, export, or quit the app - and also shortly (under a second) after you stop adjusting a photo you're still sitting on, so a crash or force-quit won't lose your latest edits.

The next time you open that photo, or open a folder containing it, NegConvert reads the sidecar and puts you right back where you left off - the film base sample and auto exposure aren't re-estimated from scratch. Photos you never actually opened get no sidecar and load with the normal automatic film-base/exposure estimate, same as before.

Sidecars travel with the image: copy or move a scan together with its `.negconvert.json` file and its settings come with it. Deleting the sidecar (or renaming the image without renaming the sidecar to match) just makes NegConvert treat that photo as never-adjusted again.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Cmd/Ctrl+O | Open Negative… |
| Cmd/Ctrl+S | Save As… |

## Tips

- Sample the film base from an area that's truly unexposed film (a sprocket hole or frame border), not part of the photographed scene — that's what the orange-mask neutralization depends on. Sometimes the results are better when selecting an area inside the image for example a grey area.
- If a whole roll was scanned under consistent lighting, sampling the film base once and copying the color balance across frames (by re-sampling on each, or just leaving the same manual Red/Green/Blue offsets) usually gets you closer, faster, than re-tuning every frame from scratch.
- Straightening automatically tightens the crop to avoid empty corners — if you need the absolute maximum frame area, straighten first, then manually drag the crop back out before applying.
- Use Linear DNG export if you want to keep grading the image in another raw-capable tool later; use TIFF/PNG/JPEG for a finished, ready-to-view positive.
