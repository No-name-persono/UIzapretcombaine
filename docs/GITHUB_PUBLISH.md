# GitHub Publish Guide

This guide is for the first public repository publication.

## 1. Review Source Files

Before creating the first commit, check that these are not staged:

- `build*/`
- `dist*/`
- `release_assets/`
- `zapret/`
- `zapret_bak_*/`
- `*.zip`
- `data/logs/`
- `data/settings.json`
- `data/profiles.json`
- `data/upstreams/`
- generated `data/hosts_*.txt`

`.gitignore` is configured to exclude them.

## 2. Create Local Git Repository

```powershell
git init
git add .
git status --short
```

Read the staged file list carefully. If a huge binary folder or private setting appears, stop and fix `.gitignore` before committing.

```powershell
git commit -m "Initial public source release"
```

## 3. Create GitHub Repository

Create an empty repository on GitHub, then connect it:

```powershell
git branch -M main
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

## 4. Publish First Release

Build or reuse a tested portable ZIP. The current local naming pattern is:

```text
Zapret2Manager_win1011_*.zip
```

Create a GitHub Release:

- Tag: `v0.1.0-alpha.1`.
- Title: `Zapret2 Manager v0.1.0-alpha.1`.
- Attach the portable ZIP.
- Mention that the EXE is unsigned and requires administrator rights.
- Mention bundled upstream component versions if known.

## 5. Recommended Repository Settings

- Enable Issues.
- Enable Discussions if you want user strategy reports and help threads.
- Protect `main` once contributors appear.
- Require CI for pull requests after the first few commits.
- Add repository topics such as `windows`, `zapret`, `dpi`, `tkinter`, `portable`.

## 6. First Issues To Open

Good starter issues:

- Refactor `ui.py` into smaller modules.
- Refactor `core.py` into backend/settings/blockcheck modules.
- Add tests for updater archive extraction safety.
- Add tests for strategy parsing.
- Add screenshots to README.
- Add signed release or installer research.

## Building From A Fresh Clone

The source repository intentionally does not store `zapret/` or `data/upstreams/`.

To build a portable archive from a clean clone, run:

```powershell
python -m pip install -r requirements-dev.txt
python fetch_release_components.py
.\build_release.bat
```

`build_release.bat` also calls `fetch_release_components.py`, but running it explicitly first makes missing network/API problems easier to diagnose.
