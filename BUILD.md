# Build Notes

## Standard portable build

Run:

```bat
build_release.bat
```

Output:

```text
dist_win1011\Zapret2Manager
```

This layout keeps `Zapret2Manager.exe`, `data`, and `zapret` in one folder so the app behaves like a portable bundle.

The portable release is self-contained for Windows 10/11:

- `zapret` is bundled into the release.
- Flowseal snapshot is bundled into `data\upstreams`.
- TG WS Proxy snapshot is bundled into `data\upstreams`.
- First launch does not require downloading these resources from GitHub.

Release packaging intentionally excludes local developer state such as logs, saved settings, generated hostlists, and personal custom profiles.

## Windows 7 target

Windows 7 is a separate target profile.

Use:

```bat
build_win7_py38.bat
```

Important constraints:

- Do not build the Win7 release with Python 3.9+.
- Use Python 3.8 x64 for the frozen app.
- For best compatibility, build on Windows 7 itself or inside a Windows 7 VM.
- The target Win7 machine needs update `KB2533623`.

## Current local result

The latest local portable build created from this workspace is:

```text
dist_win1011\Zapret2Manager
```
