"""
core.py — Логика Zapret2 Manager
Bootstrap (скачивание/распаковка), Backend (запуск winws2), Profile (конфиги)
"""

import os
import sys
import subprocess
import shutil
import json
import datetime
import time
import re
import zipfile
import io
import ctypes
import traceback
import logging
from pathlib import Path
from urllib import request, error as urlerror

from flowseal_profiles import build_flowseal_runtime_profile

# Windows Job Object — для принудительного убийства дерева процессов
if sys.platform == "win32":
    import ctypes.wintypes as wt

    _kernel32 = ctypes.windll.kernel32

    def create_job_object():
        """Создаёт Windows Job Object. Все процессы в нём умрут при закрытии."""
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        # Настраиваем: при закрытии job handle — убить все процессы
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [("v", ctypes.c_uint64 * 6)]
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _kernel32.SetInformationJobObject(
            job, 9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info), ctypes.sizeof(info)
        )
        return job

    def assign_process_to_job(job, process_handle):
        """Добавляет процесс в Job Object."""
        return _kernel32.AssignProcessToJobObject(job, process_handle)

    def terminate_job(job, exit_code=1):
        """Убивает ВСЕ процессы в Job Object."""
        _kernel32.TerminateJobObject(job, exit_code)
        _kernel32.CloseHandle(job)
else:
    def create_job_object(): return None
    def assign_process_to_job(j, h): pass
    def terminate_job(j, c=1): pass

# ──────────────────────────────────────────────────────
#  ЛОГИРОВАНИЕ
# ──────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
LOG_DIR = os.path.join(DATA_DIR, "logs")
CUSTOM_LISTS_DIR = os.path.join(DATA_DIR, "custom-lists")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")

ZAPRET_DIR = os.path.join(SCRIPT_DIR, "zapret")
WINWS_DIR = os.path.join(ZAPRET_DIR, "zapret-winws")
LUA_DIR = os.path.join(WINWS_DIR, "lua")
FILES_DIR = os.path.join(WINWS_DIR, "files")

BUNDLE_ZIP_URL = "https://github.com/bol-van/zapret-win-bundle/archive/refs/heads/master.zip"
BUNDLE_INNER_DIR = "zapret-win-bundle-master"

APP_NAME = "Zapret2 Manager"
APP_VERSION = "1.2.0"

# Создаём папки для логов заранее
for _d in [DATA_DIR, LOG_DIR, CUSTOM_LISTS_DIR]:
    os.makedirs(_d, exist_ok=True)

# Настраиваем логирование в файл + консоль
_log_file = os.path.join(LOG_DIR, f"manager_{datetime.date.today()}.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("core")
log.info("=" * 60)
log.info(f"{APP_NAME} v{APP_VERSION} запущен")
log.info(f"Python: {sys.version}")
log.info(f"Platform: {sys.platform}")
log.info(f"Script dir: {SCRIPT_DIR}")
log.info(f"Log file: {_log_file}")

WINDOWS_CLI_TEXT_KW = {"text": True}
if sys.platform == "win32":
    # Windows console tools (tasklist/taskkill) emit OEM-encoded output.
    WINDOWS_CLI_TEXT_KW.update({"encoding": "oem", "errors": "replace"})

ENGINE_EXECUTABLES = (
    "winws2.exe",
    "winws.exe",
    "nfqws2.exe",
    "nfqws.exe",
    "tpws2.exe",
    "tpws.exe",
)
AUTOSTART_TASK_NAME = f"{APP_NAME} Autostart"
AUTO_SYNC_INTERVAL_DAYS = 30


def kill_process_images(image_names=ENGINE_EXECUTABLES, timeout: int = 10, logger=None) -> list:
    """Force-kill known zapret engine processes by image name."""
    messages = []
    for image_name in image_names:
        try:
            r = subprocess.run(
                ["taskkill", "/T", "/F", "/IM", image_name],
                capture_output=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                **WINDOWS_CLI_TEXT_KW,
            )
            stdout = (r.stdout or "").strip()
            stderr = (r.stderr or "").strip()
            msg = f"taskkill {image_name}: returncode={r.returncode}, stdout={stdout}, stderr={stderr}"
            messages.append(msg)
            if logger:
                logger.info(msg)
        except Exception as e:
            msg = f"taskkill {image_name}: {e}"
            messages.append(msg)
            if logger:
                logger.warning(msg)
    return messages


def is_admin() -> bool:
    try:
        result = ctypes.windll.shell32.IsUserAnAdmin() != 0
        log.info(f"Admin check: {result}")
        return result
    except Exception as e:
        log.warning(f"Admin check failed: {e}")
        return False


def request_admin():
    """Перезапуск с правами администратора."""
    if is_admin():
        return True
    log.info("Requesting admin elevation...")
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            f'"{os.path.abspath(sys.argv[0])}"',
            SCRIPT_DIR, 1
        )
        sys.exit(0)
    except Exception as e:
        log.error(f"Failed to elevate: {e}")
        return False


def _preferred_gui_python() -> str:
    exe = os.path.abspath(sys.executable)
    base, name = os.path.split(exe)
    if name.lower() == "python.exe":
        candidate = os.path.join(base, "pythonw.exe")
        if os.path.isfile(candidate):
            return candidate
    return exe


def _autostart_task_command() -> str:
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([os.path.abspath(sys.executable)])

    return subprocess.list2cmdline([
        _preferred_gui_python(),
        os.path.join(SCRIPT_DIR, "main.py"),
    ])


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", AUTOSTART_TASK_NAME],
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            **WINDOWS_CLI_TEXT_KW,
        )
        enabled = result.returncode == 0
        log.info(f"Autostart enabled: {enabled}")
        return enabled
    except Exception as e:
        log.warning(f"Autostart query failed: {e}")
        return False


def set_autostart_enabled(enabled: bool) -> tuple:
    if sys.platform != "win32":
        return False, "Автозапуск поддерживается только на Windows"

    try:
        if enabled:
            task_cmd = _autostart_task_command()
            result = subprocess.run(
                [
                    "schtasks",
                    "/Create",
                    "/F",
                    "/SC",
                    "ONLOGON",
                    "/RL",
                    "HIGHEST",
                    "/TN",
                    AUTOSTART_TASK_NAME,
                    "/TR",
                    task_cmd,
                ],
                capture_output=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                **WINDOWS_CLI_TEXT_KW,
            )
            if result.returncode != 0:
                stdout = (result.stdout or "").strip()
                stderr = (result.stderr or "").strip()
                msg = stderr or stdout or "Не удалось создать задачу автозапуска"
                log.error(f"Autostart create failed: {msg}")
                return False, msg
            if not is_autostart_enabled():
                return False, "Задача автозапуска не появилась в Планировщике"
            return True, "Автозапуск включён (Планировщик задач Windows)"

        result = subprocess.run(
            ["schtasks", "/Delete", "/F", "/TN", AUTOSTART_TASK_NAME],
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            **WINDOWS_CLI_TEXT_KW,
        )
        if result.returncode != 0 and is_autostart_enabled():
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            msg = stderr or stdout or "Не удалось отключить автозапуск"
            log.error(f"Autostart delete failed: {msg}")
            return False, msg
        return True, "Автозапуск отключён"
    except Exception as e:
        log.error(f"Autostart toggle failed: {e}")
        return False, str(e)


def parse_saved_datetime(value: str):
    if not value:
        return None
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def is_monthly_auto_sync_due(settings: dict, now: datetime.datetime = None) -> bool:
    if not settings.get("monthly_auto_sync", True):
        return False

    now = now or datetime.datetime.now()
    latest = None
    for key in ("last_auto_sync_check", "last_update"):
        parsed = parse_saved_datetime(settings.get(key, ""))
        if parsed and (latest is None or parsed > latest):
            latest = parsed

    if latest is None:
        return True

    return (now - latest) >= datetime.timedelta(days=AUTO_SYNC_INTERVAL_DAYS)


# ──────────────────────────────────────────────────────
#  BOOTSTRAP: скачивание и установка zapret-win-bundle
# ──────────────────────────────────────────────────────
class Bootstrap:

    def __init__(self):
        self.log = logging.getLogger("bootstrap")
        self.log.info("Bootstrap initialized")
        self.log.info(f"  ZAPRET_DIR = {ZAPRET_DIR}")
        self.log.info(f"  WINWS_DIR  = {WINWS_DIR}")
        self.log.info(f"  LUA_DIR    = {LUA_DIR}")

    def check_bundle(self) -> bool:
        """Проверяет наличие winws2.exe."""
        path = os.path.join(WINWS_DIR, "winws2.exe")
        exists = os.path.isfile(path)
        self.log.info(f"check_bundle: winws2.exe exists = {exists} ({path})")
        if not exists:
            # Пробуем найти где-то в zapret/
            self.log.info("Searching for winws2.exe in zapret tree...")
            for root, dirs, files in os.walk(ZAPRET_DIR):
                for f in files:
                    self.log.debug(f"  found: {os.path.join(root, f)}")
                    if f == "winws2.exe":
                        self.log.info(f"  FOUND winws2.exe at {root}")
                        return True
                # Ограничиваем глубину
                if root.count(os.sep) - ZAPRET_DIR.count(os.sep) > 3:
                    break
        return exists

    def check_windivert(self) -> bool:
        dll = os.path.isfile(os.path.join(WINWS_DIR, "WinDivert.dll"))
        sys_f = os.path.isfile(os.path.join(WINWS_DIR, "WinDivert64.sys"))
        self.log.info(f"check_windivert: dll={dll}, sys={sys_f}")
        return dll and sys_f

    def find_winws2(self) -> str:
        """Находит winws2.exe."""
        primary = os.path.join(WINWS_DIR, "winws2.exe")
        if os.path.isfile(primary):
            self.log.info(f"find_winws2: {primary}")
            return primary
        # Поиск по дереву
        for root, dirs, files in os.walk(ZAPRET_DIR):
            if "winws2.exe" in files:
                path = os.path.join(root, "winws2.exe")
                self.log.info(f"find_winws2 (search): {path}")
                return path
        self.log.warning(f"find_winws2: NOT FOUND, returning default {primary}")
        return primary

    def find_lua_dir(self) -> str:
        for p in [LUA_DIR, os.path.join(WINWS_DIR, "lua"),
                  os.path.join(ZAPRET_DIR, "lua")]:
            if os.path.isdir(p):
                self.log.info(f"find_lua_dir: {p}")
                return p
        self.log.warning(f"find_lua_dir: NOT FOUND, returning {LUA_DIR}")
        return LUA_DIR

    def find_lists_dir(self) -> str:
        for p in [FILES_DIR, os.path.join(WINWS_DIR, "files"),
                  os.path.join(ZAPRET_DIR, "files")]:
            if os.path.isdir(p):
                self.log.info(f"find_lists_dir: {p}")
                return p
        self.log.warning(f"find_lists_dir: NOT FOUND, returning {FILES_DIR}")
        return FILES_DIR

    def download_bundle(self, progress_cb=None) -> tuple:
        """Скачивает ZIP с GitHub."""
        self.log.info(f"Downloading {BUNDLE_ZIP_URL}")
        try:
            req = request.Request(BUNDLE_ZIP_URL, headers={
                "User-Agent": "Mozilla/5.0 Zapret2Manager/1.2"
            })
            self.log.debug("Opening URL...")
            resp = request.urlopen(req, timeout=120)
            self.log.debug(f"Response status: {resp.status}")
            self.log.debug(f"Response headers: {dict(resp.headers)}")

            total = int(resp.headers.get("Content-Length", 0))
            self.log.info(f"Content-Length: {total} bytes")

            data = bytearray()
            block = 65536
            downloaded = 0

            while True:
                chunk = resp.read(block)
                if not chunk:
                    break
                data.extend(chunk)
                downloaded += len(chunk)
                if progress_cb and total > 0:
                    pct = int(downloaded * 100 / total)
                    try:
                        progress_cb(pct, downloaded, total)
                    except Exception as e:
                        self.log.warning(f"progress_cb error: {e}")

                # Логируем каждые ~5 MB
                if downloaded % (5 * 1048576) < block:
                    self.log.debug(f"Downloaded {downloaded / 1048576:.1f} MB / {total / 1048576:.1f} MB")

            resp.close()
            self.log.info(f"Download complete: {len(data)} bytes")
            return True, bytes(data)

        except urlerror.HTTPError as e:
            self.log.error(f"HTTP error: {e.code} {e.reason}")
            return False, f"HTTP {e.code}: {e.reason}"
        except urlerror.URLError as e:
            self.log.error(f"URL error: {e.reason}")
            return False, f"Ошибка сети: {e.reason}"
        except Exception as e:
            self.log.error(f"Download error: {traceback.format_exc()}")
            return False, str(e)

    def extract_bundle(self, zip_data: bytes) -> tuple:
        """Распаковывает ZIP."""
        self.log.info(f"Extracting ZIP ({len(zip_data)} bytes) → {ZAPRET_DIR}")
        try:
            # Бэкап
            if os.path.isdir(ZAPRET_DIR):
                backup = f"{ZAPRET_DIR}_bak_{int(time.time())}"
                self.log.info(f"Backing up existing: {ZAPRET_DIR} → {backup}")
                try:
                    shutil.move(ZAPRET_DIR, backup)
                except Exception as e:
                    self.log.warning(f"Backup failed: {e}, trying to remove")
                    shutil.rmtree(ZAPRET_DIR, ignore_errors=True)

            os.makedirs(ZAPRET_DIR, exist_ok=True)

            self.log.debug("Opening ZIP...")
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                namelist = zf.namelist()
                self.log.info(f"ZIP contains {len(namelist)} entries")

                # Показываем первые 20 для отладки
                for name in namelist[:20]:
                    self.log.debug(f"  ZIP entry: {name}")
                if len(namelist) > 20:
                    self.log.debug(f"  ... and {len(namelist) - 20} more")

                extracted = 0
                for member in namelist:
                    # Убираем верхнюю папку
                    if member.startswith(BUNDLE_INNER_DIR + "/"):
                        rel_path = member[len(BUNDLE_INNER_DIR) + 1:]
                    elif member.startswith(BUNDLE_INNER_DIR + "\\"):
                        rel_path = member[len(BUNDLE_INNER_DIR) + 1:]
                    else:
                        # Может быть без верхней папки
                        rel_path = member

                    if not rel_path:
                        continue

                    target = os.path.join(ZAPRET_DIR, rel_path.replace("/", os.sep))

                    if member.endswith("/") or member.endswith("\\"):
                        os.makedirs(target, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with zf.open(member) as src, open(target, "wb") as dst:
                            dst.write(src.read())
                        extracted += 1

                self.log.info(f"Extracted {extracted} files")

            # Логируем что получилось
            self.log.info("Listing extracted top-level:")
            if os.path.isdir(ZAPRET_DIR):
                for item in os.listdir(ZAPRET_DIR):
                    full = os.path.join(ZAPRET_DIR, item)
                    kind = "DIR" if os.path.isdir(full) else "FILE"
                    self.log.info(f"  [{kind}] {item}")

            # Проверяем winws
            if os.path.isdir(WINWS_DIR):
                self.log.info(f"Listing {WINWS_DIR}:")
                for item in os.listdir(WINWS_DIR):
                    self.log.info(f"  {item}")
            else:
                self.log.warning(f"WINWS_DIR not found: {WINWS_DIR}")
                # Ищем winws2.exe
                self.log.info("Searching for winws2.exe...")
                found = False
                for root, dirs, files in os.walk(ZAPRET_DIR):
                    for f in files:
                        if f == "winws2.exe":
                            self.log.info(f"  FOUND: {os.path.join(root, f)}")
                            found = True
                if not found:
                    self.log.error("winws2.exe NOT FOUND anywhere!")

            if self.check_bundle():
                return True, "OK: winws2.exe найден"
            else:
                return False, "winws2.exe не найден после распаковки"

        except zipfile.BadZipFile as e:
            self.log.error(f"Bad ZIP: {e}")
            return False, f"Повреждённый ZIP: {e}"
        except Exception as e:
            self.log.error(f"Extract error: {traceback.format_exc()}")
            return False, str(e)

    def update_bundle(self, progress_cb=None) -> tuple:
        """Скачать + распаковать."""
        ok, data = self.download_bundle(progress_cb)
        if not ok:
            return False, data
        return self.extract_bundle(data)

    def full_setup(self, step_cb=None, dl_progress_cb=None) -> list:
        """
        Полный цикл установки.
        step_cb(step_name, step_num, total) — перед каждым шагом
        dl_progress_cb(pct, downloaded, total) — прогресс скачивания
        """
        self.log.info("=== FULL SETUP START ===")
        steps = []
        total = 3

        # 1. Директории
        if step_cb:
            step_cb("Директории", 1, total)
        try:
            for d in [DATA_DIR, LOG_DIR, CUSTOM_LISTS_DIR]:
                os.makedirs(d, exist_ok=True)
            steps.append(("Директории", True, "OK"))
            self.log.info("Step 1 OK: directories")
        except Exception as e:
            steps.append(("Директории", False, str(e)))
            self.log.error(f"Step 1 FAIL: {e}")

        # 2. Скачивание + распаковка
        if step_cb:
            step_cb("Скачивание zapret-win-bundle", 2, total)
        if not self.check_bundle():
            self.log.info("Step 2: downloading bundle...")
            ok, data = self.download_bundle(progress_cb=dl_progress_cb)
            if ok:
                self.log.info("Step 2: download OK, extracting...")
                ok2, msg = self.extract_bundle(data)
                steps.append(("Скачивание и распаковка", ok2, msg))
                self.log.info(f"Step 2 extract: ok={ok2}, msg={msg}")
            else:
                steps.append(("Скачивание", False, str(data)))
                self.log.error(f"Step 2 FAIL download: {data}")
                return steps
        else:
            steps.append(("zapret-win-bundle", True, "Уже установлен"))
            self.log.info("Step 2 SKIP: already installed")

        # 3. Проверка
        if step_cb:
            step_cb("Проверка", 3, total)
        checks = []
        has_winws = self.check_bundle()
        has_wd = self.check_windivert()
        has_lua = os.path.isdir(self.find_lua_dir())
        checks.append(f"winws2 {'✓' if has_winws else '✗'}")
        checks.append(f"WinDivert {'✓' if has_wd else '✗'}")
        checks.append(f"Lua {'✓' if has_lua else '✗'}")
        all_ok = has_winws and has_wd
        steps.append(("Проверка", all_ok, ", ".join(checks)))
        self.log.info(f"Step 3: {', '.join(checks)}, all_ok={all_ok}")

        self.log.info("=== FULL SETUP END ===")
        return steps


# ──────────────────────────────────────────────────────
#  BACKEND: управление процессом winws2
# ──────────────────────────────────────────────────────
class Backend:
    def __init__(self, settings: dict):
        self.settings = settings
        self.process = None
        self._job_object = None
        self._running = False
        self.log = logging.getLogger("backend")
        self.log.info(f"Backend init, settings: {json.dumps(settings, ensure_ascii=False, indent=2)}")

    def _tasklist_has_process(self, image_name: str) -> bool:
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH"],
                capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                **WINDOWS_CLI_TEXT_KW
            )
            stdout = (r.stdout or "").lower()
            return image_name.lower() in stdout
        except Exception as e:
            self.log.debug(f"tasklist check error for {image_name}: {e}")
            return False

    def _resolve_binary(self, args: list, requested_binary: str = "") -> str:
        if requested_binary:
            return requested_binary

        configured = self.settings.get("winws_bin", "")
        wants_legacy = any("--dpi-desync" in arg for arg in args)
        if wants_legacy:
            search_dirs = []
            if configured:
                search_dirs.append(os.path.dirname(configured))
            if self.settings.get("winws_dir", ""):
                search_dirs.append(self.settings["winws_dir"])
            search_dirs.append(WINWS_DIR)

            checked = set()
            for directory in search_dirs:
                candidate = os.path.join(directory, "winws.exe")
                key = os.path.normcase(os.path.abspath(candidate))
                if key in checked:
                    continue
                checked.add(key)
                if os.path.isfile(candidate):
                    self.log.info(f"START selected legacy winws.exe: {candidate}")
                    return candidate

            if configured:
                return os.path.join(os.path.dirname(configured), "winws.exe")
            return os.path.join(WINWS_DIR, "winws.exe")

        return configured

    @property
    def is_running(self) -> bool:
        if self.process and self.process.poll() is None:
            return True
        try:
            return any(self._tasklist_has_process(name) for name in ENGINE_EXECUTABLES)
        except Exception as e:
            self.log.debug(f"is_running check error: {e}")
            return self._running

    def start(self, profile_or_args) -> tuple:
        """Запускает winws2.exe с аргументами."""
        profile = None
        if hasattr(profile_or_args, "args") and not isinstance(profile_or_args, (list, tuple)):
            profile = profile_or_args
            args = list(profile.args)
        else:
            args = list(profile_or_args)

        requested_binary = getattr(profile, "binary", "") if profile else ""
        winws = self._resolve_binary(args, requested_binary=requested_binary)
        engine_name = os.path.basename(winws) if winws else "winws"
        self.log.info(f"START: winws_bin={winws}")
        self.log.info(f"START: args={args}")

        if not winws or not os.path.isfile(winws):
            msg = f"{engine_name} не найден: {winws}"
            self.log.error(msg)
            return False, msg

        lua_dir = self.settings.get("lua_dir", "")
        work_dir = os.path.dirname(winws)
        self.log.info(f"START: lua_dir={lua_dir}, work_dir={work_dir}")

        # Подставляем ОТНОСИТЕЛЬНЫЕ пути к lua (cwd будет work_dir)
        # Это обходит проблему пробелов в абсолютных путях
        resolved = []
        for a in args:
            orig = a
            if "@zapret-" in a and lua_dir:
                # Вычисляем относительный путь от work_dir к lua файлу
                for lf in ["zapret-lib.lua", "zapret-antidpi.lua", "zapret-obfs.lua"]:
                    full_lua = os.path.join(lua_dir, lf)
                    try:
                        rel_lua = os.path.relpath(full_lua, work_dir)
                    except ValueError:
                        # Разные диски — используем абсолютный с кавычками
                        rel_lua = full_lua
                    a = a.replace(f"@{lf}", f"@{rel_lua}")
            if a != orig:
                self.log.debug(f"  resolved: {orig} -> {a}")
            resolved.append(a)

        # Умное разделение: если строка содержит несколько --param, разбиваем
        # но НЕ ломаем пути с пробелами
        flat = []
        for a in resolved:
            a = a.strip()
            if not a:
                continue
            # Считаем кол-во параметров (начинающихся с --)
            parts = a.split(" --")
            if len(parts) > 1:
                # Несколько параметров в одной строке: "--filter-tcp=80 --filter-l7=http"
                flat.append(parts[0].strip())
                for p in parts[1:]:
                    flat.append("--" + p.strip())
            else:
                flat.append(a)

        # Popen с СПИСКОМ на Windows сам квотирует аргументы.
        # Убираем shell-уровневые кавычки:
        #   --lua-init="code here"  → --lua-init=code here
        #   --wf-raw-part=@"path"   → --wf-raw-part=@path
        # Иначе Popen двойно экранирует, и winws2 получает мусор.
        cleaned = []
        for a in flat:
            orig = a
            # Паттерн: --key="value" → --key=value
            if '="' in a and a.endswith('"'):
                eq_pos = a.index('="')
                key = a[:eq_pos + 1]  # --lua-init=
                val = a[eq_pos + 2:-1]  # убираем " с обеих сторон
                a = key + val
            # Паттерн: --key=@"path" → --key=@path
            elif '=@"' in a and a.endswith('"'):
                at_pos = a.index('=@"')
                key = a[:at_pos + 2]  # --wf-raw-part=@
                val = a[at_pos + 3:-1]  # убираем " с обеих сторон
                a = key + val
            if a != orig:
                self.log.debug(f"  strip quotes: {repr(orig)} -> {repr(a)}")
            cleaned.append(a)

        self.log.info(f"START cleaned args ({len(cleaned)}):")
        for i, a in enumerate(cleaned):
            self.log.info(f"  [{i}] {repr(a)}")

        # Собираем список аргументов для Popen
        # Popen с СПИСКОМ на Windows сам правильно квотирует каждый аргумент
        cmd_list = [winws] + cleaned

        self.log.info(f"START cmd_list ({len(cmd_list)} items):")
        for i, a in enumerate(cmd_list):
            self.log.info(f"  [{i}] {repr(a)}")
        self.log.info(f"START cwd: {work_dir}")

        try:
            self.process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=work_dir,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            self._running = True
            self.log.info(f"START OK: PID={self.process.pid}")
            self._job_object = create_job_object()
            if self._job_object:
                try:
                    assigned = assign_process_to_job(self._job_object, int(self.process._handle))
                    self.log.info(f"START Job Object assigned: {bool(assigned)}")
                except Exception as e:
                    self.log.warning(f"START Job Object assignment failed: {e}")

            # Ждём 1 секунду и проверяем не упал ли процесс сразу
            time.sleep(1)
            exit_code = self.process.poll()
            if exit_code is not None:
                # Процесс уже завершился — читаем вывод
                output = ""
                try:
                    output = self.process.stdout.read(2000)
                except Exception:
                    pass
                self._running = False
                if self._job_object:
                    try:
                        terminate_job(self._job_object)
                    except Exception:
                        pass
                    self._job_object = None
                self.process = None
                msg = f"{engine_name} exited immediately (code {exit_code})"
                if output:
                    msg += f"\nВывод:\n{output}"
                self.log.error(msg)
                return False, msg

            return True, f"PID {self.process.pid}"
        except FileNotFoundError as e:
            self.log.error(f"START FileNotFoundError: {e}")
            return False, f"Файл не найден: {e}"
        except PermissionError as e:
            self.log.error(f"START PermissionError: {e}")
            return False, f"Нет прав: {e}. Запустите от администратора."
        except OSError as e:
            self.log.error(f"START OSError: {e}")
            return False, f"Ошибка ОС: {e}"
        except Exception as e:
            self.log.error(f"START error: {traceback.format_exc()}")
            return False, str(e)

    def stop(self) -> tuple:
        self.log.info("STOP requested")
        try:
            if self._job_object:
                try:
                    self.log.info("Terminating Backend Job Object")
                    terminate_job(self._job_object)
                except Exception as e:
                    self.log.warning(f"Job Object terminate failed: {e}")
                self._job_object = None
                self.process = None

            if self.process and self.process.poll() is None:
                self.log.info(f"Terminating PID {self.process.pid}")
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.log.warning("Terminate timeout, killing...")
                    self.process.kill()
                self.process = None

            for image_name in ENGINE_EXECUTABLES:
                self.log.info(f"Killing all {image_name} via taskkill")
                r = subprocess.run(
                    ["taskkill", "/T", "/F", "/IM", image_name],
                    capture_output=True, timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    **WINDOWS_CLI_TEXT_KW
                )
                stdout = (r.stdout or "").strip()
                stderr = (r.stderr or "").strip()
                self.log.info(
                    f"taskkill {image_name}: returncode={r.returncode}, stdout={stdout}, stderr={stderr}"
                )
            self._running = False
            return True, "Остановлен"
        except Exception as e:
            self.log.error(f"STOP error: {traceback.format_exc()}")
            return False, str(e)

    def get_process_output(self) -> str:
        """Пытается прочитать вывод winws2."""
        if self.process and self.process.stdout:
            try:
                # Неблокирующее чтение
                import selectors
                sel = selectors.DefaultSelector()
                sel.register(self.process.stdout, selectors.EVENT_READ)
                events = sel.select(timeout=0.1)
                if events:
                    return self.process.stdout.readline()
                sel.close()
            except Exception:
                pass
        return ""


# ──────────────────────────────────────────────────────
#  ЦЕЛЕВЫЕ ДОМЕНЫ
# ──────────────────────────────────────────────────────
TARGETS_FILE = os.path.join(DATA_DIR, "targets.json")

# Домены по умолчанию с категориями
DEFAULT_TARGETS = {
    "YouTube": [
        "youtube.com", "www.youtube.com", "youtu.be",
        "yt3.ggpht.com", "googlevideo.com",
    ],
    "Discord": [
        "discord.com", "discord.gg", "discordapp.com",
        "cdn.discordapp.com", "gateway.discord.gg",
        "media.discordapp.net",
    ],
    "Telegram": [
        "telegram.org", "web.telegram.org", "t.me",
        "core.telegram.org",
    ],
    "Google Docs": [
        "docs.google.com", "drive.google.com",
        "sheets.google.com", "slides.google.com",
    ],
}


def load_targets() -> dict:
    """Загружает целевые домены. Возвращает {категория: [домены]}."""
    if os.path.isfile(TARGETS_FILE):
        try:
            with open(TARGETS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            log.info(f"Loaded targets: {sum(len(v) for v in data.values())} domains in {len(data)} categories")
            return data
        except Exception as e:
            log.warning(f"Failed to load targets: {e}")
    return dict(DEFAULT_TARGETS)


def save_targets(targets: dict):
    try:
        with open(TARGETS_FILE, "w", encoding="utf-8") as f:
            json.dump(targets, f, indent=2, ensure_ascii=False)
        log.info("Targets saved")
    except Exception as e:
        log.error(f"Failed to save targets: {e}")


def get_all_domains(targets: dict) -> list:
    """Возвращает плоский список всех доменов."""
    domains = []
    for cat_domains in targets.values():
        domains.extend(cat_domains)
    return sorted(set(domains))


def write_hostlist(targets: dict, filepath: str = None) -> str:
    """Записывает все домены в hostlist-файл для winws2. Возвращает путь."""
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "target-hosts.txt")
    domains = get_all_domains(targets)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# Auto-generated by Zapret2 Manager\n")
        f.write(f"# {datetime.datetime.now().isoformat()}\n")
        for d in domains:
            f.write(d + "\n")
    log.info(f"Hostlist written: {filepath} ({len(domains)} domains)")
    return filepath


# ──────────────────────────────────────────────────────
#  СТРАТЕГИИ ПО ДОМЕНАМ (комбо-конфиги)
# ──────────────────────────────────────────────────────
DOMAIN_STRATEGIES_FILE = os.path.join(DATA_DIR, "domain_strategies.json")


def load_domain_strategies() -> dict:
    """
    Загружает {домен_или_категория: {"strategy": "...", "found": "2026-...", "test": "tls12"}}
    """
    if os.path.isfile(DOMAIN_STRATEGIES_FILE):
        try:
            with open(DOMAIN_STRATEGIES_FILE, encoding="utf-8") as f:
                data = json.load(f)
            log.info(f"Loaded domain strategies: {len(data)} entries")
            return data
        except Exception as e:
            log.warning(f"Failed to load domain strategies: {e}")
    return {}


def save_domain_strategies(strategies: dict):
    try:
        with open(DOMAIN_STRATEGIES_FILE, "w", encoding="utf-8") as f:
            json.dump(strategies, f, indent=2, ensure_ascii=False)
        log.info(f"Saved {len(strategies)} domain strategies")
    except Exception as e:
        log.error(f"Failed to save domain strategies: {e}")


def write_single_hostlist(domain: str, targets: dict) -> str:
    """Записывает hostlist для одного домена (+ связанные из категории)."""
    related = get_related_domains(domain, targets)

    safe_name = domain.replace(".", "_").replace("/", "_")
    filepath = os.path.join(DATA_DIR, f"hosts_{safe_name}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        for d in sorted(set(related)):
            f.write(d + "\n")
    return filepath


def get_related_domains(domain: str, targets: dict) -> list:
    for doms in targets.values():
        if domain in doms:
            return list(doms)
    return [domain]


def write_domains_hostlist(domains: list, filename_hint: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", filename_hint).strip("_") or "custom"
    filepath = os.path.join(DATA_DIR, f"hosts_{safe_name}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        for d in sorted(set(domains)):
            f.write(d + "\n")
    return filepath


def split_winws_args(params_str: str) -> list:
    args = []
    for part in (params_str or "").split(" --"):
        part = part.strip()
        if not part:
            continue
        if not part.startswith("--"):
            part = "--" + part
        args.append(part)
    return args


def inspect_strategy(raw_strategy: str) -> dict:
    if isinstance(raw_strategy, dict):
        raw_strategy = (
            raw_strategy.get("strategy")
            or raw_strategy.get("params")
            or raw_strategy.get("raw")
            or ""
        )

    text = str(raw_strategy or "").strip()
    tool = "winws2"
    params_str = text
    match = re.search(r"\b(winws2?|winws)\b(.*)$", text, re.IGNORECASE)
    if match:
        tool = match.group(1).lower()
        params_str = match.group(2).strip()

    args = split_winws_args(params_str)
    lower_text = text.lower()
    lower_args = [arg.lower() for arg in args]

    protocol = "tls"
    if (
        "quic" in lower_text
        or any(arg.startswith("--filter-udp=") for arg in lower_args)
        or any("--wf-udp-out=443" in arg for arg in lower_args)
        or any("--payload=quic_initial" in arg for arg in lower_args)
    ):
        protocol = "quic"
    elif (
        re.search(r"\bcurl_test_http\b", lower_text)
        or any(arg.startswith("--filter-tcp=80") for arg in lower_args)
        or any("--wf-tcp-out=80" in arg for arg in lower_args)
        or any("--payload=http_req" in arg for arg in lower_args)
    ):
        protocol = "http"

    has_filter_tcp = any(arg.startswith("--filter-tcp=") for arg in lower_args)
    has_filter_udp = any(arg.startswith("--filter-udp=") for arg in lower_args)
    has_filter_l7 = any(arg.startswith("--filter-l7=") for arg in lower_args)
    has_range = any(
        arg.startswith("--in-range=") or arg.startswith("--out-range=")
        for arg in lower_args
    )

    return {
        "raw": text,
        "tool": tool,
        "args": args,
        "protocol": protocol,
        "has_wf": any(arg.startswith("--wf-") for arg in lower_args),
        "has_range": has_range,
        "has_filter_tcp": has_filter_tcp,
        "has_filter_udp": has_filter_udp,
        "has_filter_l7": has_filter_l7,
    }


def build_strategy_chain_args(raw_strategy: str, hostlist_arg: str = "", keep_wf: bool = False) -> list:
    meta = inspect_strategy(raw_strategy)
    if not meta["args"]:
        return []

    if meta["protocol"] == "http":
        transport_filter = "--filter-tcp=80"
        l7_filter = "--filter-l7=http"
        range_filter = "--out-range=-d10"
    elif meta["protocol"] == "quic":
        transport_filter = "--filter-udp=443"
        l7_filter = "--filter-l7=quic"
        range_filter = ""
    else:
        transport_filter = "--filter-tcp=443"
        l7_filter = "--filter-l7=tls"
        range_filter = "--out-range=-d10"

    chain = []
    if hostlist_arg:
        chain.append(hostlist_arg)
    if not (meta["has_filter_tcp"] or meta["has_filter_udp"]):
        chain.append(transport_filter)
    if l7_filter and not meta["has_filter_l7"]:
        chain.append(l7_filter)
    if range_filter and not meta["has_range"]:
        chain.append(range_filter)

    for arg in meta["args"]:
        if not keep_wf and arg.startswith("--wf-"):
            continue
        chain.append(arg)
    return chain


def build_combo_profile(domain_strategies: dict, targets: dict, name: str = None) -> 'Profile':
    """
    Строит мульти-профиль где каждый домен/группа имеет свою стратегию.

    domain_strategies: {"youtube.com": "--payload=tls_client_hello --lua-desync=fake:...", ...}
    targets: {"YouTube": ["youtube.com", ...], ...}

    Результат: Profile с --new блоками, каждый с своим --hostlist и стратегией.
    """
    if not domain_strategies:
        return generate_default_profile(targets)

    args = [
        "--wf-tcp-out=80,443",
        "--lua-init=@zapret-lib.lua",
        "--lua-init=@zapret-antidpi.lua",
    ]

    first = True
    http_domains = set()

    for domain, strategy in domain_strategies.items():
        if not strategy:
            continue

        related_domains = get_related_domains(domain, targets)
        hostlist = write_single_hostlist(domain, targets)
        try:
            rel = os.path.relpath(hostlist, WINWS_DIR)
        except ValueError:
            rel = hostlist

        chain_args = build_strategy_chain_args(strategy, hostlist_arg=f'--hostlist="{rel}"')
        if not chain_args:
            continue

        if not first:
            args.append("--new")
        first = False

        args.extend(chain_args)

        meta = inspect_strategy(strategy)
        if meta["protocol"] == "http":
            http_domains.update(related_domains)

    all_domains = get_all_domains(targets)
    http_fallback_domains = [d for d in all_domains if d not in http_domains]
    if http_fallback_domains:
        http_hostlist = write_domains_hostlist(http_fallback_domains, "http_fallback")
        try:
            rel_http = os.path.relpath(http_hostlist, WINWS_DIR)
        except ValueError:
            rel_http = http_hostlist

        if not first:
            args.append("--new")
        first = False
        args.extend([
            f'--hostlist="{rel_http}"',
            "--filter-tcp=80",
            "--filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ])

    if all_domains:
        quic_hostlist = write_domains_hostlist(all_domains, "quic_all")
        try:
            rel_quic = os.path.relpath(quic_hostlist, WINWS_DIR)
        except ValueError:
            rel_quic = quic_hostlist

        if not first:
            args.append("--new")
        args.extend([
            f'--hostlist="{rel_quic}"',
            "--filter-udp=443",
            "--filter-l7=quic",
            "--payload=quic_initial",
            "--lua-desync=fake:blob=fake_default_quic:repeats=11",
        ])

    n_domains = len(domain_strategies)
    if not name:
        name = f"Комбо ({n_domains} {'стратегия' if n_domains == 1 else 'стратегий'})"

    return Profile(
        name=name,
        desc=f"Per-domain стратегии: {', '.join(domain_strategies.keys())}",
        args=args,
    )


def build_profile_from_raw_strategy(raw_strategy: str, targets: dict, name: str = None) -> 'Profile':
    meta = inspect_strategy(raw_strategy)
    if not meta["args"]:
        return generate_default_profile(targets)

    hostlist = write_hostlist(targets)
    try:
        rel = os.path.relpath(hostlist, WINWS_DIR)
    except ValueError:
        rel = hostlist

    args = [
        "--wf-tcp-out=80,443",
        "--lua-init=@zapret-lib.lua",
        "--lua-init=@zapret-antidpi.lua",
    ]
    args.extend(build_strategy_chain_args(raw_strategy, hostlist_arg=f'--hostlist="{rel}"'))

    if meta["protocol"] != "http":
        args.extend([
            "--new",
            f'--hostlist="{rel}"',
            "--filter-tcp=80",
            "--filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ])

    if meta["protocol"] != "quic":
        args.extend([
            "--new",
            f'--hostlist="{rel}"',
            "--filter-udp=443",
            "--filter-l7=quic",
            "--payload=quic_initial",
            "--lua-desync=fake:blob=fake_default_quic:repeats=11",
        ])

    preview = " ".join(meta["args"])[:80]
    return Profile(
        name=name or "Blockcheck",
        desc=f"Собран из blockcheck: {preview}...",
        args=args,
    )


# ──────────────────────────────────────────────────────
#  BLOCKCHECK: автоанализ стратегий
# ──────────────────────────────────────────────────────
def find_blockcheck() -> str:
    """Находит blockcheck2.cmd в дереве zapret."""
    candidates = [
        os.path.join(ZAPRET_DIR, "blockcheck", "blockcheck2.cmd"),
        os.path.join(ZAPRET_DIR, "blockcheck2.cmd"),
        os.path.join(WINWS_DIR, "..", "blockcheck", "blockcheck2.cmd"),
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if os.path.isfile(p):
            log.info(f"find_blockcheck: {p}")
            return p
    for root, dirs, files in os.walk(ZAPRET_DIR):
        for f in files:
            if f.lower() in ("blockcheck2.cmd", "blockcheck.cmd"):
                path = os.path.join(root, f)
                log.info(f"find_blockcheck (search): {path}")
                return path
    log.warning("blockcheck2.cmd NOT FOUND")
    return ""


def run_blockcheck(domains: list = None, mode: str = "quick", extra_env: dict = None) -> subprocess.Popen:
    """
    Запускает blockcheck2 НАПРЯМУЮ через cygwin bash, минуя elevator.exe.

    Проблема: blockcheck2.cmd → elevator.exe → ОТДЕЛЬНЫЙ процесс → наш pipe пуст, код 0 мгновенно.
    Решение: мы уже admin (START_ADMIN.bat), вызываем bash + blockcheck2.sh напрямую.
    """
    bc_cmd = find_blockcheck()
    if not bc_cmd:
        raise FileNotFoundError("blockcheck2.cmd не найден")
    bc_dir = os.path.dirname(bc_cmd)

    if not domains:
        domains = ["youtube.com", "discord.com"]
    domain_str = " ".join(domains)

    # === Ищем bash.exe в cygwin ===
    bash_exe = None
    for p in [
        os.path.join(ZAPRET_DIR, "cygwin", "bin", "bash.exe"),
        os.path.join(bc_dir, "..", "cygwin", "bin", "bash.exe"),
        os.path.join(bc_dir, "cygwin", "bin", "bash.exe"),
    ]:
        p = os.path.normpath(p)
        if os.path.isfile(p):
            bash_exe = p
            break
    if not bash_exe:
        for root, dirs, files in os.walk(ZAPRET_DIR):
            if "bash.exe" in files:
                bash_exe = os.path.join(root, "bash.exe")
                break
    if not bash_exe:
        raise FileNotFoundError(
            "bash.exe не найден в cygwin.\n"
            "Запустите blockcheck2.cmd вручную из папки zapret.")

    # === Ищем blockcheck2.sh ===
    bc_sh = None
    for p in [
        os.path.join(bc_dir, "zapret2", "blockcheck2.sh"),
        os.path.join(bc_dir, "zapret", "blockcheck2.sh"),
        os.path.join(bc_dir, "blockcheck2.sh"),
    ]:
        if os.path.isfile(p):
            bc_sh = p
            break
    if not bc_sh:
        for root, dirs, files in os.walk(bc_dir):
            if "blockcheck2.sh" in files:
                bc_sh = os.path.join(root, "blockcheck2.sh")
                break
    if not bc_sh:
        raise FileNotFoundError("blockcheck2.sh не найден")

    # === Конвертируем Windows путь → cygwin путь ===
    def to_cygpath(winpath):
        winpath = os.path.abspath(winpath)
        drive = winpath[0].lower()
        rest = winpath[2:].replace("\\", "/")
        return f"/cygdrive/{drive}{rest}"

    bc_sh_cyg = to_cygpath(bc_sh)
    bash_dir = os.path.dirname(bash_exe)
    bc_sh_dir = os.path.dirname(bc_sh)

    log.info(f"run_blockcheck DIRECT bash mode:")
    log.info(f"  bash: {bash_exe}")
    log.info(f"  sh:   {bc_sh}")
    log.info(f"  cyg:  {bc_sh_cyg}")
    log.info(f"  cwd:  {bc_sh_dir}")
    log.info(f"  DOMAINS={domain_str}, SCANLEVEL={mode}")

    # === Формируем env ===
    env = os.environ.copy()
    env["BATCH"] = "1"
    env["DOMAINS"] = domain_str
    env["SCANLEVEL"] = mode
    env["SKIP_DNSCHECK"] = "1"
    env["SKIP_IPBLOCK"] = "1"
    env["CURL_MAX_TIME"] = "4"
    # PATH включает cygwin/bin для curl, ncat и прочего
    env["PATH"] = bash_dir + ";" + env.get("PATH", "")

    if extra_env:
        env.update(extra_env)
        log.info(f"  extra_env: {extra_env}")
    else:
        env["ENABLE_HTTP"] = "0"
        env["ENABLE_HTTPS_TLS12"] = "1"
        env["ENABLE_HTTPS_TLS13"] = "0"
        env["ENABLE_HTTP3"] = "0"

    # === Запуск ===
    # CREATE_NEW_PROCESS_GROUP нужен чтобы Job Object работал
    proc = subprocess.Popen(
        [bash_exe, "--login", "-c", f"'{bc_sh_cyg}'"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=bc_sh_dir,
        env=env,
        bufsize=1,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    # Создаём Job Object и добавляем процесс
    # При terminate_job() ВСЕ дочерние процессы (winws2, curl, bash) умрут
    job = create_job_object()
    if job:
        # kernel32.OpenProcess чтобы получить handle с нужными правами
        PROCESS_ALL_ACCESS = 0x1F0FFF
        h = _kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, proc.pid)
        if h:
            assign_process_to_job(job, h)
            _kernel32.CloseHandle(h)
            log.info(f"  Process assigned to Job Object")
        else:
            log.warning(f"  Failed to open process for Job assignment")
    proc._job_object = job  # Сохраняем для terminate

    log.info(f"  Started PID: {proc.pid}")
    return proc



def parse_blockcheck_output(text: str) -> list:
    """
    Парсит вывод blockcheck/blockcheck2.
    Ищет блок SUMMARY и строки AVAILABLE.

    Возвращает список словарей:
    [{"ipv": "4", "domain": "youtube.com", "test": "curl_test_https_tls13",
      "tool": "nfqws", "params": "--dpi-desync=fake --dpi-desync-ttl=6"}, ...]
    """
    results = []

    # Паттерн SUMMARY: "ipv4 domain test : tool params"
    summary_pattern = re.compile(
        r'ipv([46])\s+(\S+)\s+(\S+)\s*:\s*(nfqws2?|winws2?|tpws)\s+(.*)',
        re.IGNORECASE
    )

    # Паттерн AVAILABLE с параметрами рядом
    available_pattern = re.compile(
        r'!!+\s*AVAILABLE\s*!!+',
        re.IGNORECASE
    )

    # Паттерн для параметров стратегии (nfqws/winws строки)
    strategy_pattern = re.compile(
        r'(nfqws2?|winws2?)\s+(--\S.*)',
        re.IGNORECASE
    )

    # Ищем SUMMARY блок
    in_summary = False
    for line in text.split("\n"):
        line = line.strip()

        if "SUMMARY" in line and line.startswith("*"):
            in_summary = True
            continue

        if in_summary:
            m = summary_pattern.match(line)
            if m:
                results.append({
                    "ipv": m.group(1),
                    "domain": m.group(2),
                    "test": m.group(3),
                    "tool": m.group(4),
                    "params": m.group(5).strip(),
                })
            elif line and not line.startswith("*") and not line.startswith("Please"):
                # Конец summary если непарсимая строка
                if not summary_pattern.match(line) and results:
                    pass  # продолжаем, могут быть пустые строки

    # Если SUMMARY не найден — ищем по AVAILABLE маркерам
    if not results:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if available_pattern.search(line):
                # Ищем стратегию в этой и соседних строках
                context = " ".join(lines[max(0, i-3):i+2])
                m = strategy_pattern.search(context)
                if m:
                    # Пытаемся найти домен
                    domain_m = re.search(r'testing\s+(\S+)', context, re.IGNORECASE)
                    domain = domain_m.group(1) if domain_m else "unknown"
                    results.append({
                        "ipv": "4",
                        "domain": domain,
                        "test": "auto",
                        "tool": m.group(1),
                        "params": m.group(2).strip(),
                    })

    log.info(f"Parsed {len(results)} strategies from blockcheck output")
    for r in results:
        log.info(f"  ipv{r['ipv']} {r['domain']} : {r['tool']} {r['params']}")

    return results


def generate_profile_from_results(results: list, targets: dict,
                                    hostlist_path: str = None) -> 'Profile':
    """
    Генерирует Profile из результатов blockcheck.
    Берёт лучшую стратегию для TLS (самую частую) и применяет к hostlist.
    """
    if not results:
        log.warning("No results to generate profile from")
        return None

    # Группируем по тесту (tls13 > tls12 > http)
    tls_params = []
    http_params = []
    quic_params = []

    for r in results:
        params = r["params"]
        test = r.get("test", "").lower()
        if "quic" in test:
            quic_params.append(params)
        elif "tls" in test or "https" in test:
            tls_params.append(params)
        elif "http" in test:
            http_params.append(params)
        else:
            tls_params.append(params)  # fallback

    # Берём первую (лучшую) стратегию из каждой категории
    # Конвертируем nfqws1 параметры в nfqws2/winws2 формат
    args = [
        "--wf-tcp-out=80,443",
        "--lua-init=@zapret-lib.lua",
        "--lua-init=@zapret-antidpi.lua",
    ]

    # Если есть hostlist — добавляем
    if hostlist_path is None:
        hostlist_path = write_hostlist(targets)
    if os.path.isfile(hostlist_path):
        # Относительный путь
        try:
            rel = os.path.relpath(hostlist_path, WINWS_DIR)
        except ValueError:
            rel = hostlist_path
        args.append(f'--hostlist="{rel}"')

    # TLS профиль
    if tls_params:
        best_tls = tls_params[0]
        args.append("--filter-tcp=443 --filter-l7=tls")
        args.append("--out-range=-d10")
        args.append("--payload=tls_client_hello")
        # Конвертация: nfqws1 → nfqws2/winws2
        converted = _convert_nfqws1_to_nfqws2(best_tls)
        args.extend(converted)
    else:
        # Фолбэк — стандартная стратегия
        args.append("--filter-tcp=443 --filter-l7=tls")
        args.append("--out-range=-d10")
        args.append("--payload=tls_client_hello")
        args.append("--lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=6")
        args.append("--lua-desync=multidisorder:pos=midsld")

    # HTTP профиль
    if http_params:
        args.append("--new")
        best_http = http_params[0]
        args.append("--filter-tcp=80 --filter-l7=http")
        args.append("--out-range=-d10")
        args.append("--payload=http_req")
        converted = _convert_nfqws1_to_nfqws2(best_http)
        args.extend(converted)

    # QUIC профиль
    if quic_params:
        args.append("--new")
        args.append("--filter-udp=443 --filter-l7=quic")
        args.append("--payload=quic_initial")
        args.append("--lua-desync=fake:blob=fake_default_quic:repeats=11")

    cats = ", ".join(targets.keys())
    return Profile(
        name=f"Авто ({cats})",
        desc=f"Автоматически сгенерирован из blockcheck. {len(results)} стратегий найдено.",
        args=args,
    )


def _convert_nfqws1_to_nfqws2(params: str) -> list:
    """
    Конвертирует параметры nfqws1 (--dpi-desync=...) в вызовы lua-desync для nfqws2.
    Базовая конвертация самых распространённых стратегий.
    """
    result = []

    # Если уже в формате nfqws2
    if "--lua-desync" in params:
        for part in params.split("--lua-desync="):
            part = part.strip()
            if part:
                result.append(f"--lua-desync={part.split()[0]}")
        return result if result else [f"--lua-desync=fake:blob=fake_default_tls:tcp_md5"]

    # Парсим nfqws1 параметры
    desync = ""
    ttl = ""
    fooling = ""
    split_pos = ""
    repeats = ""
    autottl = ""

    for part in params.split():
        if part.startswith("--dpi-desync="):
            desync = part.split("=", 1)[1]
        elif part.startswith("--dpi-desync-ttl="):
            ttl = part.split("=", 1)[1]
        elif part.startswith("--dpi-desync-autottl="):
            autottl = part.split("=", 1)[1]
        elif part.startswith("--dpi-desync-fooling="):
            fooling = part.split("=", 1)[1]
        elif part.startswith("--dpi-desync-split-pos="):
            split_pos = part.split("=", 1)[1]
        elif part.startswith("--dpi-desync-repeats="):
            repeats = part.split("=", 1)[1]

    if not desync:
        return ["--lua-desync=fake:blob=fake_default_tls:tcp_md5"]

    # Конвертируем desync phases
    phases = desync.split(",")

    for phase in phases:
        lua_parts = [phase]
        if phase == "fake":
            lua_parts = ["fake:blob=fake_default_tls"]
        elif phase in ("fakedsplit", "fakeddisorder"):
            lua_parts = [phase]
        elif phase in ("multisplit", "multidisorder"):
            if split_pos:
                lua_parts = [f"{phase}:pos={split_pos}"]
            else:
                lua_parts = [f"{phase}:pos=midsld"]

        # Добавляем модификаторы
        mods = []
        if fooling:
            for f in fooling.split(","):
                if f == "md5sig":
                    mods.append("tcp_md5")
                elif f == "badseq":
                    mods.append("tcp_seq=-10000")
                elif f == "datanoack":
                    mods.append("tcp_flags_unset=ack")
        if ttl:
            mods.append(f"ip_ttl={ttl}")
            mods.append(f"ip6_ttl={ttl}")
        if autottl:
            mods.append(f"ip_autottl={autottl}")
            mods.append(f"ip6_autottl={autottl}")
        if repeats:
            mods.append(f"repeats={repeats}")

        lua_str = ":".join(lua_parts + mods) if mods else ":".join(lua_parts)
        result.append(f"--lua-desync={lua_str}")

    return result if result else ["--lua-desync=fake:blob=fake_default_tls:tcp_md5"]


def generate_default_profile(targets: dict) -> 'Profile':
    """
    Генерирует профиль по умолчанию на основе списка доменов.
    Использует проверенную стратегию: fake autottl + orig-ttl=1.
    """
    hostlist_path = write_hostlist(targets)
    try:
        rel = os.path.relpath(hostlist_path, WINWS_DIR)
    except ValueError:
        rel = hostlist_path

    cats = ", ".join(targets.keys())
    n = sum(len(v) for v in targets.values())
    return Profile(
        name=f"Быстрый ({cats})",
        desc=f"fake autottl + orig-ttl для {n} доменов. Проверенная стратегия.",
        args=[
            "--wf-tcp-out=80,443",
            "--lua-init=@zapret-lib.lua",
            "--lua-init=@zapret-antidpi.lua",
            f'--hostlist="{rel}"',
            "--filter-tcp=443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
            "--new",
            f'--hostlist="{rel}"',
            "--filter-tcp=80 --filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
            "--new",
            "--filter-udp=443 --filter-l7=quic",
            "--payload=quic_initial",
            "--lua-desync=fake:blob=fake_default_quic:repeats=11",
        ],
    )


# ──────────────────────────────────────────────────────
#  БЫСТРЫЙ ТЕСТЕР ПРЕСЕТОВ
# ──────────────────────────────────────────────────────

# Готовые пресеты — проверенные стратегии для РФ провайдеров
# Каждый пресет = список аргументов для winws2 (без --wf-tcp-out, --lua-init)
QUICK_PRESETS = [
    {
        "name": "fake autottl + orig-ttl=1",
        "desc": "Классика. fake с autottl, оригиналу ставим ttl=1",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    },
    {
        "name": "double fake autottl + orig-ttl=1",
        "desc": "Два fake (пустой+TLS) с autottl",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=0x00000000:ip_autottl=-5,3-20:repeats=1",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:tls_mod=rnd,dupsid:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    },
    {
        "name": "fake autottl + multisplit midsld + orig-ttl",
        "desc": "fake + разрезка по середине домена + orig-ttl",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:repeats=1",
            "--lua-desync=multisplit:pos=midsld",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    },
    {
        "name": "fake md5sig repeats=6 + multidisorder",
        "desc": "fake с md5sig фулингом + multidisorder",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=6",
            "--lua-desync=multidisorder:pos=midsld",
        ],
    },
    {
        "name": "fake badseq + multidisorder",
        "desc": "fake с badseq фулингом",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_seq=-10000:repeats=6",
            "--lua-desync=multidisorder:pos=midsld",
        ],
    },
    {
        "name": "fake TTL=3",
        "desc": "fake с фиксированным TTL=3",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_ttl=3:repeats=1",
        ],
    },
    {
        "name": "fake TTL=5",
        "desc": "fake с фиксированным TTL=5",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_ttl=5:repeats=1",
        ],
    },
    {
        "name": "fake TTL=8",
        "desc": "fake с фиксированным TTL=8",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_ttl=8:repeats=1",
        ],
    },
    {
        "name": "multisplit pos=2",
        "desc": "Просто разрезка на позиции 2",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=multisplit:pos=2",
        ],
    },
    {
        "name": "multidisorder pos=1,midsld",
        "desc": "Разрезка с реордерингом",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=multidisorder:pos=1,midsld",
        ],
    },
    {
        "name": "wssize 1:6 + fakedsplit midsld TTL=3",
        "desc": "Уменьшение окна + fakedsplit для TLS 1.2 блоков",
        "args": [
            "--lua-desync=wssize:wsize=1:scale=6",
            "--payload=tls_client_hello",
            "--lua-desync=fakedsplit:pos=midsld:ip_ttl=3:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    },
    {
        "name": "wssize 1:6 + fakedsplit md5sig",
        "desc": "wssize + fakedsplit с md5sig",
        "args": [
            "--lua-desync=wssize:wsize=1:scale=6",
            "--payload=tls_client_hello",
            "--lua-desync=fakedsplit:pos=midsld:tcp_md5:repeats=1",
            "--payload=empty --out-range=<s1",
            "--lua-desync=send:tcp_md5",
        ],
    },
    {
        "name": "fake rnd,dupsid + multisplit pos=1",
        "desc": "fake с рандомизацией TLS + multisplit",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:tls_mod=rnd,dupsid:repeats=1",
            "--lua-desync=multisplit:pos=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    },
    {
        "name": "fake autottl=-3 + multisplit sniext+1",
        "desc": "Другая дельта autottl + разрезка после SNI",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-3,3-20:repeats=1",
            "--lua-desync=multisplit:pos=sniext+1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    },
    {
        "name": "multisplit nodrop pos=2 + orig-ttl",
        "desc": "multisplit без дропа оригинала",
        "args": [
            "--payload=tls_client_hello",
            "--lua-desync=multisplit:blob=fake_default_tls:ip_autottl=-5,3-20:pos=2:nodrop:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
    },
]


def test_single_preset(preset_args: list, test_domain: str,
                        winws_bin: str, lua_dir: str,
                        timeout: int = 5) -> dict:
    """
    Тестирует один пресет:
    1. Запускает winws2 с пресетом
    2. Делает curl к домену
    3. Проверяет результат
    4. Убивает winws2

    Возвращает: {"ok": bool, "time_ms": int, "curl_code": int, "error": str}
    """
    work_dir = os.path.dirname(winws_bin)

    # Формируем Lua пути
    lua_args = []
    for lf in ["zapret-lib.lua", "zapret-antidpi.lua"]:
        full = os.path.join(lua_dir, lf)
        try:
            rel = os.path.relpath(full, work_dir)
        except ValueError:
            rel = full
        lua_args.append(f"--lua-init=@{rel}")

    # Полная команда
    base_args = ["--wf-tcp-out=443"] + lua_args
    base_args.append("--filter-tcp=443 --filter-l7=tls")
    base_args.append("--out-range=-d10")

    all_args = base_args + preset_args

    # Собираем flat
    flat = []
    for a in all_args:
        a = a.strip()
        if not a:
            continue
        parts = a.split(" --")
        if len(parts) > 1:
            flat.append(parts[0].strip())
            for p in parts[1:]:
                flat.append("--" + p.strip())
        else:
            flat.append(a)

    cmd_str = f'"{winws_bin}"'
    for a in flat:
        if '"' in a:
            cmd_str += f" {a}"
        elif " " in a:
            cmd_str += f' "{a}"'
        else:
            cmd_str += f" {a}"

    result = {"ok": False, "time_ms": 0, "curl_code": -1, "error": ""}

    proc = None
    try:
        # 1. Запускаем winws2
        proc = subprocess.Popen(
            cmd_str, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=work_dir, shell=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        time.sleep(0.8)  # Даём winws2 инициализироваться

        if proc.poll() is not None:
            out = proc.stdout.read(500) if proc.stdout else ""
            result["error"] = f"winws2 упал: {out[:200]}"
            return result

        # 2. curl тест
        t0 = time.time()
        curl_cmd = [
            "curl", "-s", "-o", "NUL", "-w", "%{http_code}",
            "--max-time", str(timeout),
            "--tlsv1.2", f"https://{test_domain}"
        ]
        # На Windows curl может быть в cygwin
        curl_paths = [
            "curl",
            os.path.join(work_dir, "..", "cygwin", "bin", "curl.exe"),
        ]
        curl_bin = "curl"
        for cp in curl_paths:
            if shutil.which(cp) or os.path.isfile(cp):
                curl_bin = cp
                break

        cr = subprocess.run(
            [curl_bin, "-s", "-o", "NUL", "-w", "%{http_code}",
             "--max-time", str(timeout),
             f"https://{test_domain}"],
            capture_output=True, text=True, timeout=timeout + 3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        elapsed = int((time.time() - t0) * 1000)
        result["time_ms"] = elapsed
        result["curl_code"] = cr.returncode

        # Проверяем HTTP код
        http_code = cr.stdout.strip()
        if cr.returncode == 0 and http_code and http_code[0] in ("2", "3"):
            result["ok"] = True
        elif cr.returncode == 0:
            result["ok"] = True  # curl вернул 0 = соединение прошло

    except subprocess.TimeoutExpired:
        result["error"] = "timeout"
        result["curl_code"] = 28
    except Exception as e:
        result["error"] = str(e)
    finally:
        # 3. Убиваем winws2
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except:
                proc.kill()
        # Убиваем все winws2 на всякий случай
        try:
            subprocess.run(["taskkill", "/F", "/IM", "winws2.exe"],
                           capture_output=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except:
            pass
        time.sleep(0.3)

    return result


def run_preset_tests(test_domain: str, winws_bin: str, lua_dir: str,
                      progress_cb=None, timeout: int = 5) -> list:
    """
    Тестирует все пресеты последовательно.
    progress_cb(idx, total, preset_name, result) вызывается после каждого.
    Возвращает список (preset, result).
    """
    results = []
    total = len(QUICK_PRESETS)

    for i, preset in enumerate(QUICK_PRESETS):
        log.info(f"Testing preset {i+1}/{total}: {preset['name']}")
        r = test_single_preset(
            preset["args"], test_domain, winws_bin, lua_dir, timeout
        )
        log.info(f"  Result: ok={r['ok']}, time={r['time_ms']}ms, curl={r['curl_code']}")
        results.append((preset, r))

        if progress_cb:
            try:
                progress_cb(i, total, preset["name"], r)
            except:
                pass

    return results


def best_preset_from_results(results: list) -> dict:
    """Выбирает лучший пресет из результатов. Приоритет: ok → время."""
    working = [(p, r) for p, r in results if r["ok"]]
    if not working:
        return None
    # Сортируем по времени
    working.sort(key=lambda x: x[1]["time_ms"])
    return working[0][0]


def preset_to_profile(preset: dict, targets: dict) -> 'Profile':
    """Конвертирует пресет в полный Profile с hostlist."""
    hostlist_path = write_hostlist(targets)
    try:
        rel = os.path.relpath(hostlist_path, WINWS_DIR)
    except ValueError:
        rel = hostlist_path

    args = [
        "--wf-tcp-out=80,443",
        "--lua-init=@zapret-lib.lua",
        "--lua-init=@zapret-antidpi.lua",
        f'--hostlist="{rel}"',
        "--filter-tcp=443 --filter-l7=tls",
        "--out-range=-d10",
    ] + preset["args"] + [
        "--new",
        f'--hostlist="{rel}"',
        "--filter-tcp=80 --filter-l7=http",
        "--out-range=-d10",
        "--payload=http_req",
        "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
        "--payload=empty --out-range=s1<d1",
        "--lua-desync=pktmod:ip_ttl=1",
        "--new",
        "--filter-udp=443 --filter-l7=quic",
        "--payload=quic_initial",
        "--lua-desync=fake:blob=fake_default_quic:repeats=11",
    ]

    return Profile(
        name=f"Найден: {preset['name']}",
        desc=f"Автотест: {preset['desc']}",
        args=args,
    )


# ──────────────────────────────────────────────────────
#  ВЕРИФИКАЦИЯ СТРАТЕГИЙ (Phase 2)
# ──────────────────────────────────────────────────────

def verify_strategy(raw_strategy: str, domain: str,
                     winws_bin: str, lua_dir: str,
                     timeout: int = 3, max_ok_ms: int = 3000) -> dict:
    """
    Проверяет одну стратегию: запускает winws2 + curl.
    timeout=3 сек для curl, max_ok_ms=3000 — всё что дольше = не рабочее.
    Возвращает: {"ok": bool, "time_ms": int, "curl_code": int, "error": str}
    """
    result = {"ok": False, "time_ms": 0, "curl_code": -1, "error": ""}
    work_dir = os.path.dirname(winws_bin)

    meta = inspect_strategy(raw_strategy)
    if not meta["args"]:
        result["error"] = "no winws args"
        return result

    lua_args = []
    for lf in ["zapret-lib.lua", "zapret-antidpi.lua"]:
        full = os.path.join(lua_dir, lf)
        try: rel = os.path.relpath(full, work_dir)
        except ValueError: rel = full
        lua_args.append(f"--lua-init=@{rel}")

    flat = []
    has_lua = any(arg.startswith("--lua-init=") for arg in meta["args"])
    has_wf = meta["has_wf"]
    if not has_wf:
        if meta["protocol"] == "http":
            flat.append("--wf-tcp-out=80")
        elif meta["protocol"] == "quic":
            flat.append("--wf-udp-out=443")
        else:
            flat.append("--wf-tcp-out=443")
    if not has_lua:
        flat.extend(lua_args)
    flat.extend(meta["args"])

    proc = None
    try:
        proc = subprocess.Popen(
            [winws_bin] + flat, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=work_dir,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        time.sleep(0.8)
        if proc.poll() is not None:
            result["error"] = f"{meta['tool']} crashed"
            return result

        t0 = time.time()
        try:
            curl_url = f"http://{domain}" if meta["protocol"] == "http" else f"https://{domain}"
            cr = subprocess.run(
                ["curl", "-s", "-o", "NUL", "-w", "%{http_code}",
                 "--max-time", str(timeout), curl_url],
                capture_output=True, text=True, timeout=timeout + 2,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            elapsed = int((time.time() - t0) * 1000)
            result["time_ms"] = elapsed
            result["curl_code"] = cr.returncode
            http_code = cr.stdout.strip()

            # Рабочая = curl OK + HTTP 2xx/3xx + быстрее max_ok_ms
            if (cr.returncode == 0 and http_code and
                    http_code[0] in ("2", "3") and elapsed < max_ok_ms):
                result["ok"] = True
            elif elapsed >= max_ok_ms:
                result["error"] = f"too slow ({elapsed}ms)"
        except subprocess.TimeoutExpired:
            result["error"] = "timeout"
            result["curl_code"] = 28
            result["time_ms"] = (timeout + 2) * 1000
    except Exception as e:
        result["error"] = str(e)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=2)
            except: proc.kill()
        for image_name in ENGINE_EXECUTABLES:
            try:
                subprocess.run(["taskkill", "/F", "/IM", image_name],
                               capture_output=True, timeout=3,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except: pass
        time.sleep(0.2)

    return result


def _strategy_key(raw: str) -> str:
    """Извлекает ключевые параметры стратегии для дедупликации."""
    idx = raw.find("winws2")
    if idx < 0:
        return raw
    params = raw[idx + 6:].strip()
    # Оставляем только lua-desync, payload, wssize — ключевые для обхода
    key_parts = []
    for part in params.split(" --"):
        part = part.strip()
        if any(part.startswith(k) for k in [
            "lua-desync=", "payload=", "out-range=", "in-range=",
            "filter-", "lua-init="  # пропускаем
        ]):
            if not part.startswith("filter-") and not part.startswith("lua-init="):
                key_parts.append(part)
    return " ".join(sorted(key_parts))


def verify_domain_strategies(domain: str, strategies: list,
                              winws_bin: str, lua_dir: str,
                              timeout: int = 3, max_ok_ms: int = 3000,
                              progress_cb=None, stop_flag=None) -> list:
    """
    Верифицирует ВСЕ уникальные стратегии для домена.
    Дедупликация по ключевым параметрам (lua-desync + payload).
    timeout=3 сек, max_ok_ms=3000 — отсекаем медленные.
    stop_flag: callable returning True to abort.
    """
    # Глубокая дедупликация
    seen_keys = set()
    unique = []
    for s in strategies:
        key = _strategy_key(s)
        if key and key not in seen_keys:
            seen_keys.add(key)
            unique.append(s)

    log.info(f"verify_domain_strategies: {domain}: {len(strategies)} raw → {len(unique)} unique")

    results = []
    for i, strat in enumerate(unique):
        if stop_flag and stop_flag():
            break

        r = verify_strategy(strat, domain, winws_bin, lua_dir, timeout, max_ok_ms)
        results.append((strat, r))

        if progress_cb:
            try: progress_cb(i, len(unique), domain, strat, r)
            except: pass

    return results


# ──────────────────────────────────────────────────────
#  ПРОФИЛИ КОНФИГУРАЦИИ
# ──────────────────────────────────────────────────────
class Profile:
    def __init__(self, name, desc, args, builtin=False, binary=""):
        self.name = name
        self.desc = desc
        self.args = args
        self.builtin = builtin
        self.binary = binary

    def to_dict(self):
        return {"name": self.name, "desc": self.desc,
                "args": self.args, "builtin": self.builtin,
                "binary": self.binary}

    @classmethod
    def from_dict(cls, d):
        return cls(d["name"], d.get("desc", d.get("description", "")),
                   d["args"], d.get("builtin", d.get("is_builtin", False)),
                   d.get("binary", d.get("bin_path", "")))


# Встроенные профили для Windows — на основе реально найденных стратегий
BUILTIN_PROFILES = [
    Profile(
        "Базовый (autottl + orig-ttl)",
        "Простейшая рабочая стратегия: fake с autottl + orig-ttl=1. Подходит для большинства РФ провайдеров.",
        [
            "--wf-tcp-out=80,443",
            "--lua-init=@zapret-lib.lua",
            "--lua-init=@zapret-antidpi.lua",
            "--filter-tcp=443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
            "--new",
            "--filter-tcp=80 --filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
        builtin=True,
    ),
    Profile(
        "Усиленный (double fake + orig-ttl)",
        "Два fake (пустой + TLS) с autottl + orig-ttl. Если базовый не помогает.",
        [
            "--wf-tcp-out=80,443",
            "--lua-init=@zapret-lib.lua",
            "--lua-init=@zapret-antidpi.lua",
            "--filter-tcp=443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=0x00000000:ip_autottl=-5,3-20:repeats=1",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:tls_mod=rnd,dupsid:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
            "--new",
            "--filter-tcp=80 --filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
        builtin=True,
    ),
    Profile(
        "WSSize + fakedsplit (TLS 1.2 тяжёлые блоки)",
        "wssize=1:6 + fakedsplit с md5sig. Для провайдеров с глубоким анализом TLS server hello.",
        [
            "--wf-tcp-out=80,443",
            "--lua-init=@zapret-lib.lua",
            "--lua-init=@zapret-antidpi.lua",
            "--filter-tcp=443 --filter-l7=tls",
            "--out-range=-d10",
            "--lua-desync=wssize:wsize=1:scale=6",
            "--payload=tls_client_hello",
            "--lua-desync=fakedsplit:pos=midsld:ip_ttl=3:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
            "--new",
            "--filter-tcp=80 --filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
        ],
        builtin=True,
    ),
    Profile(
        "Полный (TLS + QUIC + Discord/VPN)",
        "Всё в одном: TLS autottl, QUIC fake, Discord/STUN/WireGuard.",
        [
            "--wf-tcp-out=80,443",
            "--lua-init=@zapret-lib.lua",
            "--lua-init=@zapret-antidpi.lua",
            '--wf-raw-part=@"windivert.filter\\windivert_part.discord_media.txt"',
            '--wf-raw-part=@"windivert.filter\\windivert_part.stun.txt"',
            '--wf-raw-part=@"windivert.filter\\windivert_part.wireguard.txt"',
            '--wf-raw-part=@"windivert.filter\\windivert_part.quic_initial_ietf.txt"',
            "--filter-tcp=443 --filter-l7=tls",
            "--out-range=-d10",
            "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
            "--new",
            "--filter-tcp=80 --filter-l7=http",
            "--out-range=-d10",
            "--payload=http_req",
            "--lua-desync=fake:blob=fake_default_http:ip_autottl=-5,3-20:repeats=1",
            "--payload=empty --out-range=s1<d1",
            "--lua-desync=pktmod:ip_ttl=1",
            "--new",
            "--filter-udp=443 --filter-l7=quic",
            "--payload=quic_initial",
            "--lua-desync=fake:blob=fake_default_quic:repeats=11",
            "--new",
            "--filter-l7=wireguard,stun,discord",
            "--payload=wireguard_initiation,wireguard_cookie,stun,discord_ip_discovery",
            "--lua-desync=fake:blob=0x00000000000000000000000000000000:repeats=2",
        ],
        builtin=True,
    ),
]


def load_settings(bootstrap: Bootstrap) -> dict:
    d = {
        "winws_bin": bootstrap.find_winws2(),
        "lua_dir": bootstrap.find_lua_dir(),
        "lists_dir": bootstrap.find_lists_dir(),
        "winws_dir": WINWS_DIR,
        "autostart_enabled": False,
        "monthly_auto_sync": True,
        "last_update": "",
        "last_auto_sync_check": "",
        "last_auto_sync_status": "",
    }
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                d.update(json.load(f))
            log.info(f"Settings loaded from {SETTINGS_FILE}")
        except Exception as e:
            log.warning(f"Failed to load settings: {e}")
    d["autostart_enabled"] = is_autostart_enabled()
    log.info(f"Effective settings: {json.dumps(d, ensure_ascii=False)}")
    return d


def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        log.info("Settings saved")
    except Exception as e:
        log.error(f"Failed to save settings: {e}")


def load_custom_profiles() -> list:
    profiles = []
    if os.path.isfile(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, encoding="utf-8") as f:
                for item in json.load(f):
                    profile = Profile.from_dict(item)
                    if not profile.binary:
                        exact = build_flowseal_runtime_profile(profile.name, profile.desc)
                        if exact:
                            profile.args = list(exact["args"])
                            profile.binary = exact["binary"]
                    profiles.append(profile)
            log.info(f"Loaded {len(profiles)} custom profiles")
        except Exception as e:
            log.warning(f"Failed to load profiles: {e}")
    return profiles


def save_custom_profiles(profiles: list):
    try:
        data = [p.to_dict() for p in profiles if not p.builtin]
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"Saved {len(data)} custom profiles")
    except Exception as e:
        log.error(f"Failed to save profiles: {e}")


# ──────────────────────────────────────────────────────
#  ИНТЕГРАЦИЯ ГЕНЕРАТОРА СТРАТЕГИЙ
# ──────────────────────────────────────────────────────

try:
    from generator import (
        StrategyGenerator, StrategyTester, StrategyCandidate,
        TestResult, build_profile_from_candidate, get_categories_info,
        get_flowseal_presets, FLOWSEAL_PRESETS,
        FOOLING_METHODS, SPLIT_POSITIONS, TLS_MODS,
    )
    HAS_GENERATOR = True
    log.info("Generator module loaded OK")

    # Конвертируем Flowseal пресеты в Profile объекты
    FLOWSEAL_PROFILES = []
    exact_flowseal_profiles = 0
    for preset in FLOWSEAL_PRESETS:
        exact = build_flowseal_runtime_profile(preset["name"], preset["desc"])
        FLOWSEAL_PROFILES.append(Profile(
            name=preset["name"],
            desc=preset["desc"],
            args=list(exact["args"]) if exact else preset["args"],
            builtin=True,
            binary=exact["binary"] if exact else "",
        ))
        if exact:
            exact_flowseal_profiles += 1
    log.info(
        f"Loaded {len(FLOWSEAL_PROFILES)} Flowseal profiles "
        f"({exact_flowseal_profiles} exact upstream)"
    )

except ImportError as e:
    HAS_GENERATOR = False
    FLOWSEAL_PROFILES = []
    log.warning(f"Generator module not available: {e}")


def run_auto_generator(domain: str, settings: dict, targets: dict,
                        include_risky: bool = False,
                        include_slow: bool = False,
                        max_working: int = 5,
                        timeout: int = 5,
                        categories: list = None,
                        progress_cb=None,
                        stop_flag=None) -> tuple:
    """
    Запускает автоматическую генерацию + тестирование стратегий.

    Возвращает: (best_profile: Profile, all_results: list)
    all_results: [(StrategyCandidate, TestResult), ...]
    """
    if not HAS_GENERATOR:
        return None, []

    winws_bin = settings.get("winws_bin", "")
    lua_dir = settings.get("lua_dir", "")

    if not winws_bin or not os.path.isfile(winws_bin):
        log.error(f"winws2 not found: {winws_bin}")
        return None, []

    # 1. Генерация кандидатов
    gen = StrategyGenerator()
    candidates = gen.generate_all(include_risky=include_risky,
                                   include_slow=include_slow)

    # Фильтр по категориям если задан
    if categories:
        candidates = [c for c in candidates if c.category in categories]
        log.info(f"Filtered to {len(candidates)} candidates by categories: {categories}")

    if not candidates:
        return None, []

    # 2. Тестирование
    tester = StrategyTester(winws_bin, lua_dir)
    results = tester.test_candidates(
        candidates=candidates,
        domain=domain,
        timeout=timeout,
        max_ok_ms=4000,
        max_working=max_working,
        progress_cb=progress_cb,
        stop_flag=stop_flag,
    )

    # 3. Выбор лучшей
    working = [(c, r) for c, r in results if r.ok]
    if not working:
        log.warning("No working strategies found")
        return None, results

    # Сортируем по скорости
    working.sort(key=lambda x: x[1].time_ms)
    best_candidate, best_result = working[0]

    # 4. Построение профиля
    hostlist_path = write_hostlist(targets)
    try:
        rel = os.path.relpath(hostlist_path, WINWS_DIR)
    except ValueError:
        rel = hostlist_path

    full_args = build_profile_from_candidate(
        best_candidate, hostlist_rel=rel,
        include_http=True, include_quic=True,
    )

    profile = Profile(
        name=f"Авто: {best_candidate.name}",
        desc=(f"Найдена автоматически для {domain}. "
              f"Время: {best_result.time_ms}ms. "
              f"{best_candidate.desc}"),
        args=full_args,
    )

    log.info(f"Best strategy: {best_candidate.name}, {best_result.time_ms}ms")
    return profile, results


def candidate_to_profile(candidate, targets: dict,
                          name: str = None) -> 'Profile':
    """Конвертирует StrategyCandidate в Profile."""
    if not HAS_GENERATOR:
        return None

    hostlist_path = write_hostlist(targets)
    try:
        rel = os.path.relpath(hostlist_path, WINWS_DIR)
    except ValueError:
        rel = hostlist_path

    full_args = build_profile_from_candidate(
        candidate, hostlist_rel=rel,
        include_http=True, include_quic=True,
    )

    return Profile(
        name=name or f"Авто: {candidate.name}",
        desc=candidate.desc,
        args=full_args,
    )


# ──────────────────────────────────────────────────────
#  TELEGRAM WEBSOCKET PROXY
# ──────────────────────────────────────────────────────

try:
    from tg_ws_proxy import TelegramWsProxy, WS_PROXY_AVAILABLE, DEFAULT_PORT
    HAS_TG_PROXY = WS_PROXY_AVAILABLE
    log.info(f"TG WS Proxy module loaded, available={WS_PROXY_AVAILABLE}")
except ImportError as e:
    HAS_TG_PROXY = False
    TelegramWsProxy = None
    DEFAULT_PORT = 1080
    log.info(f"TG WS Proxy module not available: {e}")

# Глобальный экземпляр прокси (один на всё приложение)
_tg_proxy_instance: 'TelegramWsProxy' = None


def get_tg_proxy(port: int = None) -> 'TelegramWsProxy':
    """Возвращает/создаёт экземпляр TG WS прокси."""
    global _tg_proxy_instance
    if _tg_proxy_instance is None and HAS_TG_PROXY:
        _tg_proxy_instance = TelegramWsProxy(port=port or DEFAULT_PORT)
    return _tg_proxy_instance


def start_tg_proxy(port: int = None) -> tuple:
    """Запускает Telegram WS прокси."""
    global _tg_proxy_instance
    if not HAS_TG_PROXY:
        return False, ("Нужна библиотека cryptography.\n"
                        "Установите: pip install cryptography")
    desired_port = port or DEFAULT_PORT
    if _tg_proxy_instance is not None and _tg_proxy_instance.port != desired_port:
        if _tg_proxy_instance.is_running:
            ok, msg = _tg_proxy_instance.stop()
            if not ok:
                return False, msg
        _tg_proxy_instance = None
    proxy = get_tg_proxy(desired_port)
    if proxy is None:
        return False, "Не удалось создать прокси"
    return proxy.start()


def stop_tg_proxy() -> tuple:
    """Останавливает Telegram WS прокси."""
    global _tg_proxy_instance
    if _tg_proxy_instance is None:
        return True, "Не запущен"
    ok, msg = _tg_proxy_instance.stop()
    if ok and not _tg_proxy_instance.is_running:
        _tg_proxy_instance = None
    return ok, msg


def is_tg_proxy_running() -> bool:
    return _tg_proxy_instance is not None and _tg_proxy_instance.is_running


def get_tg_proxy_link(port: int = None) -> str:
    p = port or (_tg_proxy_instance.port if _tg_proxy_instance else DEFAULT_PORT)
    return f"tg://socks?server=127.0.0.1&port={p}"


def get_tg_proxy_stats() -> str:
    if _tg_proxy_instance:
        return _tg_proxy_instance.get_stats_str()
    return "Прокси не запущен"
