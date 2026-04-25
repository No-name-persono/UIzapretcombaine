# Security Policy

Zapret2 Manager controls tools that can intercept and modify local network traffic. Treat process management, updater code, bundled binaries, and release packaging as security-sensitive areas.

## Supported Versions

Only the latest public release is supported once releases are published.

## Reporting Issues

If you find a security-sensitive bug, do not publish exploit steps in a public issue. Contact the maintainers privately if a private contact is listed in the repository.

If no private contact exists yet, open a public issue with a minimal description and ask for a private channel.

## Sensitive Areas

- Downloading and replacing upstream components.
- Process cleanup for `winws2.exe`, `winws.exe`, `nfqws*.exe`, and `tpws*.exe`.
- WinDivert driver handling.
- Tray and full-exit behavior.
- Autostart task creation.
- Release archive contents.

## User Safety

Users should download releases only from the official repository Releases page. Unsigned Windows binaries may trigger SmartScreen or antivirus warnings, especially because WinDivert is a packet interception driver.
