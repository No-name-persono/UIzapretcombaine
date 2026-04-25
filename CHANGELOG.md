# Changelog

This project follows a simple human-readable changelog until formal versioning is introduced.

## Unreleased

- Added GitHub-ready project documentation and contribution files.
- Added third-party notices and source/release separation guidance.
- Added updater support for standalone `bol-van/zapret2` blockcheck overlay.
- Improved updater validation for zapret, zapret2, Flowseal snapshots, and tg-ws-proxy snapshots.
- Improved updater failure handling so one GitHub/API error does not crash the whole sync.
- Improved tray handling through queued tray actions.
- Improved full-exit cleanup for related zapret engine processes.

## 1.2.0 local alpha

- Windows 10/11 portable PyInstaller build profile.
- Background tray mode.
- Built-in and Flowseal-derived strategy profiles.
- Telegram WebSocket proxy integration.
- Monthly upstream sync option.
- Autostart option.
