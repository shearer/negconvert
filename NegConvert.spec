# -*- mode: python ; coding: utf-8 -*-
# Shared across macOS/Windows/Linux (see .github/workflows/build.yml) - only
# the icon and the final macOS .app wrapping differ per platform.
import sys

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    icon = 'assets/NegConvert.icns'
elif sys.platform == 'win32':
    icon = 'assets/NegConvert.ico'  # generated at build time, see workflow
else:
    icon = None  # PyInstaller can't embed an icon in a Linux ELF binary

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NegConvert',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    # None = build for the current machine's own architecture. CI now runs
    # this on both an Apple Silicon and an Intel macOS runner (see
    # .github/workflows/build.yml) to produce separate arm64/x86_64
    # builds, so this can no longer be hardcoded to arm64.
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NegConvert',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='NegConvert.app',
        icon='assets/NegConvert.icns',
        bundle_identifier='com.negconvert.app',
        info_plist={
            'CFBundleName': 'NegConvert',
            'CFBundleDisplayName': 'NegConvert',
            'CFBundleShortVersionString': '1.1.0',
            'CFBundleVersion': '1.1.0',
            'NSHighResolutionCapable': True,
            'NSHumanReadableCopyright': 'NegConvert',
        },
    )
