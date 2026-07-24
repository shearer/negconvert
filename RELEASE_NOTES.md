# Release Notes

## v2026.07.008 — 2026-07-24

### Fixed

- **Auto Base Color no longer casts converted C-41 scans green/cyan.** For a real orange-masked base, the red channel's estimate routinely came out above 1.0 before being gamma-encoded back to sRGB, which silently clipped it to 1.0 and threw away exactly the red-vs-green/blue difference the estimate exists to measure — biasing the recovered base toward neutral and leaving a green/cyan tint in the converted positive. The estimate is now rescaled to a 1.0 ceiling first, preserving the relative cast between channels. This only affected regular JPEG/TIFF/PNG scans; raw/DNG loads (already linear, no sRGB round-trip) were unaffected by this particular bug.
  - Note: Auto Base Color still can't recover an accurate result on a scan that has no genuinely near-clear (film-base or blown-highlight) content in frame at all — for those, sample a known-neutral element in the scene (e.g. pavement, a gray card) with the pipette instead.

## v2026.07.007 — 2026-07-21

### Changed

- **Automatic conversion reworked, adapted from NegPy's "Auto Density / Auto Grade" per-frame metering.** Exposure, Contrast, Gamma, and now Saturation are all computed together as one auto-graded starting point, instead of Saturation being left at a flat 1.0:
  - Metering is now **center-weighted**, like an in-camera light meter, so a large sky, ceiling, or bright wall near the frame edge no longer skews the reading away from the actual subject.
  - The auto result is **mood-preserving**: a deliberately low-key or high-key frame is only partially pulled toward average brightness/contrast rather than flattened to one fixed target every time.
  - **Auto Base Color** no longer needs an actual strip of unexposed film in the frame — it now reads each color channel's own near-clear area independently and compares them, so it still works on scans cropped tight to just the image.
  - Gamma is now applied as a hue-safe curve on luma (rescaling each pixel's RGB to match) instead of a per-channel power curve, which used to amplify any residual color cast in the highlights.
  - Saturation range extended from 0–2 to 0–3 to give headroom for the new auto-suggested value on low-Gamma frames.
- **Crop is now the recommended first step.** Because Auto Base Color and the auto exposure/contrast/gamma/saturation grade are measured from whatever's in the current crop, cropping to the frame and clicking **Apply Crop** produces a meaningfully better initial conversion than the rough estimate computed on the raw, uncropped scan at Open. See [MANUAL.md](MANUAL.md#typical-workflow) for the recommended order.

### Fixed

- Auto-graded images no longer come out systematically flat/washed-out or over-dark on ordinary, symmetric tonal histograms — both the black/white stretch and the Gamma repositioning are now damped rather than applied at full, uncalibrated strength.

## v2026.07.006 — 2026-07-16

### Added

- **Per-image settings persistence.** Color, adjustment, crop, and rotation settings for each photo are now saved to a small sidecar file next to it (`<filename>.negconvert.json`). Reopening that photo — or a folder containing it — restores exactly where you left off, instead of re-estimating the film base and exposure from scratch. Sidecars are written automatically when you switch frames, export, quit, and periodically (about a second after you stop) while you're still adjusting a photo, so a crash or force-quit won't lose recent edits. See [MANUAL.md](MANUAL.md#remembering-settings-between-sessions) for details.
- **Copy/apply settings between frames.** Right-click a photo in the filmstrip and choose **Copy Settings** to copy its film mode, film base sample, exposure/density/contrast/gamma, color balance, saturation, denoise, and sharpening. Right-click another photo (or a group marked with Ctrl+click) and choose **Apply Settings** to paste them on — handy for a roll shot under consistent lighting where re-tuning every frame by hand would be redundant. Crop and rotation are left untouched, since those are framing choices rather than part of the color conversion. See [MANUAL.md](MANUAL.md#copying-color-settings-to-other-frames).
- Added [MANUAL.md](MANUAL.md), a full walkthrough of the interface and controls.
- Added README and LICENSE (AGPL-3.0-or-later).

### Changed

- Filmstrip: clicking a new photo now automatically clears any existing Ctrl+click multi-selection, instead of requiring you to deselect marked frames one at a time before picking a new one.

## v2026.07.005 and earlier

See commit history for changes prior to this file's introduction.
