# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH)
RELEASE_DATA = ROOT / "release_assets" / "data"
DATA_SOURCE = RELEASE_DATA if RELEASE_DATA.exists() else ROOT / "data"
ZAPRET_SOURCE = ROOT / "zapret"
RUN_NO_TRAY = ROOT / "run_no_tray.bat"
OPTIONAL_DATAS = []
if RUN_NO_TRAY.exists():
    OPTIONAL_DATAS.append((str(RUN_NO_TRAY), "."))

CRYPTO_DATAS, CRYPTO_BINARIES, CRYPTO_HIDDENIMPORTS = collect_all("cryptography")
CFFI_DATAS, CFFI_BINARIES, CFFI_HIDDENIMPORTS = collect_all("cffi")
try:
    WEBSOCKETS_DATAS, WEBSOCKETS_BINARIES, WEBSOCKETS_HIDDENIMPORTS = collect_all("websockets")
except Exception:
    WEBSOCKETS_DATAS, WEBSOCKETS_BINARIES, WEBSOCKETS_HIDDENIMPORTS = [], [], []


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=CRYPTO_BINARIES + CFFI_BINARIES + WEBSOCKETS_BINARIES,
    datas=[
        (str(DATA_SOURCE), 'data'),
        (str(ZAPRET_SOURCE), 'zapret'),
    ] + OPTIONAL_DATAS + CRYPTO_DATAS + CFFI_DATAS + WEBSOCKETS_DATAS,
    hiddenimports=sorted(set(
        CRYPTO_HIDDENIMPORTS +
        CFFI_HIDDENIMPORTS +
        WEBSOCKETS_HIDDENIMPORTS +
        [
            'cryptography.hazmat.primitives.ciphers',
            '_cffi_backend',
        ]
    )),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Zapret2Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Zapret2Manager',
)
