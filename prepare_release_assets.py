import json
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC_DATA = ROOT / "data"
RELEASE_ROOT = ROOT / "release_assets"
RELEASE_DATA = RELEASE_ROOT / "data"


def copytree_if_exists(src: Path, dst: Path):
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def prepare_upstream_state(src: Path, dst: Path):
    if src.is_file():
        with open(src, encoding="utf-8") as f:
            state = json.load(f)
    else:
        state = {}

    if isinstance(state, dict):
        for key, item in state.items():
            if not isinstance(item, dict):
                continue
            # Portable releases must not expose or depend on developer-machine
            # absolute paths. Runtime sync will rewrite these with real paths.
            item["backup_dir"] = ""
            if key == "tg_ws_proxy":
                item["snapshot_dir"] = "data/upstreams/tg-ws-proxy"
            elif key == "flowseal":
                item["snapshot_dir"] = "data/upstreams/flowseal-zapret-discord-youtube"
            elif key == "zapret2":
                item["target_dir"] = "zapret/blockcheck/zapret2"

    write_json(dst, state)


def main():
    if RELEASE_ROOT.exists():
        shutil.rmtree(RELEASE_ROOT)

    (RELEASE_DATA / "logs").mkdir(parents=True, exist_ok=True)
    (RELEASE_DATA / "custom-lists").mkdir(parents=True, exist_ok=True)
    (RELEASE_DATA / "upstreams").mkdir(parents=True, exist_ok=True)

    copytree_if_exists(
        SRC_DATA / "upstreams" / "flowseal-zapret-discord-youtube",
        RELEASE_DATA / "upstreams" / "flowseal-zapret-discord-youtube",
    )
    copytree_if_exists(
        SRC_DATA / "upstreams" / "tg-ws-proxy",
        RELEASE_DATA / "upstreams" / "tg-ws-proxy",
    )

    prepare_upstream_state(
        SRC_DATA / "upstream_state.json",
        RELEASE_DATA / "upstream_state.json",
    )

    if (SRC_DATA / "targets.json").is_file():
        shutil.copy2(SRC_DATA / "targets.json", RELEASE_DATA / "targets.json")

    write_json(RELEASE_DATA / "release_manifest.json", {
        "profile": "portable-full",
        "includes": [
            "zapret bundle",
            "zapret2 upstream overlay",
            "flowseal snapshot",
            "tg-ws-proxy snapshot",
        ],
        "first_run_download_required": False,
    })

    print(f"Prepared release assets in: {RELEASE_ROOT}")


if __name__ == "__main__":
    main()
