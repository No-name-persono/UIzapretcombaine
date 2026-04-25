# Maintainer Notes

This project is partly a product and partly glue code. The most valuable maintainer work is reducing surprise for users.

## Good First Areas

- Split `ui.py` into smaller views/controllers.
- Split `core.py` into backend, profiles, blockcheck, settings, and process modules.
- Add tests for strategy parsing and updater path sanitization.
- Improve diagnostics around failed starts/stops.
- Improve release automation.
- Improve documentation and screenshots.

## High-Risk Areas

- Tray icon Win32 callback behavior.
- Full exit cleanup.
- Job Object/process tree handling.
- WinDivert driver deletion.
- Upstream archive extraction.
- Autostart scheduled task creation.

## Refactor Direction

Suggested future package structure:

```text
zapret_manager/
  app.py
  ui/
  backend/
  upstreams/
  profiles/
  telegram_proxy/
  packaging/
tests/
```

Avoid large rewrites unless there is a clear test path. The current priority is predictable behavior over architectural beauty.
