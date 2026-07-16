# Release Notes

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
