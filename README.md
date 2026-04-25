# Zapret2 Manager

Russian quickstart: [README_RU.md](README_RU.md)

Zapret2 Manager is a Windows desktop manager for running DPI-bypass strategies through zapret/zapret2 tooling, Flowseal strategy presets, blockcheck helpers, and an adapted Telegram WebSocket proxy.

The goal is simple: give non-technical users one understandable interface, while keeping the project open enough for developers to improve strategies, packaging, update logic, and UI behavior.

## Status

The project is currently an early Windows 10/11 alpha/beta. It works as a portable desktop app, but the codebase is still being cleaned up for public collaboration.

Windows 7 is not a current target. Keep Windows 10/11 as the supported path unless a maintainer explicitly revives the Win7 build profile.

## What It Does

- Starts and stops zapret/zapret2 `winws2.exe` strategies from a GUI.
- Includes built-in strategy profiles and Flowseal-derived presets.
- Can run Telegram WebSocket proxy support from the same application.
- Can hide to the Windows tray and keep services running in the background.
- Stops related DPI/proxy processes on full application exit.
- Can check upstream updates for zapret, zapret2, Flowseal strategy snapshots, and tg-ws-proxy.
- Can build a portable Windows release with bundled runtime components.

## What This Project Is Not

- It is not the original zapret, zapret2, Flowseal strategy pack, tg-ws-proxy, or WinDivert project.
- It is not a guarantee that any specific strategy will work for every ISP.
- It is not a signed commercial installer. Windows SmartScreen or antivirus tools may warn about unsigned binaries and WinDivert.

## Upstreams

This manager integrates or references these projects:

- `bol-van/zapret-win-bundle`: https://github.com/bol-van/zapret-win-bundle
- `bol-van/zapret2`: https://github.com/bol-van/zapret2
- `Flowseal/zapret-discord-youtube`: https://github.com/Flowseal/zapret-discord-youtube
- `Flowseal/tg-ws-proxy`: https://github.com/Flowseal/tg-ws-proxy
- `basil00/WinDivert`: https://github.com/basil00/WinDivert

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before publishing binary releases.

## For Users

Download the latest portable ZIP from GitHub Releases, extract it into a normal folder, and run `Zapret2Manager.exe`.

Recommended first steps:

1. Start the application as administrator.
2. Open the configuration tab.
3. Choose a built-in or Flowseal profile.
4. Click start.
5. If something breaks, click stop or fully exit from the tray menu.

The app needs administrator rights because zapret/WinDivert needs access to network traffic interception.

## For Developers

Clone the repository, install Python, install dependencies, and run the app from source.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements-dev.txt
python main.py
```

If `zapret/` is missing, the setup/bootstrap flow can download the Windows bundle. For a fully bundled release, prepare upstream assets and build the portable app.

```powershell
python prepare_release_assets.py
.\build_release.bat
```

The release output is written to:

```text
dist_win1011\Zapret2Manager
```

## Repository Layout

```text
main.py                    App entry point and single-instance guard
ui.py                      Tkinter UI, tray behavior, user actions
core.py                    zapret backend, profiles, blockcheck, settings
upstreams.py               GitHub upstream sync/update logic
tg_ws_proxy.py             Adapted embedded Telegram WS proxy
flowseal_profiles.py       Flowseal strategy profile conversion
generator.py               Strategy generation helpers
prepare_release_assets.py  Release asset staging
Zapret2Manager.spec        PyInstaller configuration
docs/                      Maintainer and user documentation
```

## Release Model

The source repository should stay lightweight. Do not commit local `build*`, `dist*`, ZIP archives, logs, personal settings, or bundled upstream binary snapshots.

GitHub Releases should contain the ready-to-run portable ZIP for end users. That ZIP may include `zapret`, Flowseal snapshots, tg-ws-proxy snapshots, and release metadata.

## Safety Notes

This project starts and stops tools that modify network traffic handling on Windows. Bugs can temporarily break connectivity until the strategy is stopped or the process is killed.

Before changing process management, tray behavior, updater logic, or WinDivert cleanup, test full exit behavior carefully.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before large changes.
