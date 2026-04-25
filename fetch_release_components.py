import json
import sys

from upstreams import sync_external_components


def main() -> int:
    print("[*] Syncing release runtime components from upstream repositories...")
    results = sync_external_components()
    print(json.dumps(results, indent=2, ensure_ascii=False))

    failed = [item for item in results if not item.get("ok")]
    if failed:
        names = ", ".join(item.get("component", "unknown") for item in failed)
        print(f"[!] Failed to sync required release components: {names}", file=sys.stderr)
        return 1

    print("[*] Release runtime components are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
