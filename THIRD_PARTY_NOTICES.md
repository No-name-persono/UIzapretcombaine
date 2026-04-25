# Third-Party Notices

Zapret2 Manager is a wrapper/manager application. It is not the author of the DPI tools, strategy packs, proxy project, or packet-divert driver it can download or bundle.

## Upstream Components

| Component | Upstream | Purpose | License notes |
| --- | --- | --- | --- |
| zapret Windows bundle | https://github.com/bol-van/zapret-win-bundle | Windows-ready zapret/zapret2 binaries, Cygwin tools, blockcheck | See upstream repository and bundled notices |
| zapret2 | https://github.com/bol-van/zapret2 | zapret2 scripts/sources used by blockcheck2 overlay | MIT license in `zapret/blockcheck/zapret2/docs/LICENSE.txt` when bundled |
| Flowseal strategies | https://github.com/Flowseal/zapret-discord-youtube | Ready-made strategy/profile reference pack | MIT license plus bundled binary notices |
| tg-ws-proxy | https://github.com/Flowseal/tg-ws-proxy | Telegram WebSocket proxy reference implementation | MIT license |
| WinDivert | https://github.com/basil00/WinDivert | Windows packet divert driver used by zapret bundles | Upstream states LGPLv3/GPLv2 licensing options |

## Distribution Policy

Source repositories should normally avoid committing generated build folders, local logs, personal settings, and ad-hoc ZIP archives.

Binary releases may include upstream snapshots and Windows binaries so that end users can run the app without Python. When doing that, keep the original license files and notices inside the release archive.

## Maintainer Note

This file is not legal advice. Before publishing a public release, check the upstream repositories and keep their current license files in the packaged archive.
