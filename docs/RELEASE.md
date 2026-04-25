# Release Checklist

Use this checklist before publishing a GitHub Release.

## Before Build

- Confirm the source tree does not contain private logs or personal settings.
- Confirm `THIRD_PARTY_NOTICES.md` is up to date.
- Confirm the latest updater run has the desired upstream component versions.
- Confirm `zapret/` exists locally if building a full portable release.
- Confirm `data/upstreams/` contains the desired Flowseal and tg-ws-proxy snapshots.

## Local Validation

```powershell
python -m py_compile main.py core.py ui.py upstreams.py tg_ws_proxy.py flowseal_profiles.py generator.py prepare_release_assets.py
python fetch_release_components.py
python prepare_release_assets.py
.\build_release.bat
```

Check that release state does not contain local developer paths:

```powershell
Select-String -Path .\dist_win1011\Zapret2Manager\data\upstream_state.json -Pattern 'C:\\Users'
```

No matches should be returned.

## Smoke Test

On a Windows 10/11 test machine:

1. Extract the release ZIP into a clean folder.
2. Start `Zapret2Manager.exe`.
3. Confirm the app opens without Python installed.
4. Start a built-in profile.
5. Stop the profile.
6. Start and stop Telegram proxy.
7. Close the window to tray.
8. Restore from tray.
9. Fully exit from tray and confirm no `winws2.exe` remains.
10. Run upstream sync once if network access is available.

## Publish

Create a GitHub Release with:

- Tag: `vX.Y.Z` or `vX.Y.Z-alpha.N`.
- ZIP: ready-to-run portable archive.
- Notes: user-visible changes, known issues, upstream component versions.
- Warning: administrator rights, unsigned EXE, WinDivert/antivirus caveat.

## Known Release Risks

- Unsigned EXE may trigger SmartScreen.
- WinDivert may trigger antivirus heuristics.
- GitHub API rate limits can temporarily block update checks.
- Strategies are ISP-dependent and may stop working without app changes.
