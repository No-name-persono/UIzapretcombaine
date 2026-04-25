@echo off
setlocal
cd /d "%~dp0"

echo [*] Building portable release...

set "PYI_EXE="
for /f "delims=" %%I in ('where pyinstaller 2^>nul') do if not defined PYI_EXE set "PYI_EXE=%%I"
if not defined PYI_EXE (
    echo [!] PyInstaller not found in PATH.
    exit /b 1
)

for %%I in ("%PYI_EXE%") do set "BUILD_PY=%%~dpI..\python.exe"
if not exist "%BUILD_PY%" (
    echo [!] Could not resolve python.exe for this PyInstaller:
    echo     %PYI_EXE%
    exit /b 1
)

tasklist /FI "IMAGENAME eq Zapret2Manager.exe" | find /I "Zapret2Manager.exe" >nul
if %errorlevel% equ 0 (
    echo [!] Close running Zapret2Manager.exe before rebuilding.
    exit /b 1
)

"%BUILD_PY%" -c "import cryptography" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing build dependency: cryptography
    "%BUILD_PY%" -m pip install cryptography
    if errorlevel 1 (
        echo [!] Failed to install cryptography into build environment.
        exit /b 1
    )
)

"%BUILD_PY%" prepare_release_assets.py
if errorlevel 1 (
    echo [!] Failed to prepare release assets.
    exit /b 1
)

"%BUILD_PY%" -m PyInstaller --noconfirm --clean --distpath dist_win1011 --workpath build_win1011 Zapret2Manager.spec
if errorlevel 1 (
    echo [!] Build failed.
    exit /b 1
)

"%BUILD_PY%" -c "from pathlib import Path; import json, sys; dist=Path(r'dist_win1011/Zapret2Manager'); required=['Zapret2Manager.exe','cryptography','data/release_manifest.json','data/upstream_state.json','data/upstreams/flowseal-zapret-discord-youtube','data/upstreams/tg-ws-proxy','zapret']; missing=[item for item in required if not (dist / item).exists()]; manifest_path=dist / 'data' / 'release_manifest.json'; manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}; missing.extend(['manifest:first_run_download_required=false'] if manifest.get('first_run_download_required') is not False else []); missing.extend(['_cffi_backend'] if not any(p.name.startswith('_cffi_backend') for p in dist.iterdir()) else []); print('[*] Build verification OK' if not missing else '[!] Missing required release assets: ' + ', '.join(missing)); sys.exit(1 if missing else 0)"
if errorlevel 1 (
    echo [!] Release verification failed.
    exit /b 1
)

echo.
echo [*] Build complete:
echo     %CD%\dist_win1011\Zapret2Manager
echo [*] Release assets source:
echo     %CD%\release_assets\data
endlocal
