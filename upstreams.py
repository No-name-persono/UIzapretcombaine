import datetime
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
import zipfile
from urllib import request, error as urlerror


if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
UPSTREAMS_DIR = os.path.join(DATA_DIR, "upstreams")
UPSTREAM_STATE_FILE = os.path.join(DATA_DIR, "upstream_state.json")

ZAPRET_DIR = os.path.join(SCRIPT_DIR, "zapret")
ZAPRET2_DIR = os.path.join(ZAPRET_DIR, "blockcheck", "zapret2")
TG_PROXY_UPSTREAM_DIR = os.path.join(UPSTREAMS_DIR, "tg-ws-proxy")

GITHUB_API_ROOT = "https://api.github.com"
USER_AGENT = "Zapret2Manager/1.2"

ZAPRET_REPO = "bol-van/zapret-win-bundle"
ZAPRET2_REPO = "bol-van/zapret2"
TG_PROXY_REPO = "Flowseal/tg-ws-proxy"
FLOWSEAL_REPO = "Flowseal/zapret-discord-youtube"
ZAPRET_REQUIRED_FILES = (
    "zapret-winws/winws2.exe",
    "zapret-winws/WinDivert.dll",
    "zapret-winws/WinDivert64.sys",
    "blockcheck/blockcheck2.cmd",
    "blockcheck/zapret2/blockcheck2.sh",
)
ZAPRET2_PRESERVE_FILES = (
    # The standalone zapret2 repo ships sources/scripts, while the Windows
    # bundle supplies these ready-to-run binaries used by blockcheck2.
    "nfq2/winws2.exe",
    "nfq2/WinDivert.dll",
    "nfq2/WinDivert64.sys",
    "ip2net/ip2net.exe",
    "mdig/mdig.exe",
    "blog.sh",
    "blog_kyber.sh",
)
ZAPRET2_REQUIRED_FILES = (
    "blockcheck2.sh",
    "lua/zapret-lib.lua",
    "nfq2/winws2.exe",
    "nfq2/WinDivert.dll",
    "nfq2/WinDivert64.sys",
    "ip2net/ip2net.exe",
    "mdig/mdig.exe",
)
TG_PROXY_INCLUDE = (
    "proxy/",
    "README.md",
    "LICENSE",
)
TG_PROXY_REQUIRED_FILES = (
    "proxy/tg_ws_proxy.py",
    "proxy/config.py",
    "proxy/fake_tls.py",
    "proxy/raw_websocket.py",
)
TG_PROXY_RUNTIME_ADAPTER_NOTE = "built-in tg_ws_proxy.py is adapted and is not blindly replaced"
TG_PROXY_UPSTREAM_ENTRY = "proxy/tg_ws_proxy.py"
FLOWSEAL_SNAPSHOT_DIR = os.path.join(UPSTREAMS_DIR, "flowseal-zapret-discord-youtube")
FLOWSEAL_INCLUDE = (
    "bin/",
    "lists/",
    "general.bat",
    "general (ALT).bat",
    "general (ALT2).bat",
    "general (ALT3).bat",
    "general (ALT5).bat",
    "general (ALT6).bat",
    "general (ALT7).bat",
    "general (ALT9).bat",
    "general (ALT10).bat",
    "general (ALT11).bat",
    "general (FAKE TLS AUTO).bat",
    "general (FAKE TLS AUTO ALT).bat",
    "general (SIMPLE FAKE).bat",
    "README.md",
    "LICENSE.txt",
)
FLOWSEAL_REQUIRED_FILES = (
    "general (ALT11).bat",
    "bin/winws.exe",
    "bin/WinDivert.dll",
    "bin/WinDivert64.sys",
    "lists/list-general.txt",
)

log = logging.getLogger("upstreams")


def _github_headers() -> dict:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    }


def _http_get_json(url: str, timeout: int = 30):
    req = request.Request(url, headers=_github_headers())
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_bytes(url: str, progress_cb=None, timeout: int = 120):
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        block = 65536
        data = bytearray()

        while True:
            chunk = resp.read(block)
            if not chunk:
                break
            data.extend(chunk)
            downloaded += len(chunk)
            if progress_cb and total > 0:
                pct = int(downloaded * 100 / total)
                progress_cb(pct, downloaded, total)

        return bytes(data)


def _repo_archive_url(repo: str, ref: str) -> str:
    owner, name = repo.split("/", 1)
    return f"https://codeload.github.com/{owner}/{name}/zip/{ref}"


def load_upstream_state() -> dict:
    if os.path.isfile(UPSTREAM_STATE_FILE):
        try:
            with open(UPSTREAM_STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            log.warning(f"Failed to load upstream state: {e}")
    return {}


def save_upstream_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(UPSTREAM_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _sanitize_rel_path(rel_path: str) -> str:
    rel_path = rel_path.replace("\\", "/").strip("/")
    if not rel_path:
        return ""
    normalized = os.path.normpath(rel_path)
    if os.path.isabs(normalized):
        raise ValueError(f"Absolute path in archive: {rel_path}")
    if normalized == ".." or normalized.startswith(".." + os.sep):
        raise ValueError(f"Unsafe path in archive: {rel_path}")
    return normalized


def _should_include_path(rel_path: str, include_prefixes) -> bool:
    if not include_prefixes:
        return True
    rel_path = rel_path.replace("\\", "/")
    for prefix in include_prefixes:
        if prefix.endswith("/"):
            if rel_path.startswith(prefix):
                return True
        elif rel_path == prefix:
            return True
    return False


def _extract_repo_archive(zip_data: bytes, payload_dir: str, include_prefixes=None) -> dict:
    os.makedirs(payload_dir, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        names = [name.replace("\\", "/") for name in zf.namelist() if name.strip()]
        roots = {name.split("/", 1)[0] for name in names}
        if len(roots) != 1:
            raise ValueError("Unexpected archive layout from upstream repository")
        root_prefix = roots.pop()

        files_written = 0
        dirs_written = 0

        for info in zf.infolist():
            raw_name = info.filename.replace("\\", "/")
            if raw_name == root_prefix or not raw_name.startswith(root_prefix + "/"):
                continue

            rel_name = raw_name[len(root_prefix) + 1:]
            if not rel_name:
                continue
            if not _should_include_path(rel_name, include_prefixes):
                continue

            target_rel = _sanitize_rel_path(rel_name)
            if not target_rel:
                continue

            target_path = os.path.join(payload_dir, target_rel)
            is_dir = info.is_dir() or raw_name.endswith("/")
            if is_dir:
                os.makedirs(target_path, exist_ok=True)
                dirs_written += 1
                continue

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with zf.open(info) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            files_written += 1

    return {"files": files_written, "dirs": dirs_written}


def _count_files(path: str) -> int:
    total = 0
    for _, _, files in os.walk(path):
        total += len(files)
    return total


def _copy_existing_paths(source_dir: str, target_dir: str, rel_paths) -> list:
    copied = []
    for rel_path in rel_paths:
        safe_rel = _sanitize_rel_path(rel_path)
        if not safe_rel:
            continue

        src = os.path.join(source_dir, safe_rel)
        dst = os.path.join(target_dir, safe_rel)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst, ignore_errors=True)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copytree(src, dst)
            copied.append(safe_rel)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(safe_rel)
    return copied


def _validate_required_files(root_dir: str, rel_paths, label: str):
    missing = [
        rel_path
        for rel_path in rel_paths
        if not os.path.isfile(os.path.join(root_dir, _sanitize_rel_path(rel_path)))
    ]
    if missing:
        raise FileNotFoundError(f"{label}: missing required files: {', '.join(missing)}")


def _is_component_metadata_current(component_dir: str, sha: str) -> bool:
    metadata_path = os.path.join(component_dir, "upstream_metadata.json")
    if not os.path.isfile(metadata_path):
        return False
    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
        return metadata.get("sha") == sha
    except Exception:
        return False


def _remote_error_result(component: str, label: str, exc: Exception) -> dict:
    log.error(f"{component} remote check failed: {traceback.format_exc()}")
    return {
        "component": component,
        "ok": False,
        "changed": False,
        "message": f"Ошибка проверки {label}: {exc}",
        "meta": {},
    }


def _replace_tree(target_dir: str, prepared_dir: str, keep_backup: bool = True) -> str:
    parent = os.path.dirname(target_dir)
    os.makedirs(parent, exist_ok=True)

    backup_dir = None
    if os.path.isdir(target_dir):
        backup_dir = f"{target_dir}_bak_{int(time.time())}"
        shutil.move(target_dir, backup_dir)

    try:
        shutil.move(prepared_dir, target_dir)
    except Exception:
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)
        if backup_dir and os.path.isdir(backup_dir):
            shutil.move(backup_dir, target_dir)
        raise

    if backup_dir and not keep_backup:
        shutil.rmtree(backup_dir, ignore_errors=True)
        backup_dir = None

    return backup_dir


def get_zapret_remote_info() -> dict:
    repo_info = _http_get_json(f"{GITHUB_API_ROOT}/repos/{ZAPRET_REPO}")
    branch = repo_info["default_branch"]
    commit_info = _http_get_json(f"{GITHUB_API_ROOT}/repos/{ZAPRET_REPO}/commits/{branch}")
    return {
        "repo": ZAPRET_REPO,
        "html_url": repo_info["html_url"],
        "branch": branch,
        "sha": commit_info["sha"],
        "commit_date": commit_info["commit"]["committer"]["date"],
        "archive_url": _repo_archive_url(ZAPRET_REPO, commit_info["sha"]),
    }


def get_zapret2_remote_info() -> dict:
    repo_info = _http_get_json(f"{GITHUB_API_ROOT}/repos/{ZAPRET2_REPO}")
    branch = repo_info["default_branch"]
    commit_info = _http_get_json(f"{GITHUB_API_ROOT}/repos/{ZAPRET2_REPO}/commits/{branch}")
    return {
        "repo": ZAPRET2_REPO,
        "html_url": repo_info["html_url"],
        "branch": branch,
        "sha": commit_info["sha"],
        "commit_date": commit_info["commit"]["committer"]["date"],
        "archive_url": _repo_archive_url(ZAPRET2_REPO, commit_info["sha"]),
    }


def get_tg_proxy_remote_info() -> dict:
    repo_info = _http_get_json(f"{GITHUB_API_ROOT}/repos/{TG_PROXY_REPO}")
    branch = repo_info["default_branch"]
    commit_info = _http_get_json(f"{GITHUB_API_ROOT}/repos/{TG_PROXY_REPO}/commits/{branch}")

    latest_release = None
    try:
        latest_release = _http_get_json(f"{GITHUB_API_ROOT}/repos/{TG_PROXY_REPO}/releases/latest")
    except urlerror.HTTPError as e:
        if e.code != 404:
            raise

    return {
        "repo": TG_PROXY_REPO,
        "html_url": repo_info["html_url"],
        "branch": branch,
        "sha": commit_info["sha"],
        "commit_date": commit_info["commit"]["committer"]["date"],
        "archive_url": _repo_archive_url(TG_PROXY_REPO, commit_info["sha"]),
        "release_tag": latest_release.get("tag_name") if latest_release else "",
        "release_date": latest_release.get("published_at") if latest_release else "",
    }


def sync_zapret_bundle(progress_cb=None) -> dict:
    state = load_upstream_state()
    try:
        remote = get_zapret_remote_info()
    except Exception as e:
        return _remote_error_result("zapret", "zapret", e)
    current = state.get("zapret", {})

    if current.get("sha") == remote["sha"] and os.path.isdir(ZAPRET_DIR):
        try:
            _validate_required_files(ZAPRET_DIR, ZAPRET_REQUIRED_FILES, "zapret")
            return {
                "component": "zapret",
                "ok": True,
                "changed": False,
                "message": f"zapret уже актуален ({remote['branch']}@{remote['sha'][:7]})",
                "meta": remote,
            }
        except Exception as e:
            log.warning(f"zapret state is current but runtime files are incomplete: {e}")

    os.makedirs(DATA_DIR, exist_ok=True)
    stage_root = tempfile.mkdtemp(prefix="zapret-sync-", dir=DATA_DIR)
    payload_dir = os.path.join(stage_root, "payload")

    try:
        zip_data = _download_bytes(remote["archive_url"], progress_cb=progress_cb)
        stats = _extract_repo_archive(zip_data, payload_dir)
        _validate_required_files(payload_dir, ZAPRET_REQUIRED_FILES, "zapret")
        backup_dir = _replace_tree(ZAPRET_DIR, payload_dir)

        state["zapret"] = {
            **remote,
            "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "backup_dir": backup_dir or "",
            "files": stats["files"],
        }
        save_upstream_state(state)

        backup_note = f", backup: {backup_dir}" if backup_dir else ""
        return {
            "component": "zapret",
            "ok": True,
            "changed": True,
            "message": (
                f"zapret обновлён до {remote['branch']}@{remote['sha'][:7]} "
                f"({stats['files']} files{backup_note})"
            ),
            "meta": remote,
        }
    except Exception as e:
        log.error(f"zapret sync failed: {traceback.format_exc()}")
        return {
            "component": "zapret",
            "ok": False,
            "changed": False,
            "message": f"Ошибка обновления zapret: {e}",
            "meta": remote,
        }
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def sync_zapret2_blockcheck(progress_cb=None) -> dict:
    state = load_upstream_state()
    try:
        remote = get_zapret2_remote_info()
    except Exception as e:
        return _remote_error_result("zapret2", "zapret2", e)
    current = state.get("zapret2", {})

    already_synced = (
        current.get("sha") == remote["sha"]
        and os.path.isdir(ZAPRET2_DIR)
        and _is_component_metadata_current(ZAPRET2_DIR, remote["sha"])
    )
    if already_synced:
        try:
            _validate_required_files(ZAPRET2_DIR, ZAPRET2_REQUIRED_FILES, "zapret2")
            return {
                "component": "zapret2",
                "ok": True,
                "changed": False,
                "message": f"zapret2 уже актуален ({remote['branch']}@{remote['sha'][:7]})",
                "meta": remote,
            }
        except Exception as e:
            log.warning(f"zapret2 metadata is current but runtime files are incomplete: {e}")

    os.makedirs(DATA_DIR, exist_ok=True)
    stage_root = tempfile.mkdtemp(prefix="zapret2-sync-", dir=DATA_DIR)
    payload_dir = os.path.join(stage_root, "payload")

    try:
        zip_data = _download_bytes(remote["archive_url"], progress_cb=progress_cb)
        _extract_repo_archive(zip_data, payload_dir)
        preserved = _copy_existing_paths(ZAPRET2_DIR, payload_dir, ZAPRET2_PRESERVE_FILES)
        _validate_required_files(payload_dir, ZAPRET2_REQUIRED_FILES, "zapret2")

        metadata_path = os.path.join(payload_dir, "upstream_metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    **remote,
                    "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "mode": "standalone_zapret2_overlay",
                    "preserved_windows_files": preserved,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        backup_dir = _replace_tree(ZAPRET2_DIR, payload_dir, keep_backup=False)
        file_count = _count_files(ZAPRET2_DIR)

        state["zapret2"] = {
            **remote,
            "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "backup_dir": backup_dir or "",
            "target_dir": ZAPRET2_DIR,
            "files": file_count,
            "mode": "standalone_zapret2_overlay",
            "preserved_windows_files": preserved,
        }
        save_upstream_state(state)

        return {
            "component": "zapret2",
            "ok": True,
            "changed": True,
            "message": (
                f"zapret2 обновлён до {remote['branch']}@{remote['sha'][:7]}; "
                f"Windows-бинарники сохранены из zapret-win-bundle ({len(preserved)} files)"
            ),
            "meta": remote,
        }
    except Exception as e:
        log.error(f"zapret2 sync failed: {traceback.format_exc()}")
        return {
            "component": "zapret2",
            "ok": False,
            "changed": False,
            "message": f"Ошибка обновления zapret2: {e}",
            "meta": remote,
        }
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def sync_tg_proxy_upstream(progress_cb=None) -> dict:
    state = load_upstream_state()
    try:
        remote = get_tg_proxy_remote_info()
    except Exception as e:
        return _remote_error_result("tg_ws_proxy", "tg-ws-proxy upstream", e)
    current = state.get("tg_ws_proxy", {})

    if current.get("sha") == remote["sha"] and os.path.isdir(TG_PROXY_UPSTREAM_DIR):
        try:
            _validate_required_files(TG_PROXY_UPSTREAM_DIR, TG_PROXY_REQUIRED_FILES, "tg-ws-proxy")
            if (
                current.get("runtime_adapter") != TG_PROXY_RUNTIME_ADAPTER_NOTE
                or current.get("upstream_entry") != TG_PROXY_UPSTREAM_ENTRY
                or current.get("snapshot_dir") != TG_PROXY_UPSTREAM_DIR
            ):
                state["tg_ws_proxy"] = {
                    **current,
                    **remote,
                    "synced_at": current.get("synced_at")
                    or datetime.datetime.now().isoformat(timespec="seconds"),
                    "backup_dir": current.get("backup_dir", ""),
                    "snapshot_dir": TG_PROXY_UPSTREAM_DIR,
                    "files": current.get("files") or _count_files(TG_PROXY_UPSTREAM_DIR),
                    "mode": "staged_upstream_snapshot",
                    "runtime_adapter": TG_PROXY_RUNTIME_ADAPTER_NOTE,
                    "upstream_entry": TG_PROXY_UPSTREAM_ENTRY,
                }
                save_upstream_state(state)

                metadata_path = os.path.join(TG_PROXY_UPSTREAM_DIR, "metadata.json")
                try:
                    metadata = {}
                    if os.path.isfile(metadata_path):
                        with open(metadata_path, encoding="utf-8") as f:
                            metadata = json.load(f)
                    metadata.update(
                        {
                            **remote,
                            "synced_at": state["tg_ws_proxy"]["synced_at"],
                            "mode": "staged_upstream_snapshot",
                            "runtime_adapter": TG_PROXY_RUNTIME_ADAPTER_NOTE,
                            "upstream_entry": TG_PROXY_UPSTREAM_ENTRY,
                            "include": list(TG_PROXY_INCLUDE),
                            "files": state["tg_ws_proxy"]["files"],
                        }
                    )
                    with open(metadata_path, "w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    log.warning(f"Failed to backfill tg-ws-proxy metadata: {e}")

            release = remote["release_tag"] or f"{remote['branch']}@{remote['sha'][:7]}"
            return {
                "component": "tg_ws_proxy",
                "ok": True,
                "changed": False,
                "message": f"tg-ws-proxy upstream уже синхронизирован ({release})",
                "meta": remote,
            }
        except Exception as e:
            log.warning(f"tg-ws-proxy state is current but snapshot is incomplete: {e}")

    os.makedirs(UPSTREAMS_DIR, exist_ok=True)
    stage_root = tempfile.mkdtemp(prefix="tg-proxy-sync-", dir=UPSTREAMS_DIR)
    payload_dir = os.path.join(stage_root, "payload")

    try:
        zip_data = _download_bytes(remote["archive_url"], progress_cb=progress_cb)
        stats = _extract_repo_archive(zip_data, payload_dir, include_prefixes=TG_PROXY_INCLUDE)
        _validate_required_files(payload_dir, TG_PROXY_REQUIRED_FILES, "tg-ws-proxy")

        metadata_path = os.path.join(payload_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    **remote,
                    "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "mode": "staged_upstream_snapshot",
                    "runtime_adapter": TG_PROXY_RUNTIME_ADAPTER_NOTE,
                    "upstream_entry": TG_PROXY_UPSTREAM_ENTRY,
                    "include": list(TG_PROXY_INCLUDE),
                    "files": stats["files"],
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        backup_dir = _replace_tree(TG_PROXY_UPSTREAM_DIR, payload_dir)

        state["tg_ws_proxy"] = {
            **remote,
            "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "backup_dir": backup_dir or "",
            "snapshot_dir": TG_PROXY_UPSTREAM_DIR,
            "files": stats["files"],
            "mode": "staged_upstream_snapshot",
            "runtime_adapter": TG_PROXY_RUNTIME_ADAPTER_NOTE,
            "upstream_entry": TG_PROXY_UPSTREAM_ENTRY,
        }
        save_upstream_state(state)

        release = remote["release_tag"] or f"{remote['branch']}@{remote['sha'][:7]}"
        return {
            "component": "tg_ws_proxy",
            "ok": True,
            "changed": True,
            "message": (
                f"tg-ws-proxy upstream синхронизирован до {release}; "
                f"snapshot сохранён в {TG_PROXY_UPSTREAM_DIR}"
            ),
            "meta": remote,
        }
    except Exception as e:
        log.error(f"tg-ws-proxy sync failed: {traceback.format_exc()}")
        return {
            "component": "tg_ws_proxy",
            "ok": False,
            "changed": False,
            "message": f"Ошибка синхронизации tg-ws-proxy upstream: {e}",
            "meta": remote,
        }
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def get_flowseal_remote_info() -> dict:
    repo_info = _http_get_json(f"{GITHUB_API_ROOT}/repos/{FLOWSEAL_REPO}")
    branch = repo_info["default_branch"]
    commit_info = _http_get_json(f"{GITHUB_API_ROOT}/repos/{FLOWSEAL_REPO}/commits/{branch}")
    return {
        "repo": FLOWSEAL_REPO,
        "html_url": repo_info["html_url"],
        "branch": branch,
        "sha": commit_info["sha"],
        "commit_date": commit_info["commit"]["committer"]["date"],
        "archive_url": _repo_archive_url(FLOWSEAL_REPO, commit_info["sha"]),
    }


def sync_flowseal_strategy_repo(progress_cb=None) -> dict:
    state = load_upstream_state()
    try:
        remote = get_flowseal_remote_info()
    except Exception as e:
        return _remote_error_result("flowseal", "Flowseal strategies", e)
    current = state.get("flowseal", {})

    if current.get("sha") == remote["sha"] and os.path.isdir(FLOWSEAL_SNAPSHOT_DIR):
        try:
            _validate_required_files(FLOWSEAL_SNAPSHOT_DIR, FLOWSEAL_REQUIRED_FILES, "flowseal")
            return {
                "component": "flowseal",
                "ok": True,
                "changed": False,
                "message": f"Flowseal strategies уже синхронизированы ({remote['branch']}@{remote['sha'][:7]})",
                "meta": remote,
            }
        except Exception as e:
            log.warning(f"Flowseal state is current but snapshot is incomplete: {e}")

    os.makedirs(UPSTREAMS_DIR, exist_ok=True)
    stage_root = tempfile.mkdtemp(prefix="flowseal-sync-", dir=UPSTREAMS_DIR)
    payload_dir = os.path.join(stage_root, "payload")

    try:
        zip_data = _download_bytes(remote["archive_url"], progress_cb=progress_cb)
        stats = _extract_repo_archive(zip_data, payload_dir, include_prefixes=FLOWSEAL_INCLUDE)

        lists_dir = os.path.join(payload_dir, "lists")
        os.makedirs(lists_dir, exist_ok=True)
        for filename in (
            "list-general-user.txt",
            "list-exclude-user.txt",
            "ipset-exclude-user.txt",
        ):
            placeholder = os.path.join(lists_dir, filename)
            if not os.path.exists(placeholder):
                open(placeholder, "w", encoding="utf-8").close()
        _validate_required_files(payload_dir, FLOWSEAL_REQUIRED_FILES, "flowseal")

        metadata_path = os.path.join(payload_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    **remote,
                    "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "mode": "flowseal_strategy_snapshot",
                    "include": list(FLOWSEAL_INCLUDE),
                    "files": stats["files"],
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        backup_dir = _replace_tree(FLOWSEAL_SNAPSHOT_DIR, payload_dir)

        state["flowseal"] = {
            **remote,
            "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "backup_dir": backup_dir or "",
            "snapshot_dir": FLOWSEAL_SNAPSHOT_DIR,
            "files": stats["files"],
            "mode": "flowseal_strategy_snapshot",
        }
        save_upstream_state(state)

        return {
            "component": "flowseal",
            "ok": True,
            "changed": True,
            "message": (
                f"Flowseal strategies синхронизированы до "
                f"{remote['branch']}@{remote['sha'][:7]}; snapshot сохранён в {FLOWSEAL_SNAPSHOT_DIR}"
            ),
            "meta": remote,
        }
    except Exception as e:
        log.error(f"Flowseal sync failed: {traceback.format_exc()}")
        return {
            "component": "flowseal",
            "ok": False,
            "changed": False,
            "message": f"Ошибка синхронизации Flowseal strategies: {e}",
            "meta": remote,
        }
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def sync_external_components(progress_cb=None) -> list:
    sync_steps = (
        ("zapret", sync_zapret_bundle),
        ("zapret2", sync_zapret2_blockcheck),
        ("tg_ws_proxy", sync_tg_proxy_upstream),
        ("flowseal", sync_flowseal_strategy_repo),
    )
    results = []
    for component, sync_fn in sync_steps:
        try:
            results.append(sync_fn(progress_cb=progress_cb))
        except Exception as e:
            log.error(f"{component} sync crashed: {traceback.format_exc()}")
            results.append(
                {
                    "component": component,
                    "ok": False,
                    "changed": False,
                    "message": f"Непредвиденная ошибка синхронизации: {e}",
                    "meta": {},
                }
            )
    return results
