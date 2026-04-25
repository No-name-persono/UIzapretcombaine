@echo off
setlocal
cd /d "%~dp0"

echo [*] Windows 7 build profile
echo [*] This build must use Python 3.8 and should ideally run on Windows 7 or a Windows 7 VM.
echo [*] Required before build:
echo     1. Python 3.8 x64
echo     2. PyInstaller installed into that Python 3.8
echo     3. KB2533623 present on the target Win7 machine
echo.

py -3.8 -c "import sys; print(sys.version)"
if errorlevel 1 (
    echo [!] Python 3.8 launcher entry not found. Install Python 3.8 first.
    exit /b 1
)

py -3.8 -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [!] PyInstaller is missing in Python 3.8.
    echo     Run: py -3.8 -m pip install pyinstaller
    exit /b 1
)

tasklist /FI "IMAGENAME eq Zapret2Manager.exe" | find /I "Zapret2Manager.exe" >nul
if %errorlevel% equ 0 (
    echo [!] Close running Zapret2Manager.exe before rebuilding.
    exit /b 1
)

py -3.8 -m PyInstaller --noconfirm --clean --distpath dist_win7 --workpath build_win7 Zapret2Manager.spec
if errorlevel 1 (
    echo [!] Win7 build failed.
    exit /b 1
)

echo.
echo [*] Win7-oriented build complete:
echo     %CD%\dist_win7\Zapret2Manager
endlocal
