<img width="1470" height="920" alt="NegConvert screenshot" src="https://github.com/user-attachments/assets/2b204176-71a0-4eef-ae3f-feb82ccd455b" />

# NegConvert

NegConvert is a desktop app for converting scanned film negatives and slides into positive images. It does the conversion in linear light using a density (log) model of how film actually responds to exposure, instead of just inverting gamma-encoded pixel values - so color balance stays accurate across shadows and highlights instead of shifting the way a naive "invert" does.

It supports color negative (C-41), black & white negative, and slide/reversal (E-6) film, reading straight from JPEG/PNG/TIFF scans or from scanner and camera RAW files (DNG, CR2/CR3, NEF, ARW, RAF, ORF, RW2, PEF, RAW/RWL, 3FR).

**Features**
- Automatic or manual film-base sampling to neutralize the orange mask on color negatives
- Per-channel (RGB) color balance, exposure, density, shadow/highlight density, contrast, gamma, saturation, denoise, and sharpening controls
- Crop with arbitrary-angle straighten
- Export to TIFF, PNG, JPEG, or Linear DNG, with sRGB, Adobe RGB, or ProPhoto RGB color profiles
- Batch export across multiple selected frames in a filmstrip view

## Installation

Prebuilt installers for macOS, Windows, and Linux are published on the [Releases page](https://github.com/shearer/negconvert/releases). Builds are unsigned, so the OS will show an "unknown developer" warning the first time you open one - see the notes below.

### macOS

1. Download `NegConvert-<version>-macos-arm64.dmg` (Apple Silicon) or `NegConvert-<version>-macos-intel.dmg` (Intel Macs).
2. Open the `.dmg` and drag **NegConvert** into **Applications**.
3. Since the build isn't notarized, the first launch will be blocked by Gatekeeper. Right-click (or Control-click) **NegConvert.app** in Applications and choose **Open**, then confirm in the dialog. This is only needed once.
4. On newer macOS versions, Gatekeeper may instead refuse to open the app at all and only offer **Move to Trash**, even after step 3. If that happens, clear the quarantine flag from Terminal and try again:
   ```bash
   xattr -cr /Applications/NegConvert.app
   ```

### Windows

1. Download `NegConvert-<version>-windows.exe`.
2. Run the installer. Windows SmartScreen will likely warn that it's from an unrecognized publisher - click **More info**, then **Run anyway**.
3. Follow the setup wizard; it adds a Start Menu entry and an optional desktop shortcut.

### Linux

1. Download `NegConvert-<version>-linux-x86_64.AppImage`.
2. Make it executable and run it:
   ```bash
   chmod +x NegConvert-<version>-linux-x86_64.AppImage
   ./NegConvert-<version>-linux-x86_64.AppImage
   ```
3. Your desktop environment may show its own "untrusted executable" prompt on first run - allow it.

### From source (any platform)

Requires Python 3.12+.

```bash
git clone https://github.com/shearer/negconvert.git
cd negconvert
pip install -r requirements.txt
python main.py
```

`requirements.txt` pulls in PySide6, Pillow, numpy, rawpy (RAW/DNG support), tifffile (Linear DNG export), and scipy (straighten rotation).

## License

NegConvert is licensed under the [GNU Affero General Public License v3.0](LICENSE) or later. If you run a modified version of NegConvert as a network service, the AGPL requires you to make the Corresponding Source available to users of that service.
