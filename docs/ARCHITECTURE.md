# Architecture

Zapret2 Manager is a Python/Tkinter desktop wrapper around several upstream networking tools. The application is intentionally portable: the frozen EXE, `data/`, and `zapret/` live side by side.

## Main Modules

| File | Responsibility |
| --- | --- |
| `main.py` | Entry point, single-instance guard, top-level startup error handling |
| `ui.py` | Tkinter interface, tray icon integration, user commands, sync scheduling |
| `core.py` | Runtime backend, profile model, zapret process start/stop, settings, blockcheck |
| `upstreams.py` | GitHub API checks, archive download/extract, updater state |
| `tg_ws_proxy.py` | Local adapted Telegram WebSocket proxy runtime |
| `flowseal_profiles.py` | Flowseal batch/profile parsing and runtime profile generation |
| `generator.py` | Strategy generation and verification helpers |
| `fetch_release_components.py` | Downloads runtime components required for source builds |
| `prepare_release_assets.py` | Creates sanitized release `data/` assets before PyInstaller build |

## Runtime Folders

| Path | Purpose | Commit to source repo |
| --- | --- | --- |
| `data/logs/` | Runtime logs | No |
| `data/settings.json` | Local user settings | No |
| `data/profiles.json` | Local/custom user profiles | No |
| `data/custom-lists/` | User-maintained lists | No, except `.gitkeep` |
| `data/upstreams/` | Downloaded upstream snapshots | No, package in Releases |
| `zapret/` | zapret Windows bundle and blockcheck runtime | No, package in Releases |
| `release_assets/` | Temporary sanitized release staging | No |
| `dist*/`, `build*/` | PyInstaller output | No |

## Process Model

The app can start several runtime processes:

- Main DPI engine: usually `winws2.exe`.
- Blockcheck: Cygwin `bash.exe`, child `curl`, and temporary `winws2.exe` checks.
- Telegram proxy: local Python thread/server from `tg_ws_proxy.py`.

Process cleanup is intentionally conservative. Full exit should stop app-owned services and force-kill known zapret engine process images as a final safety net.

## Tray Model

The Windows tray icon is handled through Win32 calls. Tray callbacks should not call Tk directly from the tray window procedure. Instead, tray actions are queued and consumed from the Tk event loop.

If you modify tray behavior, test:

- Single left click.
- Double left click.
- Right-click menu.
- Close window to tray.
- Full exit from tray menu.
- Full exit while DPI or TG proxy is running.

## Updater Model

`sync_external_components()` updates components in this order:

1. `zapret`: downloads `bol-van/zapret-win-bundle`.
2. `zapret2`: downloads `bol-van/zapret2` and overlays it into `zapret/blockcheck/zapret2`.
3. `tg_ws_proxy`: downloads a reference upstream snapshot into `data/upstreams/tg-ws-proxy`.
4. `flowseal`: downloads a Flowseal strategy snapshot into `data/upstreams/flowseal-zapret-discord-youtube`.

The `zapret2` overlay preserves Windows binaries from the Windows bundle because the standalone `zapret2` repository ships sources/scripts, not ready-to-run Windows `winws2.exe` runtime files.

The `tg_ws_proxy` snapshot does not blindly replace the local `tg_ws_proxy.py`. The local file is adapted for embedded runtime use.

## Release Build

`build_release.bat` runs `fetch_release_components.py`, then `prepare_release_assets.py`, then PyInstaller with `Zapret2Manager.spec`.

The intended release shape is:

```text
Zapret2Manager/
  Zapret2Manager.exe
  data/
  zapret/
  ...
```

The source repository can stay lightweight while GitHub Releases carry the bundled runtime archive.
