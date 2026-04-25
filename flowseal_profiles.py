"""
Helpers for exact Flowseal batch-based presets.

The app ships simplified Flowseal presets inside generator.py for winws2 tests,
but some upstream strategies (notably ALT11) only work correctly with the
original winws.exe command line and the companion bin/lists snapshot.
"""

import logging
import os
import re
import sys

log = logging.getLogger("flowseal_profiles")

if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FLOWSEAL_SNAPSHOT_DIR = os.path.join(
    SCRIPT_DIR, "data", "upstreams", "flowseal-zapret-discord-youtube"
)

FLOWSEAL_BATCH_MAP = {
    "Flowseal: multisplit seqovl=681": "general.bat",
    "Flowseal ALT: fake+fakedsplit ts": "general (ALT).bat",
    "Flowseal ALT2: multisplit seqovl=652": "general (ALT2).bat",
    "Flowseal ALT3: autottl + md5sig/badseq": "general (ALT3).bat",
    "Flowseal ALT5: syndata+multidisorder": "general (ALT5).bat",
    "Flowseal ALT6: fake md5sig + disorder": "general (ALT6).bat",
    "Flowseal ALT7: fake ts + multisplit": "general (ALT7).bat",
    "Flowseal ALT9: hostfakesplit": "general (ALT9).bat",
    "Flowseal ALT10: simple fake ts": "general (ALT10).bat",
    "Flowseal ALT11: fake+multisplit double": "general (ALT11).bat",
    "Flowseal FAKE TLS AUTO: rnd+dupsid": "general (FAKE TLS AUTO).bat",
    "Flowseal FAKE TLS AUTO ALT: fakedsplit": "general (FAKE TLS AUTO ALT).bat",
    "Flowseal SIMPLE FAKE": "general (SIMPLE FAKE).bat",
}

_START_RE = re.compile(
    r'^start\s+"[^"]*"\s+(?:/min\s+)?"(?P<exe>[^"]*winws\.exe)"\s+(?P<args>.+)$',
    re.IGNORECASE,
)
_FILTER_KEYS = ("--filter-tcp=", "--filter-udp=")
_LIST_KEYS = ("--wf-tcp=", "--wf-udp=", "--filter-tcp=", "--filter-udp=")


def has_flowseal_snapshot() -> bool:
    return os.path.isdir(FLOWSEAL_SNAPSHOT_DIR)


def get_batch_path(preset_name: str) -> str:
    filename = FLOWSEAL_BATCH_MAP.get(preset_name, "")
    if not filename:
        return ""
    path = os.path.join(FLOWSEAL_SNAPSHOT_DIR, filename)
    return path if os.path.isfile(path) else ""


def _join_caret_lines(lines) -> list:
    joined = []
    current = ""
    for raw in lines:
        line = raw.rstrip("\r\n").strip()
        if not line:
            continue
        if line.endswith("^"):
            current += line[:-1].rstrip() + " "
            continue
        current += line
        joined.append(current.strip())
        current = ""
    if current:
        joined.append(current.strip())
    return joined


def _split_cmdline(text: str) -> list:
    tokens = []
    current = []
    in_quotes = False
    for ch in text:
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
        elif ch.isspace() and not in_quotes:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current))
    return tokens


def _normalize_token(token: str) -> str:
    for key in _LIST_KEYS:
        if token.startswith(key):
            value = token.split("=", 1)[1].strip().strip(",")
            value = re.sub(r",+", ",", value)
            return f"{key}{value}"
    return token


def _split_global_and_chains(tokens: list) -> tuple:
    first_filter_idx = next(
        (i for i, token in enumerate(tokens) if token.startswith("--filter-")),
        None,
    )
    if first_filter_idx is None:
        return [_normalize_token(token) for token in tokens], []

    global_tokens = [_normalize_token(token) for token in tokens[:first_filter_idx]]
    chains = []
    current = []
    for token in tokens[first_filter_idx:]:
        if token == "--new":
            if current:
                chains.append(current)
                current = []
        else:
            current.append(_normalize_token(token))
    if current:
        chains.append(current)
    return global_tokens, chains


def _is_valid_chain(tokens: list) -> bool:
    has_filter = False
    for token in tokens:
        if token.startswith(_FILTER_KEYS):
            has_filter = True
            value = token.split("=", 1)[1].strip().strip(",")
            if not value:
                return False
    return has_filter


def build_flowseal_runtime_profile(preset_name: str, desc: str = ""):
    batch_path = get_batch_path(preset_name)
    if not batch_path:
        return None

    try:
        with open(batch_path, encoding="utf-8-sig", errors="ignore") as f:
            lines = _join_caret_lines(f.readlines())

        start_line = next(
            (
                line
                for line in lines
                if line.lower().startswith("start ") and "winws.exe" in line.lower()
            ),
            "",
        )
        if not start_line:
            raise ValueError("start line with winws.exe not found")

        bin_dir = os.path.join(FLOWSEAL_SNAPSHOT_DIR, "bin") + os.sep
        lists_dir = os.path.join(FLOWSEAL_SNAPSHOT_DIR, "lists") + os.sep
        command = start_line
        command = command.replace("%BIN%", bin_dir)
        command = command.replace("%LISTS%", lists_dir)
        command = command.replace("%GameFilterTCP%", "")
        command = command.replace("%GameFilterUDP%", "")

        match = _START_RE.match(command)
        if not match:
            raise ValueError("failed to parse start command")

        binary = match.group("exe")
        args_text = match.group("args")
        tokens = _split_cmdline(args_text)
        global_tokens, chains = _split_global_and_chains(tokens)

        valid_chains = []
        dropped = 0
        for chain in chains:
            if _is_valid_chain(chain):
                valid_chains.append(chain)
            else:
                dropped += 1

        args = list(global_tokens)
        for index, chain in enumerate(valid_chains):
            if index:
                args.append("--new")
            args.extend(chain)

        if not os.path.isfile(binary):
            raise FileNotFoundError(binary)

        return {
            "name": preset_name,
            "desc": desc,
            "args": args,
            "binary": binary,
            "batch_path": batch_path,
            "dropped_chains": dropped,
            "snapshot_dir": FLOWSEAL_SNAPSHOT_DIR,
        }
    except Exception as e:
        log.warning("Failed to build exact Flowseal profile %s: %s", preset_name, e)
        return None
