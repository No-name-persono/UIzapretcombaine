# Contributing

Thanks for wanting to improve Zapret2 Manager. The project exists to make a complicated set of tools usable for normal Windows users, so good contributions are not only code. Clear docs, safer defaults, better diagnostics, and reliable cleanup matter a lot.

## Priorities

- Make the app safer to start, stop, hide to tray, and fully exit.
- Keep the UI understandable for non-technical users.
- Avoid breaking existing built-in and Flowseal-derived profiles.
- Improve updater behavior without blindly replacing adapted local code.
- Keep releases portable and self-contained for Windows 10/11.
- Document risky behavior instead of hiding it.

## Development Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements-dev.txt
python main.py
```

Run a syntax check before opening a pull request:

```powershell
python -m py_compile main.py core.py ui.py upstreams.py tg_ws_proxy.py flowseal_profiles.py generator.py prepare_release_assets.py
```

## Pull Request Checklist

- Explain what changed and why.
- Mention whether the change affects zapret, zapret2, Flowseal strategies, tg-ws-proxy, or packaging.
- Test start/stop behavior if the change touches process management.
- Test full application exit if the change touches tray behavior or cleanup.
- Do not commit local logs, settings, generated hostlists, build folders, or release ZIPs.
- Keep third-party license files in binary releases.

## Code Style

The current codebase is pragmatic and still needs refactoring. Prefer small, safe changes over broad rewrites.

Use clear names and keep user-facing Russian text understandable. If you add a low-level workaround, add a short comment explaining why it exists.

## Upstream Code

Do not blindly paste or overwrite upstream code if the local file is adapted for Zapret2 Manager. For example, `tg_ws_proxy.py` is intentionally adapted and should be updated carefully.

When changing updater behavior, preserve the distinction between:

- `zapret-win-bundle`: Windows-ready binaries and blockcheck bundle.
- `zapret2`: standalone scripts/sources overlaid into blockcheck while preserving Windows binaries.
- `tg-ws-proxy`: upstream snapshot used for reference; runtime adapter is local.
- `Flowseal`: strategy snapshot and profile source.
