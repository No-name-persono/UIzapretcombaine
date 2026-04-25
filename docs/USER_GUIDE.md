# User Guide

This guide is for normal Windows users who downloaded a release ZIP.

## Install

1. Download the latest ZIP from GitHub Releases.
2. Extract it into a folder such as `C:\Tools\Zapret2Manager`.
3. Run `Zapret2Manager.exe`.
4. Allow administrator elevation if Windows asks.

Do not run the app directly from inside the ZIP archive.

## Basic Use

1. Open the app.
2. Go to `Конфигурации`.
3. Select a profile.
4. Click start.
5. Check the status indicator.
6. Click stop before switching strategies if something behaves strangely.

## Tray Behavior

Closing the window hides the app to the tray. The active DPI/proxy services may continue running in the background.

Use the tray menu to restore the window, stop services, or fully exit the app.

Full exit should stop zapret and Telegram proxy components.

## Telegram Proxy

The Telegram tab controls the embedded Telegram WebSocket proxy.

If the proxy is disabled, Telegram may still remember its own proxy setting. The app can expose a proxy link, but users may still need to disable proxy manually inside Telegram depending on Telegram client behavior.

## Updates

The app can check upstream components:

- zapret Windows bundle.
- standalone zapret2 scripts for blockcheck.
- Flowseal strategy snapshot.
- tg-ws-proxy upstream snapshot.

The monthly update option checks these upstreams periodically. Updates may fail temporarily if GitHub rate limits or network access blocks the request.

## Troubleshooting

If the internet connection breaks after testing a strategy:

1. Open the app and click stop.
2. Use the tray menu and choose full exit.
3. If needed, open Task Manager and check for `winws2.exe`, `winws.exe`, `nfqws*.exe`, or `tpws*.exe`.
4. Restart Windows if the driver/network stack is in a bad state.

If antivirus flags the app, remember that WinDivert is a packet interception driver. Download releases only from the official repository and inspect bundled files if unsure.
