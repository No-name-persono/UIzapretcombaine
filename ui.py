"""
ui.py — Графический интерфейс Zapret2 Manager
Окно установки (SetupWindow) и основное окно (MainApp)
"""

import os
import sys
import json
import shutil
import subprocess
import datetime
import threading
import time
import logging
import traceback
import atexit
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from flowseal_profiles import build_flowseal_runtime_profile
from upstreams import sync_external_components

from core import (
    Bootstrap, Backend, Profile,
    BUILTIN_PROFILES, APP_NAME, APP_VERSION,
    WINWS_DIR, CUSTOM_LISTS_DIR, LOG_DIR, ZAPRET_DIR, DATA_DIR,
    is_admin, request_admin,
    load_settings, save_settings,
    load_custom_profiles, save_custom_profiles,
    find_blockcheck, run_blockcheck, terminate_job,
    load_targets, save_targets, get_all_domains, write_hostlist,
    parse_blockcheck_output, generate_profile_from_results,
    generate_default_profile, DEFAULT_TARGETS,
    load_domain_strategies, save_domain_strategies, build_combo_profile,
    build_profile_from_raw_strategy,
    verify_strategy, verify_domain_strategies,
    HAS_GENERATOR, run_auto_generator, candidate_to_profile,
    FLOWSEAL_PROFILES,
    HAS_TG_PROXY, start_tg_proxy, stop_tg_proxy, is_tg_proxy_running,
    get_tg_proxy_link, get_tg_proxy_stats, DEFAULT_PORT,
    is_autostart_enabled, set_autostart_enabled,
    AUTO_SYNC_INTERVAL_DAYS, is_monthly_auto_sync_due,
    kill_process_images,
)

log = logging.getLogger("ui")

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes as wt

    _user32 = ctypes.windll.user32
    _shell32 = ctypes.windll.shell32
    _kernel32 = ctypes.windll.kernel32

    WM_TRAYICON = 0x8001
    WM_NULL = 0x0000
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONDOWN = 0x0204
    WM_RBUTTONUP = 0x0205
    WM_CONTEXTMENU = 0x007B
    NIN_SELECT = 0x0400
    NIN_KEYSELECT = 0x0401
    _user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
    _user32.RegisterWindowMessageW.restype = wt.UINT
    WM_TASKBARCREATED = _user32.RegisterWindowMessageW("TaskbarCreated")

    NIM_ADD = 0x00000000
    NIM_MODIFY = 0x00000001
    NIM_DELETE = 0x00000002
    NIM_SETVERSION = 0x00000004

    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004

    NOTIFYICON_VERSION_4 = 4
    IDI_APPLICATION = 32512

    MF_STRING = 0x00000000
    MF_SEPARATOR = 0x00000800
    TPM_RIGHTBUTTON = 0x0002
    TPM_RETURNCMD = 0x0100
    TPM_NONOTIFY = 0x0080

    MENU_RESTORE = 1001
    MENU_STOP_ALL = 1002
    MENU_EXIT = 1003

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wt.DWORD),
            ("Data2", wt.WORD),
            ("Data3", wt.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]


    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wt.DWORD),
            ("hWnd", wt.HWND),
            ("uID", wt.UINT),
            ("uFlags", wt.UINT),
            ("uCallbackMessage", wt.UINT),
            ("hIcon", wt.HANDLE),
            ("szTip", wt.WCHAR * 128),
            ("dwState", wt.DWORD),
            ("dwStateMask", wt.DWORD),
            ("szInfo", wt.WCHAR * 256),
            ("uVersion", wt.UINT),
            ("szInfoTitle", wt.WCHAR * 64),
            ("dwInfoFlags", wt.DWORD),
            ("guidItem", GUID),
            ("hBalloonIcon", wt.HANDLE),
        ]


    _WNDPROC = ctypes.WINFUNCTYPE(wt.LPARAM, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    _shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    _shell32.Shell_NotifyIconW.restype = wt.BOOL
    _user32.LoadIconW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
    _user32.LoadIconW.restype = wt.HANDLE
    _user32.CreatePopupMenu.restype = wt.HMENU
    _user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, wt.WPARAM, wt.LPCWSTR]
    _user32.AppendMenuW.restype = wt.BOOL
    _user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, ctypes.c_void_p]
    _user32.TrackPopupMenu.restype = wt.UINT
    _user32.DestroyMenu.argtypes = [wt.HMENU]
    _user32.DestroyMenu.restype = wt.BOOL
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    _user32.GetCursorPos.restype = wt.BOOL
    _user32.SetForegroundWindow.argtypes = [wt.HWND]
    _user32.SetForegroundWindow.restype = wt.BOOL
    _user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    _user32.PostMessageW.restype = wt.BOOL
    _user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    _user32.DefWindowProcW.restype = wt.LPARAM
    _user32.RegisterClassW.restype = wt.ATOM
    _user32.CreateWindowExW.argtypes = [
        wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p,
    ]
    _user32.CreateWindowExW.restype = wt.HWND
    _user32.DestroyWindow.argtypes = [wt.HWND]
    _user32.DestroyWindow.restype = wt.BOOL
    _user32.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]
    _user32.UnregisterClassW.restype = wt.BOOL
    _kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    _kernel32.GetModuleHandleW.restype = wt.HINSTANCE


    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wt.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wt.HINSTANCE),
            ("hIcon", wt.HICON),
            ("hCursor", wt.HANDLE),
            ("hbrBackground", wt.HBRUSH),
            ("lpszMenuName", wt.LPCWSTR),
            ("lpszClassName", wt.LPCWSTR),
        ]


    _user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]


    class WindowsTrayIcon:
        def __init__(self, root, on_restore, on_stop_all, on_exit):
            self.root = root
            self.on_restore = on_restore
            self.on_stop_all = on_stop_all
            self.on_exit = on_exit
            self.hwnd = None
            self._icon_id = 1
            self._installed = False
            self._class_name = f"Zapret2ManagerTray_{os.getpid()}_{id(self)}"
            self._hinstance = None
            self._wndproc_ref = None
            self._class_registered = False
            self._pending_action = None
            self._action_lock = threading.Lock()

        @property
        def installed(self) -> bool:
            return self._installed

        def install(self) -> bool:
            if self._installed:
                return True
            try:
                self.root.update_idletasks()
                self._hinstance = _kernel32.GetModuleHandleW(None)
                self._wndproc_ref = _WNDPROC(self._wndproc)

                wc = WNDCLASSW()
                wc.lpfnWndProc = self._wndproc_ref
                wc.hInstance = self._hinstance
                wc.lpszClassName = self._class_name
                atom = _user32.RegisterClassW(ctypes.byref(wc))
                if not atom:
                    log.error("Tray window class registration failed")
                    return False
                self._class_registered = True

                self.hwnd = _user32.CreateWindowExW(
                    0,
                    self._class_name,
                    self._class_name,
                    0,
                    0,
                    0,
                    0,
                    0,
                    None,
                    None,
                    self._hinstance,
                    None,
                )
                if not self.hwnd:
                    log.error("Tray message window creation failed")
                    self._destroy_message_window()
                    return False

                if not self._add_shell_icon():
                    self._destroy_message_window()
                    return False
                self._installed = True
                return True
            except Exception:
                log.error("Tray install failed:\n%s", traceback.format_exc())
                self._destroy_message_window()
                return False

        def remove(self):
            if self._installed:
                try:
                    data = self._build_nid()
                    _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
                except Exception:
                    pass
            self._installed = False
            self._destroy_message_window()

        def update_tooltip(self, text: str):
            if not self._installed:
                return
            try:
                data = self._build_nid(tooltip=text)
                _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))
            except Exception:
                pass

        def _build_nid(self, tooltip: str = ""):
            data = NOTIFYICONDATAW()
            data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            data.hWnd = self.hwnd
            data.uID = self._icon_id
            data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            data.uCallbackMessage = WM_TRAYICON
            data.hIcon = _user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
            data.szTip = (tooltip or APP_NAME)[:127]
            return data

        def _add_shell_icon(self) -> bool:
            data = self._build_nid()
            if not _shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
                log.error("Shell_NotifyIconW(NIM_ADD) failed")
                return False
            data.uVersion = NOTIFYICON_VERSION_4
            _shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(data))
            return True

        def _destroy_message_window(self):
            try:
                if self.hwnd:
                    _user32.DestroyWindow(self.hwnd)
            except Exception:
                pass
            self.hwnd = None
            try:
                if self._class_registered and self._hinstance:
                    _user32.UnregisterClassW(self._class_name, self._hinstance)
            except Exception:
                pass
            self._class_registered = False
            self._wndproc_ref = None

        def _show_menu(self):
            if not self.hwnd:
                return
            menu = _user32.CreatePopupMenu()
            if not menu:
                return
            try:
                _user32.AppendMenuW(menu, MF_STRING, MENU_RESTORE, "Развернуть")
                _user32.AppendMenuW(menu, MF_STRING, MENU_STOP_ALL, "Остановить обход и прокси")
                _user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                _user32.AppendMenuW(menu, MF_STRING, MENU_EXIT, "Выйти")

                pt = wt.POINT()
                _user32.GetCursorPos(ctypes.byref(pt))
                _user32.SetForegroundWindow(self.hwnd)
                cmd = _user32.TrackPopupMenu(
                    menu,
                    TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                    pt.x,
                    pt.y,
                    0,
                    self.hwnd,
                    None,
                )
                _user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
            finally:
                _user32.DestroyMenu(menu)

            if cmd == MENU_RESTORE:
                self._queue_action("restore")
            elif cmd == MENU_STOP_ALL:
                self._queue_action("stop_all")
            elif cmd == MENU_EXIT:
                self._queue_action("exit")

        def _queue_action(self, action: str):
            with self._action_lock:
                self._pending_action = action

        def consume_action(self):
            with self._action_lock:
                action = self._pending_action
                self._pending_action = None
                return action

        def _wndproc(self, hwnd, msg, wparam, lparam):
            if msg == WM_TRAYICON:
                event = int(lparam) & 0xFFFF
                if event in (
                    WM_LBUTTONDOWN,
                    WM_LBUTTONUP,
                    WM_LBUTTONDBLCLK,
                    NIN_SELECT,
                    NIN_KEYSELECT,
                ):
                    self._queue_action("restore")
                    return 0
                if event == WM_CONTEXTMENU:
                    self._show_menu()
                    return 0
            if msg == WM_TASKBARCREATED and self._installed:
                self._add_shell_icon()
                return 0
            return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)
else:
    WindowsTrayIcon = None

# Импорт генератора если доступен
if HAS_GENERATOR:
    from generator import (
        StrategyGenerator, get_categories_info,
    )


# ──────────────────────────────────────────────────────
#  ТЕМА
# ──────────────────────────────────────────────────────
class T:
    BG = "#1a1b2e"; CARD = "#232440"; INP = "#2a2b4a"; HOV = "#2f3055"
    FG = "#e0e0f0"; DIM = "#8888aa"; BR = "#ffffff"
    ACC = "#6c5ce7"; AH = "#7f6ef0"; OK = "#00b894"; OKD = "#1a3a32"
    ERR = "#e74c3c"; ERRD = "#3a1a1a"; WARN = "#fdcb6e"; INFO = "#74b9ff"
    BRD = "#3a3b5c"; BRF = "#6c5ce7"
    F = ("Segoe UI", 11); FB = ("Segoe UI", 11, "bold")
    FL = ("Segoe UI", 14, "bold"); FT = ("Segoe UI", 20, "bold")
    FM = ("Consolas", 10); FS = ("Segoe UI", 9)


# ──────────────────────────────────────────────────────
#  ОКНО УСТАНОВКИ
# ──────────────────────────────────────────────────────
class SetupWindow:
    """Окно первоначальной загрузки zapret-win-bundle."""

    def __init__(self, bootstrap: Bootstrap):
        self.bootstrap = bootstrap
        self.success = False
        self.log = logging.getLogger("setup_ui")

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — Установка")
        self.root.geometry("640x520")
        self.root.configure(bg=T.BG)
        self.root.resizable(False, False)

        self._build()
        self.log.info("Setup window created")

        # АВТОЗАПУСК скачивания через 500мс после показа окна
        self.log.info("Scheduling auto-install in 500ms")
        self.root.after(500, self._start_install)

    def _build(self):
        tk.Label(self.root, text="⚡ Первоначальная настройка",
                 font=T.FL, bg=T.BG, fg=T.FG).pack(pady=(20, 4))
        tk.Label(self.root, text="Скрипт скачает zapret-win-bundle с GitHub (~50 MB)",
                 font=T.FS, bg=T.BG, fg=T.DIM).pack(pady=(0, 4))

        admin_text = "✓ Запущено от администратора" if is_admin() else "⚠ Нет прав администратора (WinDivert не запустится)"
        admin_color = T.OK if is_admin() else T.WARN
        tk.Label(self.root, text=admin_text, font=("Segoe UI", 10), bg=T.BG, fg=admin_color).pack(pady=(0, 12))

        # Шаги
        sf = tk.Frame(self.root, bg=T.CARD, highlightbackground=T.BRD, highlightthickness=1)
        sf.pack(fill="x", padx=24, pady=(0, 8))

        self.step_names = ["Директории", "Скачивание zapret-win-bundle", "Проверка компонентов"]
        self.step_w = {}
        for i, name in enumerate(self.step_names):
            row = tk.Frame(sf, bg=T.CARD)
            row.pack(fill="x", padx=16, pady=(8 if i == 0 else 3, 8 if i == len(self.step_names) - 1 else 3))
            ind = tk.Label(row, text="○", font=T.FS, bg=T.CARD, fg=T.DIM, width=3)
            ind.pack(side="left")
            lbl = tk.Label(row, text=name, font=T.F, bg=T.CARD, fg=T.DIM)
            lbl.pack(side="left")
            st = tk.Label(row, text="", font=T.FS, bg=T.CARD, fg=T.DIM)
            st.pack(side="right")
            self.step_w[i] = (ind, lbl, st)

        # Статус — крупный текст что происходит
        self.status_label = tk.Label(self.root, text="⏳ Загрузка начнётся автоматически...",
                                      font=T.FB, bg=T.BG, fg=T.WARN)
        self.status_label.pack(pady=(8, 4))

        # Прогресс
        pf = tk.Frame(self.root, bg=T.BG)
        pf.pack(fill="x", padx=24, pady=(0, 4))
        self.dl_label = tk.Label(pf, text="Ожидание...", font=T.FS, bg=T.BG, fg=T.DIM)
        self.dl_label.pack(anchor="w")
        self.dl_var = tk.DoubleVar(value=0)
        ttk.Progressbar(pf, variable=self.dl_var, maximum=100).pack(fill="x")

        # Лог
        lf = tk.Frame(self.root, bg=T.CARD, highlightbackground=T.BRD, highlightthickness=1)
        lf.pack(fill="both", expand=True, padx=24, pady=(8, 8))
        self.log_text = tk.Text(lf, bg=T.INP, fg=T.FG, font=T.FM, bd=0,
                                 highlightthickness=0, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Кнопка (изначально disabled — установка автоматическая)
        bf = tk.Frame(self.root, bg=T.BG)
        bf.pack(fill="x", padx=24, pady=(0, 16))
        self.btn = tk.Button(bf, text="Идёт загрузка...", font=T.FB, bg="#444466",
                              fg=T.BR, bd=0, padx=24, pady=8, cursor="hand2",
                              state="disabled")
        self.btn.pack(side="right")

    def _add_log(self, msg):
        def _do():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _do)

    def _set_step(self, idx, status, msg=""):
        def _do():
            if idx not in self.step_w:
                return
            ind, lbl, st = self.step_w[idx]
            cfg = {
                "run": ("◉", T.WARN, T.FG, "...", T.WARN),
                "ok": ("✓", T.OK, T.OK, msg[:50], T.OK),
                "fail": ("✗", T.ERR, T.ERR, msg[:50], T.ERR),
            }
            c = cfg.get(status, cfg["run"])
            ind.configure(text=c[0], fg=c[1])
            lbl.configure(fg=c[2])
            st.configure(text=c[3], fg=c[4])
        self.root.after(0, _do)

    def _dl_progress(self, pct, downloaded, total):
        mb_d = downloaded / 1048576
        mb_t = total / 1048576
        self.root.after(0, lambda: self.dl_var.set(pct))
        self.root.after(0, lambda: self.dl_label.configure(
            text=f"Скачано: {mb_d:.1f} / {mb_t:.1f} MB ({pct}%)"))
        self.root.after(0, lambda: self.status_label.configure(
            text=f"📥 Скачивание... {pct}%", fg=T.INFO))

    def _set_status(self, text, color=None):
        self.root.after(0, lambda: self.status_label.configure(
            text=text, fg=color or T.WARN))

    def _start_install(self):
        self.log.info("_start_install called")
        self._add_log("Запуск установки...")
        self._set_status("⏳ Подготовка к загрузке...", T.WARN)
        self.btn.configure(state="disabled", text="Идёт установка...", bg="#444466")
        threading.Thread(target=self._do_install, daemon=True).start()

    def _do_install(self):
        self.log.info("Install thread started")
        self._add_log("Поток установки запущен")
        try:
            # Перехватываем логи bootstrap в UI
            class UIHandler(logging.Handler):
                def __init__(self, add_log_fn):
                    super().__init__()
                    self.add_log_fn = add_log_fn
                def emit(self, record):
                    try:
                        self.add_log_fn(self.format(record))
                    except Exception:
                        pass

            handler = UIHandler(self._add_log)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.bootstrap.log.addHandler(handler)

            def step_cb(name, num, total):
                self._set_step(num - 1, "run")
                self._set_status(f"⏳ [{num}/{total}] {name}...", T.WARN)
                self._add_log(f"\n[{num}/{total}] {name}...")

            self.log.info("Calling full_setup...")
            self._add_log("Вызов full_setup()...")

            steps = self.bootstrap.full_setup(
                step_cb=step_cb,
                dl_progress_cb=self._dl_progress
            )

            self.log.info(f"full_setup returned {len(steps)} steps")
            self._add_log(f"Получено {len(steps)} шагов")

            for i, (name, ok, msg) in enumerate(steps):
                self._set_step(i, "ok" if ok else "fail", msg)
                self.log.info(f"  Step {i}: {name} = {'OK' if ok else 'FAIL'}: {msg}")

            all_ok = all(ok for _, ok, _ in steps)
            self.success = all_ok

            self.bootstrap.log.removeHandler(handler)

            self.log.info(f"Install complete. all_ok={all_ok}, scheduling finish()")
            self._add_log(f"\nВсе шаги выполнены. Успех: {all_ok}")

            def finish():
                self.log.info("finish() called on main thread")
                try:
                    self.dl_var.set(100)
                    if all_ok:
                        self._set_status("✅ Установка завершена! Запуск через 2 сек...", T.OK)
                        self.btn.configure(state="disabled", text="✓ Установлено!", bg=T.OK)
                        self._add_log("\n✓ Установка завершена! Окно закроется автоматически...")
                        self.log.info("Success! Auto-closing in 2s")
                        # Автоматически закрываем окно через 2 секунды
                        self.root.after(2000, self._auto_close)
                    else:
                        self._set_status("❌ Есть ошибки — проверьте лог ниже", T.ERR)
                        self.btn.configure(state="normal", text="↻ Повторить",
                                            bg=T.WARN, command=self._start_install)
                        self._add_log("\n⚠ Есть ошибки. Проверьте лог.")
                        self.log.warning("Setup had errors, waiting for user")
                except Exception as e:
                    self.log.error(f"finish() error: {traceback.format_exc()}")
                    self._add_log(f"finish() ошибка: {e}")

            self.root.after(0, finish)
            self.log.info("finish() scheduled via root.after(0)")

        except Exception as e:
            self.log.error(f"Install error: {traceback.format_exc()}")
            self._add_log(f"\n✗ ОШИБКА: {e}\n{traceback.format_exc()}")
            self._set_status(f"❌ Ошибка: {e}", T.ERR)
            self.root.after(0, lambda: self.btn.configure(
                state="normal", text="↻ Повторить", bg=T.WARN, command=self._start_install))

    def _auto_close(self):
        """Автоматически закрывает окно установки."""
        self.log.info("_auto_close: destroying setup window")
        try:
            self.root.destroy()
        except Exception as e:
            self.log.error(f"_auto_close error: {e}")

    def run(self) -> bool:
        self.log.info("SetupWindow.run() entering mainloop")
        self.root.mainloop()
        self.log.info(f"SetupWindow.run() mainloop exited, success={self.success}")
        return self.success


# ──────────────────────────────────────────────────────
#  ОСНОВНОЕ ОКНО
# ──────────────────────────────────────────────────────
class MainApp:

    def __init__(self, bootstrap: Bootstrap):
        self.bootstrap = bootstrap
        self.log = logging.getLogger("main_app")
        self.log.info("MainApp init")

        try:
            self.settings = load_settings(bootstrap)
            self.backend = Backend(self.settings)
            self.profiles = list(BUILTIN_PROFILES) + list(FLOWSEAL_PROFILES) + load_custom_profiles()
            self.active_idx = 0
            self._sync_in_progress = False
            self._hidden_to_tray = False
            self._exit_requested = False
            self._exit_cleanup_done = False
            self._tray_restore_job = None
            self._tray_action_poll_job = None
            self.tray_icon = None

            self.root = tk.Tk()
            self.root.title(APP_NAME)
            self.root.geometry("1020x750")
            self.root.minsize(860, 600)
            self.root.configure(bg=T.BG)
            self._styles()
            self._ui()
            self._setup_lifecycle()
            self._poll()
            self.root.after(1500, self._maybe_run_monthly_auto_sync)
            self.log.info("MainApp ready")
        except Exception as e:
            self.log.error(f"MainApp init error: {traceback.format_exc()}")
            raise

    def run(self):
        self.log.info("Entering mainloop")
        self.root.mainloop()

    def _setup_lifecycle(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        atexit.register(self._atexit_cleanup)
        if "--no-tray" in sys.argv or os.environ.get("ZAPRET2_DISABLE_TRAY") == "1":
            self.log.warning("Tray icon disabled by startup option")
            return
        if WindowsTrayIcon is not None:
            self.root.after(0, self._setup_tray_icon)

    def _setup_tray_icon(self):
        if self.tray_icon is not None:
            return
        try:
            tray = WindowsTrayIcon(
                self.root,
                on_restore=self._queue_restore_from_tray,
                on_stop_all=self._stop_all_from_tray,
                on_exit=self._request_full_exit,
            )
            if tray.install():
                self.tray_icon = tray
                self._update_tray_tooltip()
                self._schedule_tray_action_poll()
            else:
                self.log.warning("Tray icon install skipped")
        except Exception:
            self.log.error("Tray setup failed:\n%s", traceback.format_exc())

    def _schedule_tray_action_poll(self):
        if self._exit_requested or self._tray_action_poll_job is not None:
            return
        self._tray_action_poll_job = self.root.after(100, self._poll_tray_actions)

    def _poll_tray_actions(self):
        self._tray_action_poll_job = None
        try:
            action = self.tray_icon.consume_action() if self.tray_icon else None
            if action == "restore":
                self._queue_restore_from_tray()
            elif action == "stop_all":
                self._stop_all_from_tray()
            elif action == "exit":
                self._request_full_exit()
        except Exception:
            self.log.error("Tray action polling failed:\n%s", traceback.format_exc())
        finally:
            self._schedule_tray_action_poll()

    def _on_window_close(self):
        self.log.info("Window close requested: exit_requested=%s hidden_to_tray=%s", self._exit_requested, self._hidden_to_tray)
        if self._exit_requested:
            self._perform_full_exit()
            return
        if self.tray_icon and self.tray_icon.installed:
            self._hide_to_tray()
        else:
            self._request_full_exit()

    def _hide_to_tray(self):
        if self._hidden_to_tray or self._exit_requested:
            return
        self.log.info("Hiding window to tray")
        self._hidden_to_tray = True
        self._log_ui("Окно скрыто в трей. Полный выход доступен через значок в области уведомлений.", "info")
        self.root.withdraw()

    def _queue_restore_from_tray(self):
        if self._exit_requested:
            return
        if self._tray_restore_job is not None:
            return
        self.log.info("Queueing tray restore")
        self._tray_restore_job = self.root.after(150, self._restore_from_tray)

    def _restore_from_tray(self):
        self._tray_restore_job = None
        if self._exit_requested:
            return
        self.log.info("Restoring window from tray")
        self._hidden_to_tray = False
        self.root.deiconify()
        self.root.update_idletasks()
        self.root.state("normal")
        self.root.lift()
        if sys.platform == "win32":
            try:
                hwnd = self.root.winfo_id()
                _user32.ShowWindow(hwnd, 9)
                _user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        try:
            self.root.after(10, self.root.focus_force)
        except Exception:
            pass

    def _stop_runtime_services(self, reason: str = "manual") -> list:
        messages = []

        try:
            if getattr(self, "bc_process", None):
                self._bc_stopping = True
                self._bc_kill_current()
                self.bc_process = None
                messages.append("blockcheck остановлен")
        except Exception as e:
            messages.append(f"blockcheck: {e}")

        try:
            if self.backend.is_running:
                ok, msg = self.backend.stop()
                messages.append(f"DPI: {msg}" if ok else f"DPI stop error: {msg}")
            else:
                messages.append("DPI: уже остановлен")
        except Exception as e:
            messages.append(f"DPI: {e}")

        try:
            if is_tg_proxy_running():
                ok, msg = stop_tg_proxy()
                messages.append(f"TG Proxy: {msg}" if ok else f"TG Proxy stop error: {msg}")
            else:
                messages.append("TG Proxy: уже остановлен")
        except Exception as e:
            messages.append(f"TG Proxy: {e}")

        self.log.info("Runtime services stop (%s): %s", reason, "; ".join(messages))
        return messages

    def _stop_all_from_tray(self):
        messages = self._stop_runtime_services(reason="tray")
        for msg in messages:
            level = "error" if "error" in msg.lower() else ("warning" if "уже остановлен" in msg.lower() else "success")
            self._log_ui(msg, level)
        self._upd_ui()
        self._tg_update_ui()

    def _confirm_full_exit(self):
        services_active = self.backend.is_running or is_tg_proxy_running()
        msg = "Полностью закрыть приложение?"
        if services_active:
            msg += "\n\nТекущая DPI-модификация и Telegram WS Proxy будут остановлены."
        if messagebox.askyesno("Выход", msg):
            self._request_full_exit()

    def _request_full_exit(self):
        if self._exit_requested:
            return
        self.log.info("Full exit requested")
        self._exit_requested = True
        self.root.after(0, self._perform_full_exit)

    def _perform_full_exit(self):
        if self._exit_cleanup_done:
            try:
                self.root.destroy()
            except Exception:
                pass
            return

        self.log.info("Performing full exit")
        self._exit_cleanup_done = True
        try:
            if self._tray_restore_job is not None:
                self.root.after_cancel(self._tray_restore_job)
        except Exception:
            pass
        self._tray_restore_job = None
        try:
            if self._tray_action_poll_job is not None:
                self.root.after_cancel(self._tray_action_poll_job)
        except Exception:
            pass
        self._tray_action_poll_job = None
        self._stop_runtime_services(reason="exit")
        try:
            kill_process_images(logger=self.log)
        except Exception:
            self.log.error("Final zapret process cleanup failed:\n%s", traceback.format_exc())
        try:
            if self.tray_icon:
                self.tray_icon.remove()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _atexit_cleanup(self):
        if self._exit_cleanup_done:
            return
        self._exit_cleanup_done = True
        try:
            self._stop_runtime_services(reason="atexit")
        except Exception:
            pass
        try:
            kill_process_images(logger=self.log)
        except Exception:
            pass

    def _update_tray_tooltip(self):
        if not self.tray_icon or not self.tray_icon.installed:
            return
        dpi_state = "DPI ON" if self.backend.is_running else "DPI OFF"
        tg_state = "TG ON" if is_tg_proxy_running() else "TG OFF"
        self.tray_icon.update_tooltip(f"{APP_NAME} | {dpi_state} | {tg_state}")

    # ── Стили ──────────────────────────────────────────
    def _refresh_quick_action_buttons(self):
        if hasattr(self, "quick_tg_btn"):
            self.quick_tg_btn.configure(
                text="Остановить TG Proxy" if is_tg_proxy_running() else "Запустить TG Proxy"
            )

    def _styles(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(".", background=T.BG, foreground=T.FG, font=T.F)
        s.configure("TNotebook", background=T.BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=T.CARD, foreground=T.DIM, font=T.FB, padding=[18, 8])
        s.map("TNotebook.Tab", background=[("selected", T.ACC)], foreground=[("selected", T.BR)])
        s.configure("Treeview", background=T.INP, foreground=T.FG, fieldbackground=T.INP,
                     borderwidth=0, font=T.F, rowheight=34)
        s.configure("Treeview.Heading", background=T.CARD, foreground=T.DIM, font=T.FB)
        s.map("Treeview", background=[("selected", T.ACC)], foreground=[("selected", T.BR)])

    # ── Виджеты ────────────────────────────────────────
    def _card(self, p):
        return tk.Frame(p, bg=T.CARD, highlightbackground=T.BRD, highlightthickness=1)
    def _entry(self, p, v):
        return tk.Entry(p, textvariable=v, bg=T.INP, fg=T.FG, font=T.F, insertbackground=T.FG, bd=0,
                         highlightthickness=1, highlightbackground=T.BRD, highlightcolor=T.BRF)
    def _sbtn(self, p, t, c):
        b = tk.Button(p, text=t, font=T.FS, bg=T.HOV, fg=T.FG, bd=0, padx=12, pady=5,
                       cursor="hand2", activebackground=T.ACC, activeforeground=T.BR, command=c)
        b.bind("<Enter>", lambda e, b=b: b.configure(bg=T.ACC))
        b.bind("<Leave>", lambda e, b=b: b.configure(bg=T.HOV))
        return b
    def _abtn(self, p, t, col, c):
        return tk.Button(p, text=t, font=T.FB, bg=col, fg=T.BR, bd=0, padx=16, pady=8,
                          cursor="hand2", activebackground=T.AH, command=c)

    # ── Лог в UI ───────────────────────────────────────
    def _log_ui(self, m, lv="info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        ln = f"[{ts}] {m}\n"
        self.log.info(f"[UI] {m}")
        for w in [getattr(self, "log_t", None), getattr(self, "dlog", None)]:
            if w:
                try:
                    w.configure(state="normal")
                    w.insert("end", ln, lv if w == getattr(self, "log_t", None) else ())
                    if w == getattr(self, "dlog", None):
                        count = int(w.index("end-1c").split(".")[0])
                        if count > 30:
                            w.delete("1.0", f"{count - 30}.0")
                    w.see("end")
                    w.configure(state="disabled")
                except Exception as e:
                    self.log.debug(f"Log widget error: {e}")

    # ── UI строим ──────────────────────────────────────
    def _ui(self):
        h = tk.Frame(self.root, bg=T.BG, pady=10, padx=20); h.pack(fill="x")
        tk.Label(h, text="⚡", font=("Segoe UI", 24), bg=T.BG, fg=T.ACC).pack(side="left")
        tk.Label(h, text=f" {APP_NAME}", font=T.FT, bg=T.BG, fg=T.BR).pack(side="left", padx=(4, 0))
        if not is_admin():
            tk.Label(h, text="⚠ Не админ", font=T.FS, bg=T.BG, fg=T.WARN).pack(side="right", padx=(0, 8))
        self.hstat = tk.Label(h, text="● НЕАКТИВЕН", font=T.FB, bg=T.BG, fg=T.ERR)
        self.hstat.pack(side="right", padx=10)
        tk.Frame(self.root, bg=T.BRD, height=1).pack(fill="x")

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=16, pady=(10, 14))
        self._tab_dash()
        self._tab_cfg()
        self._tab_generator()
        self._tab_telegram()
        self._tab_blockcheck()
        self._tab_lists()
        self._tab_logs()
        self._tab_set()

    # ── Панель ─────────────────────────────────────────
    def _tab_dash(self):
        t = tk.Frame(self.nb, bg=T.BG); self.nb.add(t, text="  Панель  ")
        c = self._card(t); c.pack(fill="x", padx=12, pady=(12, 6))
        r = tk.Frame(c, bg=T.CARD); r.pack(fill="x", padx=20, pady=16)
        l = tk.Frame(r, bg=T.CARD); l.pack(side="left", fill="x", expand=True)
        tk.Label(l, text="Модификация трафика", font=T.FL, bg=T.CARD, fg=T.BR).pack(anchor="w")
        self.sd = tk.Label(l, text="Нажмите для запуска winws2", font=T.F, bg=T.CARD, fg=T.DIM)
        self.sd.pack(anchor="w", pady=(4, 0))
        self.tbtn = tk.Button(r, text="▶  ЗАПУСТИТЬ", font=T.FL, bg=T.OK, fg=T.BR, bd=0,
                               padx=28, pady=10, cursor="hand2", activebackground=T.AH, command=self._toggle)
        self.tbtn.pack(side="right", padx=(20, 0))
        self.ibar = tk.Frame(c, bg=T.ERRD, height=4); self.ibar.pack(fill="x", padx=20, pady=(0, 16))
        self.ifill = tk.Frame(self.ibar, bg=T.ERR, height=4); self.ifill.place(x=0, y=0, relwidth=1, relheight=1)

        ir = tk.Frame(t, bg=T.BG); ir.pack(fill="x", padx=12, pady=6)
        for col, lbl_t, attr, clr, val in [
            (0, "ПРОФИЛЬ", "lprof", T.INFO, self.profiles[0].name),
            (1, "ОБНОВЛЕНИЕ", "lupd", T.WARN, self.settings.get("last_update") or "— никогда"),
        ]:
            cc = self._card(ir)
            cc.pack(side="left", fill="both", expand=True, padx=(0 if col == 0 else 4, 4 if col == 0 else 0))
            tk.Label(cc, text=lbl_t, font=T.FS, bg=T.CARD, fg=T.DIM).pack(anchor="w", padx=16, pady=(12, 2))
            w = tk.Label(cc, text=val, font=T.FB, bg=T.CARD, fg=clr)
            w.pack(anchor="w", padx=16, pady=(0, 12))
            setattr(self, attr, w)

        c3 = self._card(ir); c3.pack(side="left", fill="both", expand=True, padx=(4, 0))
        tk.Label(c3, text="ДЕЙСТВИЯ", font=T.FS, bg=T.CARD, fg=T.DIM).pack(anchor="w", padx=16, pady=(12, 2))
        br = tk.Frame(c3, bg=T.CARD); br.pack(anchor="w", padx=16, pady=(0, 12))
        self._sbtn(br, "Синхронизировать upstream", self._update_bundle).pack(side="left", padx=(0, 6))
        self._sbtn(br, "Скрыть в трей", self._hide_to_tray).pack(side="left", padx=(0, 6))
        self._sbtn(br, "Открыть папку", self._open_folder).pack(side="left", padx=(0, 6))
        self._sbtn(br, "Открыть лог-файл", self._open_logfile).pack(side="left")

        lc = self._card(t); lc.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        tk.Label(lc, text="СОБЫТИЯ", font=T.FS, bg=T.CARD, fg=T.DIM).pack(anchor="w", padx=16, pady=(12, 4))
        self.dlog = tk.Text(lc, height=6, bg=T.INP, fg=T.FG, font=T.FM, bd=0, insertbackground=T.FG,
                             highlightthickness=1, highlightbackground=T.BRD, state="disabled", wrap="word")
        self.dlog.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # ── Конфигурации ───────────────────────────────────
    def _tab_cfg(self):
        t = tk.Frame(self.nb, bg=T.BG); self.nb.add(t, text="  Конфигурации  ")
        lf = tk.Frame(t, bg=T.BG); lf.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=12)
        tp = tk.Frame(lf, bg=T.BG); tp.pack(fill="x", pady=(0, 8))
        tk.Label(tp, text="Профили", font=T.FL, bg=T.BG, fg=T.BR).pack(side="left")
        self._sbtn(tp, "+ Новый", self._addp).pack(side="right", padx=(6, 0))
        self._sbtn(tp, "Импорт", self._imp).pack(side="right")
        cc = self._card(lf); cc.pack(fill="both", expand=True)
        self.plb = tk.Listbox(cc, bg=T.INP, fg=T.FG, font=T.F, bd=0, selectbackground=T.ACC,
                               selectforeground=T.BR, activestyle="none", highlightthickness=0)
        self.plb.pack(fill="both", expand=True, padx=2, pady=2)
        self.plb.bind("<<ListboxSelect>>", self._onsel)
        rf = tk.Frame(t, bg=T.BG); rf.pack(side="right", fill="both", expand=True, padx=(6, 12), pady=12)
        rc = self._card(rf); rc.pack(fill="both", expand=True)
        inn = tk.Frame(rc, bg=T.CARD); inn.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(inn, text="Название:", font=T.FB, bg=T.CARD, fg=T.DIM).pack(anchor="w")
        self.cn = tk.StringVar(); self._entry(inn, self.cn).pack(fill="x", pady=(2, 8), ipady=5)
        tk.Label(inn, text="Описание:", font=T.FB, bg=T.CARD, fg=T.DIM).pack(anchor="w")
        self.cd = tk.StringVar(); self._entry(inn, self.cd).pack(fill="x", pady=(2, 8), ipady=5)
        tk.Label(inn, text="Аргументы winws2 (по строке):", font=T.FB, bg=T.CARD, fg=T.DIM).pack(anchor="w")
        self.ca = tk.Text(inn, bg=T.INP, fg=T.FG, font=T.FM, bd=0, insertbackground=T.FG,
                           wrap="word", highlightthickness=1, highlightbackground=T.BRD, highlightcolor=T.BRF)
        self.ca.pack(fill="both", expand=True, pady=(2, 10))
        br = tk.Frame(inn, bg=T.CARD); br.pack(fill="x")
        self._abtn(br, "Применить", T.OK, self._applp).pack(side="left", padx=(0, 6))
        self._abtn(br, "Сохранить", T.ACC, self._savep).pack(side="left", padx=(0, 6))
        self._abtn(br, "Удалить", T.ERR, self._delp).pack(side="left", padx=(0, 6))
        self._abtn(br, "Экспорт", T.HOV, self._expp).pack(side="right")
        # Заполняем список ПОСЛЕ создания всех виджетов правой панели
        self._refp()

    # ── Генератор стратегий ───────────────────────────
    def _tab_generator(self):
        t = tk.Frame(self.nb, bg=T.BG)
        self.nb.add(t, text="  ⚡ Генератор  ")

        if not HAS_GENERATOR:
            tk.Label(t, text="Модуль генератора не найден.\n"
                     "Убедитесь что generator.py находится рядом с main.py",
                     font=T.FB, bg=T.BG, fg=T.ERR).pack(expand=True)
            return

        # === Верхняя панель: кнопки ===
        top = tk.Frame(t, bg=T.BG)
        top.pack(fill="x", padx=12, pady=(8, 4))

        self.gen_start_btn = self._abtn(top, "▶ Найти стратегию", T.OK, self._gen_start)
        self.gen_start_btn.pack(side="left", padx=(0, 4))
        self._abtn(top, "■ Стоп", T.ERR, self._gen_stop).pack(side="left", padx=(0, 4))

        self.gen_status = tk.Label(top, text="Готов", font=T.FB, bg=T.BG, fg=T.DIM)
        self.gen_status.pack(side="right", padx=(0, 8))
        self.gen_found_label = tk.Label(top, text="", font=T.FB, bg=T.BG, fg=T.OK)
        self.gen_found_label.pack(side="right", padx=(0, 12))

        # === Панель быстрых пресетов Flowseal ===
        from generator import get_flowseal_presets
        presets = get_flowseal_presets()

        preset_frame = self._card(t)
        preset_frame.pack(fill="x", padx=12, pady=(0, 4))

        pf_top = tk.Frame(preset_frame, bg=T.CARD)
        pf_top.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(pf_top, text="⚡ Готовые пресеты Flowseal", font=T.FB, bg=T.CARD, fg=T.FG).pack(side="left")
        tk.Label(pf_top, text=f"({len(presets)} шт. — нажмите чтобы применить)",
                 font=T.FS, bg=T.CARD, fg=T.DIM).pack(side="left", padx=(8, 0))

        # Скроллируемая полоса кнопок
        pf_scroll = tk.Frame(preset_frame, bg=T.CARD)
        pf_scroll.pack(fill="x", padx=8, pady=(2, 6))

        pf_canvas = tk.Canvas(pf_scroll, bg=T.CARD, highlightthickness=0, height=68)
        pf_inner = tk.Frame(pf_canvas, bg=T.CARD)
        pf_canvas.create_window((0, 0), window=pf_inner, anchor="nw")
        pf_canvas.pack(fill="x")

        # Прокрутка мышью
        def _on_mousewheel(event):
            pf_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        pf_canvas.bind("<MouseWheel>", _on_mousewheel)
        pf_inner.bind("<MouseWheel>", _on_mousewheel)

        row1 = tk.Frame(pf_inner, bg=T.CARD)
        row1.pack(fill="x", pady=(0, 2))
        row2 = tk.Frame(pf_inner, bg=T.CARD)
        row2.pack(fill="x")

        for i, preset in enumerate(presets):
            target_row = row1 if i < (len(presets) + 1) // 2 else row2
            # Цвет по типу
            if "Flowseal" in preset["name"]:
                clr = "#2d5a27"  # зелёный для Flowseal
            elif "Комбо" in preset["name"]:
                clr = "#4a2d6e"  # фиолетовый для комбо
            elif "Discord" in preset["name"] or "Полный" in preset["name"]:
                clr = "#2d4a6e"  # синий для Discord/полных
            else:
                clr = T.HOV

            short_name = preset["name"].replace("Flowseal ", "").replace("Flowseal: ", "")
            btn = tk.Button(target_row, text=short_name, font=T.FS,
                            bg=clr, fg=T.FG, bd=0, padx=8, pady=4, cursor="hand2",
                            activebackground=T.ACC, activeforeground=T.BR,
                            command=lambda p=preset: self._apply_flowseal_preset(p))
            btn.pack(side="left", padx=(0, 3))
            btn.bind("<Enter>", lambda e, b=btn, c=clr: b.configure(bg=T.ACC))
            btn.bind("<Leave>", lambda e, b=btn, c=clr: b.configure(bg=c))

        pf_inner.update_idletasks()
        pf_canvas.configure(scrollregion=pf_canvas.bbox("all"),
                             xscrollcommand=lambda *a: None)

        # === Основной контент ===
        content = tk.Frame(t, bg=T.BG)
        content.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # --- Левая панель: настройки ---
        left = tk.Frame(content, bg=T.BG, width=320)
        left.pack(side="left", fill="y", padx=(0, 6))
        left.pack_propagate(False)

        # Домен для теста
        dc = self._card(left)
        dc.pack(fill="x", pady=(0, 6))
        tk.Label(dc, text="Настройки теста", font=T.FB, bg=T.CARD, fg=T.FG).pack(
            anchor="w", padx=8, pady=(6, 4))

        pf = tk.Frame(dc, bg=T.CARD)
        pf.pack(fill="x", padx=8, pady=(0, 6))

        tk.Label(pf, text="Домен:", font=T.FS, bg=T.CARD, fg=T.DIM).grid(
            row=0, column=0, sticky="w", pady=2)
        self.gen_domain_var = tk.StringVar(value="youtube.com")
        gen_domains = ["youtube.com", "discord.com", "t.me", "docs.google.com"]
        self.gen_domain_menu = ttk.Combobox(pf, textvariable=self.gen_domain_var,
                                             values=gen_domains, width=18)
        self.gen_domain_menu.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=2)

        tk.Label(pf, text="Таймаут curl (сек):", font=T.FS, bg=T.CARD, fg=T.DIM).grid(
            row=1, column=0, sticky="w", pady=2)
        self.gen_timeout_var = tk.StringVar(value="5")
        timeout_frame = tk.Frame(pf, bg=T.CARD)
        timeout_frame.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)
        for val in ["3", "5", "8", "10"]:
            tk.Radiobutton(timeout_frame, text=val, variable=self.gen_timeout_var, value=val,
                            bg=T.CARD, fg=T.FG, selectcolor=T.INP, activebackground=T.CARD,
                            activeforeground=T.FG, font=T.FS).pack(side="left")

        tk.Label(pf, text="Макс. рабочих:", font=T.FS, bg=T.CARD, fg=T.DIM).grid(
            row=2, column=0, sticky="w", pady=2)
        self.gen_maxwork_var = tk.StringVar(value="5")
        maxwork_frame = tk.Frame(pf, bg=T.CARD)
        maxwork_frame.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=2)
        for val in ["3", "5", "10", "20"]:
            tk.Radiobutton(maxwork_frame, text=val, variable=self.gen_maxwork_var, value=val,
                            bg=T.CARD, fg=T.FG, selectcolor=T.INP, activebackground=T.CARD,
                            activeforeground=T.FG, font=T.FS).pack(side="left")

        pf.columnconfigure(1, weight=1)

        # Опции
        oc = self._card(left)
        oc.pack(fill="x", pady=(0, 6))
        tk.Label(oc, text="Опции", font=T.FB, bg=T.CARD, fg=T.FG).pack(
            anchor="w", padx=8, pady=(6, 4))
        of = tk.Frame(oc, bg=T.CARD)
        of.pack(fill="x", padx=8, pady=(0, 6))

        self.gen_risky_var = tk.BooleanVar(value=False)
        tk.Checkbutton(of, text="Рискованные (badsum/badack)",
                        variable=self.gen_risky_var, bg=T.CARD, fg=T.FG,
                        selectcolor=T.INP, activebackground=T.CARD, font=T.FS).pack(anchor="w")

        self.gen_slow_var = tk.BooleanVar(value=False)
        tk.Checkbutton(of, text="WSSize (замедляет скорость!)",
                        variable=self.gen_slow_var, bg=T.CARD, fg=T.FG,
                        selectcolor=T.INP, activebackground=T.CARD, font=T.FS).pack(anchor="w")

        # Категории
        cc = self._card(left)
        cc.pack(fill="both", expand=True, pady=(0, 0))
        tk.Label(cc, text="Категории", font=T.FB, bg=T.CARD, fg=T.FG).pack(
            anchor="w", padx=8, pady=(6, 2))
        tk.Label(cc, text="(пустое = все)", font=T.FS, bg=T.CARD, fg=T.DIM).pack(
            anchor="w", padx=8, pady=(0, 4))

        cat_frame = tk.Frame(cc, bg=T.CARD)
        cat_frame.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        # Скроллируемый фрейм для категорий
        cat_canvas = tk.Canvas(cat_frame, bg=T.CARD, highlightthickness=0)
        cat_scrollbar = ttk.Scrollbar(cat_frame, orient="vertical", command=cat_canvas.yview)
        cat_inner = tk.Frame(cat_canvas, bg=T.CARD)

        cat_inner.bind("<Configure>", lambda e: cat_canvas.configure(
            scrollregion=cat_canvas.bbox("all")))
        cat_canvas.create_window((0, 0), window=cat_inner, anchor="nw")
        cat_canvas.configure(yscrollcommand=cat_scrollbar.set)

        cat_canvas.pack(side="left", fill="both", expand=True)
        cat_scrollbar.pack(side="right", fill="y")

        self.gen_cat_vars = {}
        cats_info = get_categories_info()
        for cat_id, cat_desc in cats_info.items():
            var = tk.BooleanVar(value=False)
            self.gen_cat_vars[cat_id] = var
            short = cat_id.replace("_", " ").title()
            tk.Checkbutton(cat_inner, text=short, variable=var,
                            bg=T.CARD, fg=T.FG, selectcolor=T.INP,
                            activebackground=T.CARD, font=T.FS,
                            wraplength=250, justify="left").pack(anchor="w", pady=1)

        # --- Правая панель: результаты ---
        right = tk.Frame(content, bg=T.BG)
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # Прогресс
        self.gen_progress_var = tk.DoubleVar(value=0)
        prog_frame = tk.Frame(right, bg=T.BG)
        prog_frame.pack(fill="x", pady=(0, 4))
        self.gen_progress_label = tk.Label(prog_frame, text="", font=T.FS, bg=T.BG, fg=T.DIM)
        self.gen_progress_label.pack(anchor="w")
        ttk.Progressbar(prog_frame, variable=self.gen_progress_var, maximum=100).pack(fill="x")

        # Вывод
        rc = self._card(right)
        rc.pack(fill="both", expand=True)

        self.gen_output = tk.Text(rc, bg=T.INP, fg=T.FG, font=T.FM, bd=0,
                                   insertbackground=T.FG, highlightthickness=0,
                                   state="disabled", wrap="word")
        sb = ttk.Scrollbar(rc, orient="vertical", command=self.gen_output.yview)
        self.gen_output.configure(yscrollcommand=sb.set)
        self.gen_output.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        sb.pack(side="right", fill="y", pady=4, padx=(0, 4))

        # Настраиваем теги
        self.gen_output.tag_configure("ok", foreground=T.OK)
        self.gen_output.tag_configure("fail", foreground=T.ERR)
        self.gen_output.tag_configure("slow", foreground=T.WARN)
        self.gen_output.tag_configure("info", foreground=T.INFO)
        self.gen_output.tag_configure("dim", foreground=T.DIM)

        # Результаты (кнопки для рабочих стратегий)
        self.gen_results_frame = tk.Frame(right, bg=T.BG)
        self.gen_results_frame.pack(fill="x", pady=(4, 0))

        # Внутренние переменные
        self._gen_stopping = False
        self._gen_working_results = []

    def _gen_append(self, text, tag=None):
        """Добавить текст в вывод генератора."""
        def _do():
            self.gen_output.configure(state="normal")
            self.gen_output.insert("end", text + "\n", tag or ())
            self.gen_output.see("end")
            self.gen_output.configure(state="disabled")
        self.root.after(0, _do)

    def _gen_start(self):
        """Запуск автоматического поиска стратегий."""
        if not is_admin():
            messagebox.showwarning("Внимание", "Нужны права администратора!")
            return

        # Останавливаем winws2 если запущен
        if self.backend.is_running:
            self.backend.stop()
            self._upd_ui()
            time.sleep(1)

        # Сброс
        self._gen_stopping = False
        self._gen_working_results = []
        self.gen_output.configure(state="normal")
        self.gen_output.delete("1.0", "end")
        self.gen_output.configure(state="disabled")
        self.gen_progress_var.set(0)
        self.gen_progress_label.configure(text="")
        self.gen_found_label.configure(text="")
        self.gen_start_btn.configure(state="disabled", bg="#444466")

        # Очистка кнопок результатов
        for w in self.gen_results_frame.winfo_children():
            w.destroy()

        domain = self.gen_domain_var.get().strip()
        if not domain:
            messagebox.showinfo("Инфо", "Укажите домен для тестирования")
            self.gen_start_btn.configure(state="normal", bg=T.OK)
            return

        timeout = int(self.gen_timeout_var.get() or "5")
        max_working = int(self.gen_maxwork_var.get() or "5")
        include_risky = self.gen_risky_var.get()
        include_slow = self.gen_slow_var.get()

        # Собираем выбранные категории
        selected_cats = [cat for cat, var in self.gen_cat_vars.items() if var.get()]

        # Считаем сколько стратегий будет
        gen = StrategyGenerator()
        all_cands = gen.generate_all(include_risky=include_risky, include_slow=include_slow)
        if selected_cats:
            all_cands = [c for c in all_cands if c.category in selected_cats]

        self._gen_append(f">>> Домен: {domain}", "info")
        self._gen_append(f">>> Стратегий для теста: {len(all_cands)}", "info")
        self._gen_append(f">>> Таймаут: {timeout}с, макс. рабочих: {max_working}", "info")
        if selected_cats:
            self._gen_append(f">>> Категории: {', '.join(selected_cats)}", "dim")
        self._gen_append(f">>> Risky: {'да' if include_risky else 'нет'}, "
                          f"WSSize: {'да' if include_slow else 'нет'}", "dim")
        self._gen_append("")
        self.gen_status.configure(text="Тестирование...", fg=T.WARN)

        # Запуск в фоне
        threading.Thread(
            target=self._gen_worker,
            args=(domain, timeout, max_working, include_risky, include_slow,
                  selected_cats if selected_cats else None),
            daemon=True,
        ).start()

    def _gen_worker(self, domain, timeout, max_working, include_risky, include_slow, categories):
        """Фоновый воркер генератора."""
        try:
            def progress_cb(i, total, candidate, result):
                pct = int((i + 1) * 100 / total)
                self.root.after(0, lambda: self.gen_progress_var.set(pct))
                self.root.after(0, lambda: self.gen_progress_label.configure(
                    text=f"[{i+1}/{total}] {candidate.name}"))

                if result.ok:
                    self._gen_working_results.append((candidate, result))
                    n = len(self._gen_working_results)
                    self._gen_append(
                        f"  ✅ [{i+1}/{total}] {candidate.name} — "
                        f"{result.time_ms}ms (HTTP {result.http_code})", "ok")
                    self.root.after(0, lambda n=n: self.gen_found_label.configure(
                        text=f"Найдено: {n}"))
                    # Добавляем кнопку для этой стратегии
                    self.root.after(0, lambda c=candidate, r=result:
                        self._gen_add_result_btn(c, r))
                elif result.time_ms >= 4000:
                    self._gen_append(
                        f"  🐌 [{i+1}/{total}] {candidate.name} — "
                        f"{result.time_ms}ms (слишком медленно)", "slow")
                else:
                    err_info = f" [{result.error}]" if result.error else ""
                    self._gen_append(
                        f"  ❌ [{i+1}/{total}] {candidate.name} — "
                        f"curl={result.curl_code}{err_info}", "fail")

            profile, all_results = run_auto_generator(
                domain=domain,
                settings=self.settings,
                targets=self.targets if hasattr(self, 'targets') else load_targets(),
                include_risky=include_risky,
                include_slow=include_slow,
                max_working=max_working,
                timeout=timeout,
                categories=categories,
                progress_cb=progress_cb,
                stop_flag=lambda: self._gen_stopping,
            )

            # Итоги
            n_tested = len(all_results)
            n_working = len(self._gen_working_results)

            self._gen_append("")
            self._gen_append(f"{'='*50}")
            self._gen_append(f">>> Протестировано: {n_tested}", "info")
            self._gen_append(f">>> Работают: {n_working}", "ok" if n_working else "fail")

            if profile:
                self._gen_append(f">>> Лучшая: {profile.name}", "ok")
                self._gen_append(f">>> {profile.desc}", "dim")
                # Активируем профиль
                self.root.after(0, lambda: self._gen_activate_profile(profile))
            else:
                self._gen_append(">>> Рабочие стратегии не найдены.", "fail")
                self._gen_append(">>> Попробуйте:", "dim")
                self._gen_append(">>>   • Увеличить таймаут", "dim")
                self._gen_append(">>>   • Включить рискованные/WSSize", "dim")
                self._gen_append(">>>   • Использовать другой домен", "dim")

            self.root.after(0, lambda: self.gen_status.configure(
                text=f"Готово: {n_working}/{n_tested} работают",
                fg=T.OK if n_working else T.ERR))

        except Exception as e:
            self.log.error(f"Generator error: {traceback.format_exc()}")
            self._gen_append(f">>> Ошибка: {e}", "fail")
            self.root.after(0, lambda: self.gen_status.configure(
                text=f"Ошибка", fg=T.ERR))
        finally:
            self.root.after(0, lambda: self.gen_start_btn.configure(
                state="normal", bg=T.OK))
            self.root.after(0, lambda: self.gen_progress_var.set(100))

    def _gen_stop(self):
        """Остановка генератора."""
        self._gen_stopping = True
        self._gen_append("\n>>> Остановка...", "slow")
        self.gen_status.configure(text="Остановлен", fg=T.WARN)
        # Убиваем winws2
        try:
            subprocess.run(["taskkill", "/F", "/IM", "winws2.exe"],
                           capture_output=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass

    def _gen_add_result_btn(self, candidate, result):
        """Добавляет кнопку для рабочей стратегии в панель результатов."""
        btn = tk.Button(
            self.gen_results_frame,
            text=f"📋 {candidate.name} ({result.time_ms}ms)",
            font=T.FS, bg=T.HOV, fg=T.FG, bd=0, padx=8, pady=3,
            cursor="hand2",
            command=lambda c=candidate: self._gen_use_candidate(c),
        )
        btn.pack(side="left", padx=(0, 4), pady=2)
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=T.ACC))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=T.HOV))

    def _gen_use_candidate(self, candidate):
        """Создаёт профиль из выбранного кандидата."""
        targets = self.targets if hasattr(self, 'targets') else load_targets()
        profile = candidate_to_profile(candidate, targets)
        if profile:
            self._gen_activate_profile(profile)

    def _gen_activate_profile(self, profile):
        """Активирует профиль из генератора."""
        self.profiles.append(profile)
        save_custom_profiles(self.profiles)
        self.active_idx = len(self.profiles) - 1
        self._refp()
        self.lprof.configure(text=profile.name)
        self._gen_append(f"\n>>> Профиль «{profile.name}» создан!", "ok")
        self._gen_append(">>> Перейдите на «Панель» → «Запустить»", "info")
        self._log_ui(f"Создан профиль: {profile.name}", "success")

    def _apply_flowseal_preset(self, preset):
        """Применяет готовый Flowseal пресет как новый профиль."""
        exact = build_flowseal_runtime_profile(preset["name"], preset["desc"])
        if exact:
            profile = Profile(
                name=preset["name"],
                desc=preset["desc"],
                args=list(exact["args"]),
                binary=exact["binary"],
            )
            batch_name = os.path.basename(exact["batch_path"])
            self._log_ui(
                f"Flowseal exact upstream: {batch_name} ({len(profile.args)} args)",
                "info",
            )
        else:
            profile = Profile(
                name=preset["name"],
                desc=preset["desc"],
                args=list(preset["args"]),
            )
            self._log_ui(
                "Flowseal snapshot не найден, использована встроенная адаптация.",
                "warning",
            )
        self.profiles.append(profile)
        save_custom_profiles(self.profiles)
        self.active_idx = len(self.profiles) - 1
        self._refp()
        self.lprof.configure(text=profile.name)
        self._log_ui(f"Применён пресет: {preset['name']}", "success")
        self.nb.select(0)  # Переключиться на панель
        messagebox.showinfo("Пресет применён",
            f"Профиль «{preset['name']}» создан и активирован.\n\n"
            f"{preset['desc']}\n\n"
            f"Нажмите «Запустить» на панели для активации.")

    # ── Telegram WebSocket Proxy ────────────────────────
    def _tab_telegram(self):
        t = tk.Frame(self.nb, bg=T.BG)
        self.nb.add(t, text="  📱 Telegram  ")

        # Заголовок
        top = tk.Frame(t, bg=T.BG)
        top.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(top, text="📱 Telegram WebSocket Proxy",
                 font=T.FL, bg=T.BG, fg=T.BR).pack(side="left")

        self.tg_status_label = tk.Label(top, text="", font=T.FB, bg=T.BG, fg=T.DIM)
        self.tg_status_label.pack(side="right", padx=(0, 8))

        # Основной контент
        content = tk.Frame(t, bg=T.BG)
        content.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # === Карточка описания ===
        desc_card = self._card(content)
        desc_card.pack(fill="x", pady=(0, 8))
        desc_inner = tk.Frame(desc_card, bg=T.CARD)
        desc_inner.pack(fill="x", padx=16, pady=12)

        if not HAS_TG_PROXY:
            tk.Label(desc_inner, text="⚠ Нужны дополнительные библиотеки",
                     font=T.FB, bg=T.CARD, fg=T.WARN).pack(anchor="w")
            if getattr(sys, "frozen", False):
                msg = (
                    "В этой сборке отсутствует встроенная библиотека cryptography.\n"
                    "Это ошибка упаковки релиза, а не проблема пользователя.\n"
                    "Скачайте полный Win10/11 билд приложения."
                )
            else:
                msg = (
                    "Установите: pip install cryptography\n"
                    "Затем перезапустите приложение."
                )
            tk.Label(desc_inner, text=msg,
                     font=T.F, bg=T.CARD, fg=T.DIM, justify="left").pack(anchor="w", pady=(4, 0))

            if not getattr(sys, "frozen", False):
                def _install_deps():
                    self._log_ui("Установка cryptography...", "info")
                    def do():
                        try:
                            import subprocess as sp
                            r = sp.run([sys.executable, "-m", "pip", "install", "cryptography"],
                                       capture_output=True, text=True, timeout=240)
                            if r.returncode == 0:
                                self.root.after(0, lambda: self._log_ui(
                                    "✓ Установлено! Перезапустите приложение.", "success"))
                                self.root.after(0, lambda: messagebox.showinfo(
                                    "Готово", "Библиотеки установлены.\n"
                                    "Перезапустите приложение для активации Telegram прокси."))
                            else:
                                stderr = (r.stderr or r.stdout or "").strip()
                                self.root.after(0, lambda: self._log_ui(
                                    f"✗ Ошибка: {stderr[:200]}", "error"))
                        except Exception as e:
                            self.root.after(0, lambda: self._log_ui(f"✗ {e}", "error"))
                    threading.Thread(target=do, daemon=True).start()

                self._abtn(desc_inner, "📦 Установить зависимости", T.ACC, _install_deps).pack(
                    anchor="w", pady=(8, 0))
            return

        # Описание
        tk.Label(desc_inner,
                 text="Ускоряет Telegram, направляя трафик через WebSocket (TLS)\n"
                      "к серверам kws*.web.telegram.org. Работает параллельно с zapret.",
                 font=T.F, bg=T.CARD, fg=T.DIM, justify="left").pack(anchor="w")

        tk.Label(desc_inner,
                 text="Telegram → SOCKS5 (127.0.0.1) → WS Proxy → WSS → Telegram DC",
                 font=("Consolas", 10), bg=T.CARD, fg=T.INFO).pack(anchor="w", pady=(6, 0))

        # === Управление ===
        ctrl_card = self._card(content)
        ctrl_card.pack(fill="x", pady=(0, 8))
        ctrl_inner = tk.Frame(ctrl_card, bg=T.CARD)
        ctrl_inner.pack(fill="x", padx=16, pady=12)

        # Кнопки
        btn_row = tk.Frame(ctrl_inner, bg=T.CARD)
        btn_row.pack(fill="x", pady=(0, 8))

        self.tg_toggle_btn = self._abtn(btn_row, "▶ Запустить WS Proxy", T.OK, self._tg_toggle)
        self.tg_toggle_btn.pack(side="left", padx=(0, 8))

        self.tg_link_btn = self._abtn(btn_row, "📲 Открыть в Telegram", T.ACC, self._tg_open_link)
        self.tg_link_btn.pack(side="left", padx=(0, 8))

        self._sbtn(btn_row, "📋 Копировать ссылку", self._tg_copy_link).pack(side="left")

        # Статус
        self.tg_status_text = tk.Label(ctrl_inner, text="● Не запущен",
                                        font=T.FB, bg=T.CARD, fg=T.ERR)
        self.tg_status_text.pack(anchor="w", pady=(4, 0))

        # Настройки порта
        port_row = tk.Frame(ctrl_inner, bg=T.CARD)
        port_row.pack(fill="x", pady=(8, 0))
        tk.Label(port_row, text="Порт:", font=T.FB, bg=T.CARD, fg=T.DIM).pack(side="left")
        self.tg_port_var = tk.StringVar(value=str(DEFAULT_PORT))
        port_entry = self._entry(port_row, self.tg_port_var)
        port_entry.configure(width=8)
        port_entry.pack(side="left", padx=(4, 12), ipady=3)

        tk.Label(port_row, text="(по умолчанию 1080)",
                 font=T.FS, bg=T.CARD, fg=T.DIM).pack(side="left")

        # === Инструкция ===
        help_card = self._card(content)
        help_card.pack(fill="x", pady=(0, 8))
        help_inner = tk.Frame(help_card, bg=T.CARD)
        help_inner.pack(fill="x", padx=16, pady=12)

        tk.Label(help_inner, text="Как подключить", font=T.FB, bg=T.CARD, fg=T.FG).pack(anchor="w")

        steps = [
            "1. Нажмите «Запустить WS Proxy» выше",
            "2. Нажмите «Открыть в Telegram» — Telegram предложит добавить прокси",
            "3. Подтвердите в Telegram — настройка сохранится навсегда",
            "",
            "Telegram запомнит прокси и будет использовать его при каждом запуске.",
            "При выключении прокси Telegram автоматически переключится на прямое соединение.",
            "",
            "⚡ WS Proxy работает ПАРАЛЛЕЛЬНО со стратегиями zapret.",
            "    Zapret обходит DPI для YouTube/Discord, WS Proxy ускоряет Telegram.",
        ]
        for step in steps:
            fg = T.OK if step.startswith("⚡") else (T.FG if step and step[0].isdigit() else T.DIM)
            tk.Label(help_inner, text=step, font=T.F, bg=T.CARD, fg=fg,
                     anchor="w", justify="left").pack(anchor="w", pady=1)

        # === Статистика ===
        stats_card = self._card(content)
        stats_card.pack(fill="both", expand=True)
        stats_inner = tk.Frame(stats_card, bg=T.CARD)
        stats_inner.pack(fill="both", expand=True, padx=16, pady=12)

        tk.Label(stats_inner, text="Статистика", font=T.FB, bg=T.CARD, fg=T.FG).pack(anchor="w")
        self.tg_stats_label = tk.Label(stats_inner, text="Прокси не запущен",
                                        font=T.FM, bg=T.CARD, fg=T.DIM,
                                        anchor="w", justify="left")
        self.tg_stats_label.pack(anchor="w", fill="x", pady=(4, 0))

        # Polling для обновления статуса
        self._tg_poll()

    def _tg_toggle(self):
        """Вкл/выкл Telegram WS прокси."""
        if is_tg_proxy_running():
            ok, msg = stop_tg_proxy()
            self._log_ui(f"TG Proxy: {msg}", "warning" if ok else "error")
        else:
            try:
                port = int(self.tg_port_var.get())
            except ValueError:
                port = DEFAULT_PORT
            ok, msg = start_tg_proxy(port)
            self._log_ui(f"TG Proxy: {msg}", "success" if ok else "error")
            if not ok:
                messagebox.showerror("Ошибка", msg)
        self._tg_update_ui()

    def _tg_open_link(self):
        """Открывает tg://socks ссылку в Telegram."""
        try:
            port = int(self.tg_port_var.get())
        except ValueError:
            port = DEFAULT_PORT
        link = get_tg_proxy_link(port)
        self._log_ui(f"Открываю Telegram: {link}", "info")
        try:
            os.startfile(link)
        except Exception as e:
            # Fallback: копировать в буфер
            self.root.clipboard_clear()
            self.root.clipboard_append(link)
            messagebox.showinfo("Ссылка скопирована",
                f"Не удалось открыть Telegram автоматически.\n\n"
                f"Ссылка скопирована в буфер обмена:\n{link}\n\n"
                f"Вставьте её в браузер или Telegram.")

    def _tg_copy_link(self):
        """Копирует ссылку прокси в буфер обмена."""
        try:
            port = int(self.tg_port_var.get())
        except ValueError:
            port = DEFAULT_PORT
        link = get_tg_proxy_link(port)
        self.root.clipboard_clear()
        self.root.clipboard_append(link)
        self._log_ui(f"Скопировано: {link}", "success")

    def _tg_update_ui(self):
        """Обновляет UI состояния TG прокси."""
        if not hasattr(self, 'tg_toggle_btn'):
            return
        running = is_tg_proxy_running()
        self.tg_toggle_btn.configure(
            text="■ Остановить WS Proxy" if running else "▶ Запустить WS Proxy",
            bg=T.ERR if running else T.OK)
        self.tg_status_text.configure(
            text=f"● Запущен (127.0.0.1:{self.tg_port_var.get()})" if running else "● Не запущен",
            fg=T.OK if running else T.ERR)
        self.tg_status_label.configure(
            text="📱 TG Proxy: ON" if running else "",
            fg=T.OK if running else T.DIM)
        self.tg_stats_label.configure(text=get_tg_proxy_stats())
        self._update_tray_tooltip()

    def _tg_poll(self):
        """Периодическое обновление статуса TG прокси."""
        if hasattr(self, 'tg_toggle_btn'):
            self._tg_update_ui()
        self.root.after(5000, self._tg_poll)

    # ── Blockcheck + Домены ─────────────────────────────
    def _tab_blockcheck(self):
        self.targets = load_targets()
        self.bc_process = None
        self.bc_full_output = ""
        self.bc_found_strategies = []  # Собранные AVAILABLE стратегии

        t = tk.Frame(self.nb, bg=T.BG); self.nb.add(t, text="  Blockcheck  ")

        # === Верхняя строка: кнопки ===
        top = tk.Frame(t, bg=T.BG)
        top.pack(fill="x", padx=12, pady=(8, 4))
        self.bc_start_btn = self._abtn(top, "▶ Запустить", T.OK, self._run_bc)
        self.bc_start_btn.pack(side="left", padx=(0, 4))
        self._abtn(top, "■ Стоп + собрать", T.ERR, self._stop_bc_and_collect).pack(side="left", padx=(0, 4))
        self._abtn(top, "⚡ Без теста", T.ACC, self._gen_fallback_profile).pack(side="left")
        self.bc_timer_label = tk.Label(top, text="", font=T.FB, bg=T.BG, fg=T.WARN)
        self.bc_timer_label.pack(side="right")
        self.bc_found_label = tk.Label(top, text="", font=T.FB, bg=T.BG, fg=T.OK)
        self.bc_found_label.pack(side="right", padx=(0, 12))
        self.bc_status = tk.Label(top, text="Готов", font=T.FB, bg=T.BG, fg=T.DIM)
        self.bc_status.pack(side="right", padx=(0, 12))

        # === Основной контент: лево + право ===
        content = tk.Frame(t, bg=T.BG)
        content.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        left = tk.Frame(content, bg=T.BG)
        left.pack(side="left", fill="both", padx=(0, 6))

        # --- Домены ---
        dc = self._card(left)
        dc.pack(fill="both", expand=True, pady=(0, 6))
        dc_top = tk.Frame(dc, bg=T.CARD)
        dc_top.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(dc_top, text="Домены", font=T.FB, bg=T.CARD, fg=T.FG).pack(side="left")
        self._sbtn(dc_top, "Сброс", self._reset_targets).pack(side="right")

        self.domain_tree = ttk.Treeview(dc, show="tree", selectmode="browse")
        self.domain_tree.pack(fill="both", expand=True, padx=4, pady=(0, 2))
        self._fill_domain_tree()

        add_frame = tk.Frame(dc, bg=T.CARD)
        add_frame.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(add_frame, text="Кат:", font=T.FS, bg=T.CARD, fg=T.DIM).pack(side="left")
        self.new_cat = tk.StringVar()
        e1 = self._entry(add_frame, self.new_cat); e1.configure(width=8)
        e1.pack(side="left", padx=(2, 4), ipady=2)
        tk.Label(add_frame, text="Домен:", font=T.FS, bg=T.CARD, fg=T.DIM).pack(side="left")
        self.new_domain = tk.StringVar()
        e2 = self._entry(add_frame, self.new_domain); e2.configure(width=16)
        e2.pack(side="left", padx=(2, 4), ipady=2)
        self._sbtn(add_frame, "+", self._add_domain).pack(side="left", padx=(0, 2))
        self._sbtn(add_frame, "-", self._del_domain).pack(side="left")

        # --- Параметры blockcheck ---
        pc = self._card(left)
        pc.pack(fill="x", pady=(0, 6))
        tk.Label(pc, text="Параметры blockcheck2", font=T.FB, bg=T.CARD, fg=T.FG).pack(anchor="w", padx=8, pady=(6, 4))

        pf = tk.Frame(pc, bg=T.CARD)
        pf.pack(fill="x", padx=8, pady=(0, 6))

        # Домен для теста
        tk.Label(pf, text="Тест домен:", font=T.FS, bg=T.CARD, fg=T.DIM).grid(row=0, column=0, sticky="w", pady=2)
        self.bc_domain_var = tk.StringVar(value="все")
        domain_choices = ["все"] + get_all_domains(self.targets)
        self.bc_domain_menu = ttk.Combobox(pf, textvariable=self.bc_domain_var,
                                             values=domain_choices, width=22, state="readonly")
        self.bc_domain_menu.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=2)

        # Таймер
        tk.Label(pf, text="Таймер (мин):", font=T.FS, bg=T.CARD, fg=T.DIM).grid(row=1, column=0, sticky="w", pady=2)
        self.bc_timer_var = tk.StringVar(value="10")
        timer_frame = tk.Frame(pf, bg=T.CARD)
        timer_frame.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)
        for val in ["5", "10", "20", "30", "60", "0"]:
            label = val if val != "0" else "∞"
            tk.Radiobutton(timer_frame, text=label, variable=self.bc_timer_var, value=val,
                            bg=T.CARD, fg=T.FG, selectcolor=T.INP, activebackground=T.CARD,
                            activeforeground=T.FG, font=T.FS).pack(side="left")

        # Уровень сканирования
        tk.Label(pf, text="Уровень:", font=T.FS, bg=T.CARD, fg=T.DIM).grid(row=2, column=0, sticky="w", pady=2)
        self.bc_level_var = tk.StringVar(value="quick")
        level_frame = tk.Frame(pf, bg=T.CARD)
        level_frame.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=2)
        for val, label in [("quick", "Quick"), ("standard", "Standard"), ("force", "Force")]:
            tk.Radiobutton(level_frame, text=label, variable=self.bc_level_var, value=val,
                            bg=T.CARD, fg=T.FG, selectcolor=T.INP, activebackground=T.CARD,
                            activeforeground=T.FG, font=T.FS).pack(side="left")

        # Протоколы
        tk.Label(pf, text="Протоколы:", font=T.FS, bg=T.CARD, fg=T.DIM).grid(row=3, column=0, sticky="w", pady=2)
        proto_frame = tk.Frame(pf, bg=T.CARD)
        proto_frame.grid(row=3, column=1, sticky="ew", padx=(4, 0), pady=2)
        self.bc_tls12 = tk.BooleanVar(value=True)
        self.bc_tls13 = tk.BooleanVar(value=True)
        self.bc_http = tk.BooleanVar(value=False)
        self.bc_quic = tk.BooleanVar(value=False)
        for var, label in [(self.bc_tls12, "TLS1.2"), (self.bc_tls13, "TLS1.3"),
                            (self.bc_http, "HTTP"), (self.bc_quic, "QUIC")]:
            tk.Checkbutton(proto_frame, text=label, variable=var, bg=T.CARD, fg=T.FG,
                            selectcolor=T.INP, activebackground=T.CARD, font=T.FS).pack(side="left")

        pf.columnconfigure(1, weight=1)

        # === ПРАВАЯ ЧАСТЬ: вывод ===
        right = tk.Frame(content, bg=T.BG)
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        rc = self._card(right)
        rc.pack(fill="both", expand=True)

        self.bc_output = tk.Text(rc, bg=T.INP, fg=T.FG, font=T.FM, bd=0,
                                  insertbackground=T.FG, highlightthickness=0,
                                  state="disabled", wrap="word")
        sb = ttk.Scrollbar(rc, orient="vertical", command=self.bc_output.yview)
        self.bc_output.configure(yscrollcommand=sb.set)
        self.bc_output.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        sb.pack(side="right", fill="y", pady=4, padx=(0, 4))

    # ── Domain management ──────────────────────────────
    def _fill_domain_tree(self):
        self.domain_tree.delete(*self.domain_tree.get_children())
        for cat, domains in self.targets.items():
            cid = self.domain_tree.insert("", "end", text=f"{cat} ({len(domains)})", open=True)
            for d in domains:
                self.domain_tree.insert(cid, "end", text=f"  {d}")
    def _add_domain(self):
        cat = self.new_cat.get().strip() or "Другое"
        domain = self.new_domain.get().strip().lower()
        if not domain: return
        if cat not in self.targets: self.targets[cat] = []
        if domain not in self.targets[cat]:
            self.targets[cat].append(domain)
        save_targets(self.targets); self._fill_domain_tree()
        self.new_domain.set("")
        # Обновляем комбобокс
        self.bc_domain_menu["values"] = ["все"] + get_all_domains(self.targets)
    def _del_domain(self):
        sel = self.domain_tree.selection()
        if not sel: return
        text = self.domain_tree.item(sel[0])["text"].strip()
        parent = self.domain_tree.parent(sel[0])
        if parent:
            cat_text = self.domain_tree.item(parent)["text"]
            for cat, doms in self.targets.items():
                if cat in cat_text and text in doms:
                    doms.remove(text)
                    if not doms: del self.targets[cat]
                    break
        else:
            for cat in list(self.targets.keys()):
                if cat in text: del self.targets[cat]; break
        save_targets(self.targets); self._fill_domain_tree()
    def _reset_targets(self):
        if messagebox.askyesno("Сброс", "Сбросить домены?"):
            self.targets = dict(DEFAULT_TARGETS)
            save_targets(self.targets); self._fill_domain_tree()
            self.bc_domain_menu["values"] = ["все"] + get_all_domains(self.targets)

    def _gen_fallback_profile(self):
        profile = generate_default_profile(self.targets)
        self.profiles.append(profile)
        save_custom_profiles(self.profiles)
        self.active_idx = len(self.profiles) - 1
        self._refp(); self.lprof.configure(text=profile.name)
        self._log_ui(f"Профиль создан (стандартные стратегии)", "success")
        self.nb.select(1)

    # ── Blockcheck runner ──────────────────────────────
    def _bc_append(self, text):
        self.bc_output.configure(state="normal")
        self.bc_output.insert("end", text + "\n")
        self.bc_output.see("end")
        self.bc_output.configure(state="disabled")

    def _run_bc(self):
        """Запуск blockcheck2 — последовательно по доменам если 'все' + таймер."""
        if not is_admin():
            messagebox.showwarning("Внимание", "Нужны права администратора!")
            return

        domain_sel = self.bc_domain_var.get()
        if domain_sel == "все":
            self._bc_domain_queue = get_all_domains(self.targets)
        else:
            self._bc_domain_queue = [domain_sel]

        if not self._bc_domain_queue:
            messagebox.showinfo("Инфо", "Добавьте хотя бы один домен")
            return

        timer_min = int(self.bc_timer_var.get() or "0")
        self._bc_level = self.bc_level_var.get()
        self._bc_extra_env = {
            "ENABLE_HTTPS_TLS12": "1" if self.bc_tls12.get() else "0",
            "ENABLE_HTTPS_TLS13": "1" if self.bc_tls13.get() else "0",
            "ENABLE_HTTP": "1" if self.bc_http.get() else "0",
            "ENABLE_HTTP3": "1" if self.bc_quic.get() else "0",
        }
        self._bc_timer_per_domain = timer_min * 60 if timer_min > 0 else 0
        self._bc_stopping = False

        # Останавливаем winws2
        if self.backend.is_running:
            self.backend.stop(); self._upd_ui(); time.sleep(1)

        # Сброс
        self.bc_full_output = ""
        self.bc_found_strategies = []
        self._bc_domain_results = {}  # {domain: [strategy_lines]}
        self._bc_current_domain = None
        self._bc_current_strategies = []
        self.bc_output.configure(state="normal")
        self.bc_output.delete("1.0", "end")
        self.bc_output.configure(state="disabled")
        self.bc_start_btn.configure(state="disabled", bg="#444466")
        self.bc_found_label.configure(text="")
        self.bc_timer_label.configure(text="")

        total = len(self._bc_domain_queue)
        mode = "по одному" if total > 1 and self._bc_timer_per_domain > 0 else "все сразу"
        self._bc_append(f">>> Доменов: {total}, режим: {mode}")
        self._bc_append(f">>> Уровень: {self._bc_level}, таймер/домен: {timer_min} мин")
        self._bc_append(f">>> Протоколы: TLS1.2={self._bc_extra_env['ENABLE_HTTPS_TLS12']}, "
                         f"TLS1.3={self._bc_extra_env['ENABLE_HTTPS_TLS13']}")
        self._bc_append("")

        if total > 1 and self._bc_timer_per_domain > 0:
            # Последовательный прогон — по одному домену
            threading.Thread(target=self._bc_sequential_worker, daemon=True).start()
        else:
            # Один домен или все сразу без таймера
            threading.Thread(target=self._bc_single_worker,
                             args=(self._bc_domain_queue,), daemon=True).start()

    def _bc_single_worker(self, domains):
        """Запускает blockcheck для списка доменов (один запуск)."""
        domain_key = domains[0] if len(domains) == 1 else "все"
        self._bc_current_domain = domain_key
        self._bc_current_strategies = []

        try:
            self.bc_process = run_blockcheck(
                domains=domains, mode=self._bc_level, extra_env=self._bc_extra_env)
            self._bc_pid = self.bc_process.pid
            self.root.after(0, lambda: self.bc_status.configure(
                text=f"[{domain_key}] PID {self._bc_pid}", fg=T.INFO))

            self._bc_start_time = time.time()
            self._bc_timer_limit = self._bc_timer_per_domain
            if self._bc_timer_limit > 0:
                self.root.after(1000, self._bc_tick)

            self._bc_prev_line = ""
            self._bc_read_output()

            if not self._bc_stopping:
                ec = self.bc_process.wait() if self.bc_process else -1
                self.bc_process = None
                # Сохраняем стратегии для этого домена
                self._bc_domain_results[domain_key] = list(self._bc_current_strategies)
                self.root.after(0, lambda: self._bc_all_done())

        except Exception as e:
            if not self._bc_stopping:
                self.root.after(0, lambda: self.bc_status.configure(
                    text=f"Ошибка: {e}", fg=T.ERR))
                self.root.after(0, lambda: self.bc_start_btn.configure(
                    state="normal", bg=T.OK))
            self.log.error(f"bc_single error: {traceback.format_exc()}")

    def _bc_sequential_worker(self):
        """Последовательно тестирует каждый домен с таймером на каждый."""
        queue = list(self._bc_domain_queue)
        total = len(queue)

        for i, domain in enumerate(queue):
            if self._bc_stopping:
                break

            self._bc_current_domain = domain
            self._bc_current_strategies = []
            self.root.after(0, lambda d=domain, i=i: self._bc_append(
                f"\n{'='*50}\n>>> [{i+1}/{total}] Тестируем: {d}\n{'='*50}"))
            self.root.after(0, lambda d=domain, i=i: self.bc_status.configure(
                text=f"[{i+1}/{total}] {d}", fg=T.INFO))

            try:
                self.bc_process = run_blockcheck(
                    domains=[domain], mode=self._bc_level, extra_env=self._bc_extra_env)
                self._bc_pid = self.bc_process.pid

                self._bc_start_time = time.time()
                self._bc_timer_limit = self._bc_timer_per_domain
                self._bc_timer_expired = False
                if self._bc_timer_limit > 0:
                    self.root.after(1000, self._bc_tick)

                self._bc_prev_line = ""
                self._bc_read_output()

                # Дождёмся завершения или таймера
                if self.bc_process:
                    try:
                        self.bc_process.wait(timeout=2)
                    except: pass

                # Сохраняем стратегии
                n = len(self._bc_current_strategies)
                self._bc_domain_results[domain] = list(self._bc_current_strategies)
                self.root.after(0, lambda d=domain, n=n: self._bc_append(
                    f">>> {d}: найдено {n} стратегий"))

                self.bc_process = None
                time.sleep(1)  # Пауза между доменами

            except Exception as e:
                self.log.error(f"bc_seq error for {domain}: {e}")
                self.root.after(0, lambda d=domain, e=e: self._bc_append(
                    f">>> Ошибка для {d}: {e}"))

        # Все домены пройдены
        if not self._bc_stopping:
            self.root.after(0, self._bc_all_done)

    def _bc_read_output(self):
        """Читает stdout из bc_process, собирает AVAILABLE стратегии."""
        while not self._bc_stopping:
            try:
                line = self.bc_process.stdout.readline()
            except (ValueError, OSError):
                break
            if not line:
                break
            line = line.rstrip("\n\r")
            self.bc_full_output += line + "\n"

            if "AVAILABLE !!!!!" in line and self._bc_prev_line:
                strat = self._bc_prev_line.strip()
                if "winws2" in strat:
                    self._bc_current_strategies.append(strat)
                    if strat not in self.bc_found_strategies:
                        self.bc_found_strategies.append(strat)
                    n = len(self.bc_found_strategies)
                    self.root.after(0, lambda n=n: self.bc_found_label.configure(
                        text=f"Найдено: {n}"))

            self._bc_prev_line = line
            self.root.after(0, lambda l=line: self._bc_append(l))

    def _bc_tick(self):
        if self._bc_stopping or not self.bc_process or self.bc_process.poll() is not None:
            return
        elapsed = time.time() - self._bc_start_time
        remaining = self._bc_timer_limit - elapsed
        if remaining <= 0:
            self._bc_append(f"\n>>> Таймер: {self._bc_current_domain} — время вышло")
            self._bc_kill_current()
            return
        mins = int(remaining) // 60
        secs = int(remaining) % 60
        self.bc_timer_label.configure(text=f"{mins}:{secs:02d}")
        self.root.after(1000, self._bc_tick)

    def _bc_kill_current(self):
        """Убивает текущий blockcheck процесс (но НЕ завершает весь прогон)."""
        proc = self.bc_process
        if proc and hasattr(proc, '_job_object') and proc._job_object:
            try:
                terminate_job(proc._job_object)
                proc._job_object = None
            except: pass
        for name in ["winws2.exe", "winws.exe", "curl.exe"]:
            try:
                subprocess.run(["taskkill", "/F", "/IM", name],
                               capture_output=True, timeout=3,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except: pass
        if proc:
            try: proc.stdout.close()
            except: pass
            try: proc.kill()
            except: pass
        self.bc_timer_label.configure(text="")

    def _stop_bc_and_collect(self):
        """Полная остановка + сбор результатов."""
        self._bc_stopping = True
        self._bc_append("\n>>> Полная остановка...")
        self.log.info(f"Full stop. Found {len(self.bc_found_strategies)} total strategies.")
        self._bc_kill_current()
        self.bc_process = None
        # Сохраняем текущие
        if self._bc_current_domain and self._bc_current_strategies:
            self._bc_domain_results[self._bc_current_domain] = list(self._bc_current_strategies)
        time.sleep(0.5)
        self._bc_all_done()

    def _bc_all_done(self):
        """Все домены пройдены — строим комбо-профиль."""
        self.bc_timer_label.configure(text="")
        self.bc_start_btn.configure(state="normal", bg=T.OK)

        total_strats = len(self.bc_found_strategies)
        domains_with = {d: s for d, s in self._bc_domain_results.items() if s}

        self._bc_append(f"\n{'='*50}")
        self._bc_append(f">>> ИТОГ: стратегий {total_strats}, доменов с результатом: {len(domains_with)}")

        if not domains_with and total_strats == 0:
            results = parse_blockcheck_output(self.bc_full_output)
            if results:
                self._bc_append(f">>> Найдено в SUMMARY: {len(results)}")
                profile = generate_profile_from_results(results, self.targets)
                if profile:
                    self._activate_bc_profile(profile)
                    return
            self._bc_append(">>> Стратегии не найдены.")
            self.bc_status.configure(text="Нет стратегий", fg=T.ERR)
            return

        # Показываем результаты Phase 1
        for domain, strats in domains_with.items():
            self._bc_append(f"\n  {domain}: {len(strats)} кандидатов")

        self._bc_append(f"\n{'='*50}")
        self._bc_append(f">>> ФАЗА 2: Верификация curl-ом (таймаут 3 сек, порог <3000ms)")
        self._bc_append(f">>> Тестируем ВСЕ уникальные стратегии на каждый домен...\n")
        self.bc_status.configure(text="Фаза 2: верификация", fg=T.WARN)

        # Запускаем верификацию в фоне
        self._bc_domains_with = domains_with
        threading.Thread(target=self._bc_verify_phase, daemon=True).start()

    def _bc_verify_phase(self):
        """Фаза 2 — проверяем стратегии реальным curl, выбираем лучшие."""
        verified = {}  # {domain: best_strategy_str}
        domains_with = self._bc_domains_with
        total_domains = len(domains_with)

        for di, (domain, strats) in enumerate(domains_with.items()):
            if self._bc_stopping:
                break

            self.root.after(0, lambda d=domain, di=di: (
                self._bc_append(f"  [{di+1}/{total_domains}] Проверяем {d}..."),
                self.bc_status.configure(text=f"Верификация {di+1}/{total_domains}: {d}", fg=T.WARN)
            ))

            def on_progress(i, total, dom, strat, result):
                if result["ok"]:
                    mark = "✅"
                elif result["time_ms"] >= 3000:
                    mark = "🐌"  # слишком медленно
                else:
                    mark = "❌"
                ms = result["time_ms"]
                idx = strat.find("--lua-desync")
                short = strat[idx:idx+50] if idx >= 0 else strat[-50:]
                self.root.after(0, lambda: self._bc_append(
                    f"    {mark} [{i+1}/{total}] {short}... {ms}ms"))

            results = verify_domain_strategies(
                domain=domain,
                strategies=strats,
                winws_bin=self.settings.get("winws_bin", ""),
                lua_dir=self.settings.get("lua_dir", ""),
                timeout=3,        # 3 сек curl таймаут
                max_ok_ms=3000,   # >3000ms = не рабочая
                progress_cb=on_progress,
                stop_flag=lambda: self._bc_stopping,
            )

            # Берём лучшую рабочую по скорости
            working = [(s, r) for s, r in results if r["ok"]]
            if working:
                working.sort(key=lambda x: x[1]["time_ms"])
                best_strat, best_result = working[0]
                verified[domain] = best_strat
                n_tested = len(results)
                n_ok = len(working)
                self.root.after(0, lambda d=domain, ms=best_result["time_ms"], n=n_ok, t=n_tested:
                    self._bc_append(f"    ✅ {d}: {n}/{t} работают, лучшая {ms}ms"))
            else:
                self.root.after(0, lambda d=domain: self._bc_append(
                    f"    ❌ {d}: ни одна стратегия не прошла curl"))

        # Итоги верификации
        n_ok = len(verified)
        n_fail = total_domains - n_ok

        self.root.after(0, lambda: self._bc_append(
            f"\n{'='*50}\n>>> Верификация: {n_ok} доменов работают, {n_fail} нет"))

        if not verified:
            self.root.after(0, lambda: self._bc_append(
                ">>> Ни одна стратегия не прошла верификацию."))
            self.root.after(0, lambda: self._bc_append(
                ">>> Попробуйте увеличить таймер или другой уровень сканирования."))
            self.root.after(0, lambda: self.bc_status.configure(
                text="Верификация: 0 рабочих", fg=T.ERR))
            self.root.after(0, lambda: self.bc_start_btn.configure(
                state="normal", bg=T.OK))
            return

        # Сохраняем верифицированные стратегии
        ds = load_domain_strategies()
        for domain, strat in verified.items():
            ds[domain] = strat
        save_domain_strategies(ds)

        # Строим комбо-профиль только из ВЕРИФИЦИРОВАННЫХ стратегий
        per_domain = {}
        for domain, strat in verified.items():
            idx = strat.find("winws2")
            if idx >= 0:
                params = strat[idx + 6:].strip()
                clean = " ".join(
                    ("--" + p.strip() if not p.strip().startswith("--") else p.strip())
                    for p in params.split(" --")
                    if p.strip() and not p.strip().startswith("wf-")
                )
                per_domain[domain] = clean

        if per_domain:
            profile = build_combo_profile(
                per_domain, self.targets,
                name=f"Верифицировано ({n_ok} доменов)"
            )
            self.root.after(0, lambda: self._activate_bc_profile(profile))
        else:
            self.root.after(0, lambda: self.bc_start_btn.configure(
                state="normal", bg=T.OK))

    def _activate_bc_profile(self, profile):
        self.profiles.append(profile)
        save_custom_profiles(self.profiles)
        self.active_idx = len(self.profiles) - 1
        self._refp(); self.lprof.configure(text=profile.name)
        self._bc_append(f"\n>>> Профиль «{profile.name}» создан!")
        self._bc_append(">>> Перейдите на «Панель» → «Запустить»")
        self.bc_status.configure(text="Профиль создан", fg=T.OK)
        self._log_ui(f"Профиль: {profile.name}", "success")

    def _profile_from_all_collected(self):
        """Фолбэк — профиль из всех собранных стратегий (без per-domain)."""
        if not self.bc_found_strategies:
            return None
        return build_profile_from_raw_strategy(
            self.bc_found_strategies[0],
            self.targets,
            name=f"Blockcheck ({len(self.bc_found_strategies)})",
        )

    # ── Списки ─────────────────────────────────────────
    def _tab_lists(self):
        t = tk.Frame(self.nb, bg=T.BG); self.nb.add(t, text="  Списки  ")
        tp = tk.Frame(t, bg=T.BG); tp.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(tp, text="Блок-листы", font=T.FL, bg=T.BG, fg=T.BR).pack(side="left")
        self._abtn(tp, "Синхронизировать upstream", T.OK, self._update_bundle).pack(side="right")
        fc = self._card(t); fc.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        cols = ("file", "size", "lines", "mod")
        self.ltree = ttk.Treeview(fc, columns=cols, show="headings", selectmode="browse")
        for c, h, w in [("file", "Файл", 300), ("size", "Размер", 100),
                         ("lines", "Строк", 80), ("mod", "Изменён", 180)]:
            self.ltree.heading(c, text=h); self.ltree.column(c, width=w)
        self.ltree.pack(fill="both", expand=True, padx=2, pady=2)
        br = tk.Frame(t, bg=T.BG); br.pack(fill="x", padx=12, pady=(0, 12))
        self._sbtn(br, "Добавить свой", self._addlist).pack(side="left", padx=(0, 6))
        self._sbtn(br, "Обновить таблицу", self._scanl).pack(side="left")
        self._scanl()

    # ── Логи ───────────────────────────────────────────
    def _tab_logs(self):
        t = tk.Frame(self.nb, bg=T.BG); self.nb.add(t, text="  Логи  ")
        tp = tk.Frame(t, bg=T.BG); tp.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(tp, text="Журнал", font=T.FL, bg=T.BG, fg=T.BR).pack(side="left")
        self._sbtn(tp, "Очистить", self._clrlog).pack(side="right", padx=(6, 0))
        self._sbtn(tp, "Открыть лог-файл", self._open_logfile).pack(side="right")
        lc = self._card(t); lc.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log_t = tk.Text(lc, bg=T.INP, fg=T.FG, font=T.FM, bd=0, insertbackground=T.FG,
                              highlightthickness=0, state="disabled", wrap="word")
        sb = ttk.Scrollbar(lc, orient="vertical", command=self.log_t.yview)
        self.log_t.configure(yscrollcommand=sb.set)
        self.log_t.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        sb.pack(side="right", fill="y", pady=4, padx=(0, 4))
        for tag, clr in [("info", T.INFO), ("success", T.OK), ("warning", T.WARN),
                          ("error", T.ERR), ("dim", T.DIM)]:
            self.log_t.tag_configure(tag, foreground=clr)
        self._log_ui(f"{APP_NAME} v{APP_VERSION}")
        self._log_ui(f"winws2: {self.settings.get('winws_bin', '?')}", "dim")
        self._log_ui(f"Lua: {self.settings.get('lua_dir', '?')}", "dim")
        self._log_ui(f"Админ: {'Да' if is_admin() else 'НЕТ!'}", "success" if is_admin() else "warning")
        self._log_ui(f"Лог-файл: {os.path.join(LOG_DIR, 'manager_*.log')}", "dim")

    # ── Настройки ──────────────────────────────────────
    def _tab_set(self):
        t = tk.Frame(self.nb, bg=T.BG); self.nb.add(t, text="  Настройки  ")
        c = self._card(t); c.pack(fill="both", expand=True, padx=12, pady=12)
        inn = tk.Frame(c, bg=T.CARD); inn.pack(fill="both", expand=True, padx=20, pady=20)
        tk.Label(inn, text="Пути", font=T.FL, bg=T.CARD, fg=T.BR).pack(anchor="w", pady=(0, 12))
        self.svars = {}
        for k, lb in [("winws_bin", "Путь к winws2.exe:"), ("lua_dir", "Lua скрипты:"),
                       ("lists_dir", "Файлы / списки:"), ("winws_dir", "Рабочая директория:")]:
            tk.Label(inn, text=lb, font=T.FB, bg=T.CARD, fg=T.DIM).pack(anchor="w", pady=(6, 0))
            v = tk.StringVar(value=self.settings.get(k, "")); self.svars[k] = v
            r = tk.Frame(inn, bg=T.CARD); r.pack(fill="x", pady=(2, 4))
            self._entry(r, v).pack(side="left", fill="x", expand=True, ipady=5)
            tk.Button(r, text="…", font=T.FB, bg=T.HOV, fg=T.FG, bd=0, padx=10, pady=3,
                       cursor="hand2", command=lambda v=v: v.set(filedialog.askdirectory() or v.get())
                       ).pack(side="right", padx=(6, 0))

        tk.Label(inn, text="Автоматизация", font=T.FL, bg=T.CARD, fg=T.BR).pack(anchor="w", pady=(16, 8))
        self.autostart_var = tk.BooleanVar(value=self.settings.get("autostart_enabled", False))
        self.monthly_sync_var = tk.BooleanVar(value=self.settings.get("monthly_auto_sync", True))

        tk.Checkbutton(
            inn,
            text="Запускать приложение при входе в Windows (через Планировщик задач, с правами администратора)",
            variable=self.autostart_var,
            bg=T.CARD, fg=T.FG, selectcolor=T.INP, activebackground=T.CARD,
            activeforeground=T.FG, font=T.F,
            wraplength=760, justify="left",
        ).pack(anchor="w")
        self.autostart_state_lbl = tk.Label(
            inn, text="", font=T.FS, bg=T.CARD, fg=T.DIM, justify="left", wraplength=760
        )
        self.autostart_state_lbl.pack(anchor="w", pady=(2, 8))

        tk.Checkbutton(
            inn,
            text=f"Раз в {AUTO_SYNC_INTERVAL_DAYS} дней проверять апдейты upstream при запуске приложения",
            variable=self.monthly_sync_var,
            bg=T.CARD, fg=T.FG, selectcolor=T.INP, activebackground=T.CARD,
            activeforeground=T.FG, font=T.F,
            wraplength=760, justify="left",
        ).pack(anchor="w")
        self.auto_sync_state_lbl = tk.Label(
            inn, text="", font=T.FS, bg=T.CARD, fg=T.DIM, justify="left", wraplength=760
        )
        self.auto_sync_state_lbl.pack(anchor="w", pady=(2, 8))

        tk.Label(inn, text="Обслуживание", font=T.FL, bg=T.CARD, fg=T.BR).pack(anchor="w", pady=(16, 8))
        mr = tk.Frame(inn, bg=T.CARD); mr.pack(fill="x")
        self._abtn(mr, "Сохранить", T.OK, self._saveset).pack(side="left", padx=(0, 6))
        self._abtn(mr, "Синхронизировать upstream", T.WARN, self._update_bundle).pack(side="left", padx=(0, 6))
        self._abtn(mr, "Удалить WinDivert", T.ERR, self._del_wd).pack(side="left", padx=(0, 6))
        if not is_admin():
            self._abtn(mr, "Запросить админ", T.ACC, request_admin).pack(side="left")
        self._refresh_automation_state()

    def _refresh_automation_state(self):
        autostart_enabled = bool(self.settings.get("autostart_enabled", False))
        if hasattr(self, "autostart_state_lbl"):
            auto_text = (
                "Автозапуск включён: приложение будет открываться при входе в Windows."
                if autostart_enabled
                else "Автозапуск выключен."
            )
            self.autostart_state_lbl.configure(
                text=auto_text,
                fg=T.OK if autostart_enabled else T.DIM,
            )

        if hasattr(self, "auto_sync_state_lbl"):
            if self.settings.get("monthly_auto_sync", True):
                last_check = self.settings.get("last_auto_sync_check") or "— ещё не было"
                status = self.settings.get("last_auto_sync_status") or "Ожидает первую проверку."
                sync_text = f"Последняя проверка: {last_check}. {status}"
                color = T.INFO
            else:
                sync_text = "Автопроверка upstream выключена."
                color = T.DIM
            self.auto_sync_state_lbl.configure(text=sync_text, fg=color)

    def _maybe_run_monthly_auto_sync(self):
        try:
            if self._sync_in_progress:
                return
            if self.backend.is_running:
                self.log.info("Monthly auto-sync skipped: backend already running")
                return
            if not is_monthly_auto_sync_due(self.settings):
                self.log.info("Monthly auto-sync not due yet")
                return
            self._start_upstream_sync(manual=False)
        except Exception:
            self.log.error(f"Auto-sync scheduler error: {traceback.format_exc()}")

    def _start_upstream_sync(self, manual: bool = True):
        if self._sync_in_progress:
            if manual:
                self._log_ui("Синхронизация уже выполняется", "warning")
            return

        self._sync_in_progress = True
        if manual:
            self._log_ui("Синхронизация upstream-компонентов...", "info")
        else:
            self._log_ui(
                f"Плановая авто-проверка upstream: раз в {AUTO_SYNC_INTERVAL_DAYS} дней",
                "info",
            )
        threading.Thread(target=self._run_upstream_sync_worker, args=(manual,), daemon=True).start()

    def _run_upstream_sync_worker(self, manual: bool):
        checked_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        summary = ""
        try:
            runtime_active = (
                self.backend.is_running
                or is_tg_proxy_running()
                or bool(getattr(self, "bc_process", None))
            )
            if runtime_active:
                self.root.after(0, lambda: self._log_ui(
                    "Остановка DPI/blockcheck/TG Proxy перед обновлением upstream...", "warning"))
                stop_messages = self._stop_runtime_services(reason="upstream-sync")
                for stop_msg in stop_messages:
                    level = "error" if "error" in stop_msg.lower() else "success"
                    self.root.after(0, lambda m=stop_msg, lv=level: self._log_ui(m, lv))
                time.sleep(0.3)
                if self.backend.is_running or is_tg_proxy_running() or bool(getattr(self, "bc_process", None)):
                    raise RuntimeError("Не удалось безопасно остановить все процессы перед обновлением")

            results = sync_external_components()
            all_ok = True
            for result in results:
                ok = result.get("ok", False)
                all_ok = all_ok and ok
                component = result.get("component", "upstream")
                message = result.get("message", "")
                level = "success" if ok else "error"
                self.root.after(0, lambda c=component, m=message, lv=level:
                    self._log_ui(f"{'✓ ' if lv == 'success' else '✗ '}{c}: {m}", lv))

            if all_ok:
                self.settings["last_update"] = checked_at
                summary = "Проверка завершена без ошибок."
                self.root.after(0, lambda: self.lupd.configure(text=checked_at))
            else:
                summary = "Часть компонентов обновилась с ошибками, детали есть в журнале."

            self.root.after(0, self._scanl)
            self.root.after(0, self._upd_ui)
        except Exception as e:
            summary = f"Ошибка: {e}"
            self.root.after(0, lambda: self._log_ui(f"✗ Ошибка: {e}", "error"))
            self.log.error(traceback.format_exc())
        finally:
            mode = "Ручная проверка" if manual else "Автопроверка"
            self.settings["last_auto_sync_check"] = checked_at
            self.settings["last_auto_sync_status"] = f"{mode}: {summary}"
            save_settings(self.settings)
            self.root.after(0, self._refresh_automation_state)
            self._sync_in_progress = False

    # ── ДЕЙСТВИЯ ───────────────────────────────────────
    def _toggle(self):
        try:
            if self.backend.is_running:
                self._log_ui("Остановка winws2...", "warning")
                ok, m = self.backend.stop()
            else:
                if not is_admin():
                    messagebox.showwarning("Внимание",
                        "WinDivert требует прав администратора.\n"
                        "Перезапустите через START_ADMIN.bat")
                    self._log_ui("Нет прав администратора!", "error")
                    return
                p = self.profiles[self.active_idx]
                self._log_ui(f"Запуск: {p.name}")
                ok, m = self.backend.start(p)
            self._log_ui(f"{'✓ ' if ok else '✗ '}{m}", "success" if ok else "error")
        except Exception as e:
            self._log_ui(f"Ошибка: {e}", "error")
            self.log.error(traceback.format_exc())
        self._upd_ui()

    def _upd_ui(self):
        try:
            on = self.backend.is_running
            tg = is_tg_proxy_running()
            self.tbtn.configure(text="■  ОСТАНОВИТЬ" if on else "▶  ЗАПУСТИТЬ", bg=T.ERR if on else T.OK)
            # Составной статус: Zapret + TG Proxy
            parts = []
            if on:
                parts.append("● DPI: ON")
            if tg:
                parts.append("📱 TG: ON")
            if not parts:
                status_text = "● НЕАКТИВЕН"
                status_fg = T.ERR
            else:
                status_text = "  ".join(parts)
                status_fg = T.OK
            self.hstat.configure(text=status_text, fg=status_fg)
            self.sd.configure(text=f"Профиль: {self.profiles[self.active_idx].name}" if on else "Модификация отключена")
            self.ifill.configure(bg=T.OK if on else T.ERR)
            self.ibar.configure(bg=T.OKD if on else T.ERRD)
            self._update_tray_tooltip()
        except Exception:
            pass

    def _poll(self):
        self._upd_ui()
        self.root.after(3000, self._poll)

    def _update_bundle(self):
        self._start_upstream_sync(manual=True)

    def _open_folder(self):
        try:
            d = WINWS_DIR if os.path.isdir(WINWS_DIR) else os.path.dirname(WINWS_DIR)
            os.startfile(d)
        except Exception as e:
            self._log_ui(f"Не удалось открыть: {e}", "error")

    def _open_logfile(self):
        try:
            import glob
            logs = sorted(glob.glob(os.path.join(LOG_DIR, "manager_*.log")))
            if logs:
                os.startfile(logs[-1])
            else:
                os.startfile(LOG_DIR)
        except Exception as e:
            self._log_ui(f"Не удалось открыть лог: {e}", "error")

    # ── Профили ────────────────────────────────────────
    def _refp(self):
        self.plb.delete(0, "end")
        for i, p in enumerate(self.profiles):
            pfx = "● " if i == self.active_idx else "  "
            tag = " [встр.]" if p.builtin else ""
            self.plb.insert("end", f"{pfx}{p.name}{tag}")
        if self.profiles:
            self.plb.select_set(self.active_idx); self._showp(self.active_idx)
    def _onsel(self, _):
        s = self.plb.curselection()
        if s: self._showp(s[0])
    def _showp(self, i):
        p = self.profiles[i]
        self.cn.set(p.name); self.cd.set(p.desc)
        self.ca.delete("1.0", "end"); self.ca.insert("1.0", "\n".join(p.args))
    def _applp(self):
        s = self.plb.curselection()
        if not s: return
        self.active_idx = s[0]; p = self.profiles[s[0]]
        self.lprof.configure(text=p.name)
        self._log_ui(f"Активирован: {p.name}", "success"); self._refp()
        if self.backend.is_running:
            self._log_ui("Перезапуск...", "warning")
            self.backend.stop(); time.sleep(0.5); self.backend.start(p); self._upd_ui()
    def _savep(self):
        s = self.plb.curselection()
        if not s: return
        p = self.profiles[s[0]]
        if p.builtin: messagebox.showinfo("Инфо", "Встроенные нельзя изменять"); return
        p.name = self.cn.get(); p.desc = self.cd.get()
        p.args = [l.strip() for l in self.ca.get("1.0", "end").strip().split("\n") if l.strip()]
        save_custom_profiles(self.profiles); self._refp()
        self._log_ui(f"Сохранён: {p.name}", "success")
    def _addp(self):
        self.profiles.append(Profile("Новый профиль", "", [
            "--wf-tcp-out=80,443", "--lua-init=@zapret-lib.lua", "--lua-init=@zapret-antidpi.lua",
            "--filter-tcp=443 --filter-l7=tls", "--out-range=-d10", "--payload=tls_client_hello",
            "--lua-desync=fake:blob=fake_default_tls:tcp_md5:repeats=6",
            "--lua-desync=multidisorder:pos=midsld"]))
        save_custom_profiles(self.profiles); self._refp()
        self.plb.select_clear(0, "end"); self.plb.select_set(len(self.profiles) - 1)
        self._showp(len(self.profiles) - 1)
    def _delp(self):
        s = self.plb.curselection()
        if not s: return
        p = self.profiles[s[0]]
        if p.builtin: messagebox.showinfo("Инфо", "Встроенные нельзя удалить"); return
        if messagebox.askyesno("Удаление", f"Удалить «{p.name}»?"):
            self.profiles.pop(s[0])
            if self.active_idx >= len(self.profiles): self.active_idx = 0
            save_custom_profiles(self.profiles); self._refp()
    def _imp(self):
        path = filedialog.askopenfilename(filetypes=[
            ("JSON", "*.json"), ("CMD/BAT", "*.cmd *.bat"),
            ("Текст", "*.txt *.conf"), ("Все", "*.*")])
        if not path: return
        try:
            with open(path, encoding="utf-8", errors="ignore") as f: content = f.read()
            try:
                d = json.loads(content)
                p = Profile.from_dict(d) if isinstance(d, dict) else Profile(Path(path).stem, "", d)
            except json.JSONDecodeError:
                lines = []
                for line in content.split("\n"):
                    line = line.strip().rstrip("^").strip()
                    if not line or line.startswith(("@", "rem", "REM", "start ", "::")): continue
                    if line.startswith("--") or line.startswith('"--'):
                        lines.append(line.strip('"'))
                if not lines:
                    lines = [l.strip().rstrip("\\").strip() for l in content.strip().split("\n") if l.strip()]
                p = Profile(Path(path).stem, f"Из {Path(path).name}", lines)
            self.profiles.append(p); save_custom_profiles(self.profiles); self._refp()
            self._log_ui(f"Импортирован: {p.name}", "success")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    def _expp(self):
        s = self.plb.curselection()
        if not s: return
        p = self.profiles[s[0]]
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                             initialfile=f"{p.name.replace(' ', '_')}.json")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(p.to_dict(), f, indent=2, ensure_ascii=False)
            self._log_ui(f"Экспорт: {path}", "success")

    # ── Списки ─────────────────────────────────────────
    def _scanl(self):
        self.ltree.delete(*self.ltree.get_children())
        dirs = [self.settings.get("lists_dir", ""), CUSTOM_LISTS_DIR]
        exts = {".txt", ".lst", ".list", ".csv", ".conf", ".bin"}
        for d in dirs:
            if not d or not os.path.isdir(d): continue
            for fn in sorted(os.listdir(d)):
                fp = os.path.join(d, fn)
                if not os.path.isfile(fp): continue
                ext = Path(fn).suffix.lower()
                if ext and ext not in exts: continue
                st = os.stat(fp); sz = st.st_size
                ss = f"{sz/1e6:.1f} MB" if sz > 1e6 else (f"{sz/1e3:.1f} KB" if sz > 1e3 else f"{sz} B")
                try:
                    with open(fp, "r", errors="ignore") as f: lns = sum(1 for _ in f)
                except: lns = "?"
                self.ltree.insert("", "end", values=(
                    fn, ss, lns, datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")))
    def _addlist(self):
        p = filedialog.askopenfilename(filetypes=[("Текст", "*.txt *.lst"), ("Все", "*.*")])
        if p:
            shutil.copy2(p, os.path.join(CUSTOM_LISTS_DIR, os.path.basename(p)))
            self._log_ui(f"Добавлен: {os.path.basename(p)}", "success"); self._scanl()

    # ── Разное ─────────────────────────────────────────
    def _clrlog(self):
        self.log_t.configure(state="normal"); self.log_t.delete("1.0", "end"); self.log_t.configure(state="disabled")
    def _tab_dash(self):
        t = tk.Frame(self.nb, bg=T.BG)
        self.nb.add(t, text="  Панель  ")

        c = self._card(t)
        c.pack(fill="x", padx=12, pady=(12, 6))
        r = tk.Frame(c, bg=T.CARD)
        r.pack(fill="x", padx=20, pady=16)
        l = tk.Frame(r, bg=T.CARD)
        l.pack(side="left", fill="x", expand=True)
        tk.Label(l, text="Модификация трафика", font=T.FL, bg=T.CARD, fg=T.BR).pack(anchor="w")
        self.sd = tk.Label(l, text="Нажмите для запуска winws2", font=T.F, bg=T.CARD, fg=T.DIM)
        self.sd.pack(anchor="w", pady=(4, 0))

        self.tbtn = tk.Button(
            r,
            text="▶  ЗАПУСТИТЬ",
            font=T.FL,
            bg=T.OK,
            fg=T.BR,
            bd=0,
            padx=28,
            pady=10,
            cursor="hand2",
            activebackground=T.AH,
            command=self._toggle,
        )
        self.tbtn.pack(side="right", padx=(20, 0))

        self.ibar = tk.Frame(c, bg=T.ERRD, height=4)
        self.ibar.pack(fill="x", padx=20, pady=(0, 16))
        self.ifill = tk.Frame(self.ibar, bg=T.ERR, height=4)
        self.ifill.place(x=0, y=0, relwidth=1, relheight=1)

        ir = tk.Frame(t, bg=T.BG)
        ir.pack(fill="x", padx=12, pady=6)
        for col, lbl_t, attr, clr, val in [
            (0, "ПРОФИЛЬ", "lprof", T.INFO, self.profiles[0].name),
            (1, "ОБНОВЛЕНИЕ", "lupd", T.WARN, self.settings.get("last_update") or "— никогда"),
        ]:
            cc = self._card(ir)
            cc.pack(side="left", fill="both", expand=True, padx=(0 if col == 0 else 4, 4 if col == 0 else 0))
            tk.Label(cc, text=lbl_t, font=T.FS, bg=T.CARD, fg=T.DIM).pack(anchor="w", padx=16, pady=(12, 2))
            w = tk.Label(cc, text=val, font=T.FB, bg=T.CARD, fg=clr)
            w.pack(anchor="w", padx=16, pady=(0, 12))
            setattr(self, attr, w)

        c3 = self._card(ir)
        c3.pack(side="left", fill="both", expand=True, padx=(4, 0))
        tk.Label(c3, text="ДЕЙСТВИЯ", font=T.FS, bg=T.CARD, fg=T.DIM).pack(anchor="w", padx=16, pady=(12, 2))
        br = tk.Frame(c3, bg=T.CARD)
        br.pack(anchor="w", padx=16, pady=(0, 12))
        self._sbtn(br, "Синхронизировать upstream", self._update_bundle).pack(side="left", padx=(0, 6))
        self.quick_tg_btn = self._sbtn(br, "Запустить TG Proxy", self._tg_toggle)
        self.quick_tg_btn.pack(side="left", padx=(0, 6))
        self._sbtn(br, "Скрыть в трей", self._hide_to_tray).pack(side="left", padx=(0, 6))
        self._sbtn(br, "Выйти полностью", self._confirm_full_exit).pack(side="left", padx=(0, 6))
        self._sbtn(br, "Открыть папку", self._open_folder).pack(side="left", padx=(0, 6))
        self._sbtn(br, "Открыть лог-файл", self._open_logfile).pack(side="left")

        lc = self._card(t)
        lc.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        tk.Label(lc, text="СОБЫТИЯ", font=T.FS, bg=T.CARD, fg=T.DIM).pack(anchor="w", padx=16, pady=(12, 4))
        self.dlog = tk.Text(
            lc,
            height=6,
            bg=T.INP,
            fg=T.FG,
            font=T.FM,
            bd=0,
            insertbackground=T.FG,
            highlightthickness=1,
            highlightbackground=T.BRD,
            state="disabled",
            wrap="word",
        )
        self.dlog.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def _tg_update_ui(self):
        if not hasattr(self, "tg_toggle_btn"):
            return
        running = is_tg_proxy_running()
        self.tg_toggle_btn.configure(
            text="■ Остановить WS Proxy" if running else "▶ Запустить WS Proxy",
            bg=T.ERR if running else T.OK,
        )
        self.tg_status_text.configure(
            text=f"● Запущен (127.0.0.1:{self.tg_port_var.get()})" if running else "● Не запущен",
            fg=T.OK if running else T.ERR,
        )
        self.tg_status_label.configure(
            text="TG Proxy: ON" if running else "",
            fg=T.OK if running else T.DIM,
        )
        self.tg_stats_label.configure(text=get_tg_proxy_stats())
        self._refresh_quick_action_buttons()
        self._update_tray_tooltip()

    def _upd_ui(self):
        try:
            on = self.backend.is_running
            tg = is_tg_proxy_running()
            self.tbtn.configure(text="■  ОСТАНОВИТЬ" if on else "▶  ЗАПУСТИТЬ", bg=T.ERR if on else T.OK)
            parts = []
            if on:
                parts.append("● DPI: ON")
            if tg:
                parts.append("TG: ON")
            if not parts:
                status_text = "● НЕАКТИВЕН"
                status_fg = T.ERR
            else:
                status_text = "  ".join(parts)
                status_fg = T.OK
            self.hstat.configure(text=status_text, fg=status_fg)
            self.sd.configure(text=f"Профиль: {self.profiles[self.active_idx].name}" if on else "Модификация отключена")
            self.ifill.configure(bg=T.OK if on else T.ERR)
            self.ibar.configure(bg=T.OKD if on else T.ERRD)
            self._refresh_quick_action_buttons()
            self._update_tray_tooltip()
        except Exception:
            pass

    def _make_scrollable_tab(self, title: str):
        tab = tk.Frame(self.nb, bg=T.BG)
        self.nb.add(tab, text=title)

        outer = tk.Frame(tab, bg=T.BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=T.BG, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        body = tk.Frame(canvas, bg=T.BG)
        body_window = canvas.create_window((0, 0), window=body, anchor="nw")

        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(body_window, width=e.width))

        def _on_mousewheel(event):
            delta = event.delta if event.delta else (-120 if getattr(event, "num", None) == 5 else 120)
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)
        body.bind("<MouseWheel>", _on_mousewheel)
        return body

    def _tg_open_settings(self):
        uri = "tg://settings"
        self._log_ui(f"Открываю настройки Telegram: {uri}", "info")
        try:
            os.startfile(uri)
        except Exception:
            messagebox.showinfo(
                "Telegram",
                "Не удалось открыть настройки Telegram автоматически.\n\n"
                "Откройте в Telegram: Settings -> Advanced -> Connection Type -> Disable proxy",
            )

    def _tab_cfg(self):
        t = tk.Frame(self.nb, bg=T.BG)
        self.nb.add(t, text="  Конфигурации  ")

        pw = ttk.Panedwindow(t, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=12, pady=12)

        lf = tk.Frame(pw, bg=T.BG)
        rf = tk.Frame(pw, bg=T.BG)
        pw.add(lf, weight=1)
        pw.add(rf, weight=2)

        tp = tk.Frame(lf, bg=T.BG)
        tp.pack(fill="x", pady=(0, 8))
        tk.Label(tp, text="Профили", font=T.FL, bg=T.BG, fg=T.BR).pack(side="left")
        self._sbtn(tp, "+ Новый", self._addp).pack(side="right", padx=(6, 0))
        self._sbtn(tp, "Импорт", self._imp).pack(side="right")

        cc = self._card(lf)
        cc.pack(fill="both", expand=True)
        list_wrap = tk.Frame(cc, bg=T.CARD)
        list_wrap.pack(fill="both", expand=True, padx=2, pady=2)
        list_scroll = ttk.Scrollbar(list_wrap, orient="vertical")
        self.plb = tk.Listbox(
            list_wrap,
            bg=T.INP,
            fg=T.FG,
            font=T.F,
            bd=0,
            selectbackground=T.ACC,
            selectforeground=T.BR,
            activestyle="none",
            highlightthickness=0,
            yscrollcommand=list_scroll.set,
        )
        list_scroll.configure(command=self.plb.yview)
        self.plb.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")
        self.plb.bind("<<ListboxSelect>>", self._onsel)

        rc = self._card(rf)
        rc.pack(fill="both", expand=True)
        inn = tk.Frame(rc, bg=T.CARD)
        inn.pack(fill="both", expand=True, padx=16, pady=16)
        inn.grid_columnconfigure(0, weight=1)
        inn.grid_rowconfigure(5, weight=1)

        tk.Label(inn, text="Название:", font=T.FB, bg=T.CARD, fg=T.DIM).grid(row=0, column=0, sticky="w")
        self.cn = tk.StringVar()
        self._entry(inn, self.cn).grid(row=1, column=0, sticky="ew", pady=(2, 8), ipady=5)

        tk.Label(inn, text="Описание:", font=T.FB, bg=T.CARD, fg=T.DIM).grid(row=2, column=0, sticky="w")
        self.cd = tk.StringVar()
        self._entry(inn, self.cd).grid(row=3, column=0, sticky="ew", pady=(2, 8), ipady=5)

        tk.Label(inn, text="Аргументы winws2 (по строке):", font=T.FB, bg=T.CARD, fg=T.DIM).grid(row=4, column=0, sticky="w")

        text_wrap = tk.Frame(inn, bg=T.CARD)
        text_wrap.grid(row=5, column=0, sticky="nsew", pady=(2, 10))
        text_wrap.grid_columnconfigure(0, weight=1)
        text_wrap.grid_rowconfigure(0, weight=1)

        text_scroll = ttk.Scrollbar(text_wrap, orient="vertical")
        self.ca = tk.Text(
            text_wrap,
            bg=T.INP,
            fg=T.FG,
            font=T.FM,
            bd=0,
            insertbackground=T.FG,
            wrap="word",
            highlightthickness=1,
            highlightbackground=T.BRD,
            highlightcolor=T.BRF,
            yscrollcommand=text_scroll.set,
        )
        text_scroll.configure(command=self.ca.yview)
        self.ca.grid(row=0, column=0, sticky="nsew")
        text_scroll.grid(row=0, column=1, sticky="ns")

        br = tk.Frame(inn, bg=T.CARD)
        br.grid(row=6, column=0, sticky="ew")
        self._abtn(br, "Применить", T.OK, self._applp).pack(side="left", padx=(0, 6))
        self._abtn(br, "Сохранить", T.ACC, self._savep).pack(side="left", padx=(0, 6))
        self._abtn(br, "Удалить", T.ERR, self._delp).pack(side="left", padx=(0, 6))
        self._abtn(br, "Экспорт", T.HOV, self._expp).pack(side="right")

        self._refp()

    def _tab_telegram(self):
        t = self._make_scrollable_tab("  📱 Telegram  ")

        top = tk.Frame(t, bg=T.BG)
        top.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(top, text="📱 Telegram WebSocket Proxy", font=T.FL, bg=T.BG, fg=T.BR).pack(side="left")
        self.tg_status_label = tk.Label(top, text="", font=T.FB, bg=T.BG, fg=T.DIM)
        self.tg_status_label.pack(side="right", padx=(0, 8))

        content = tk.Frame(t, bg=T.BG)
        content.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        desc_card = self._card(content)
        desc_card.pack(fill="x", pady=(0, 8))
        desc_inner = tk.Frame(desc_card, bg=T.CARD)
        desc_inner.pack(fill="x", padx=16, pady=12)

        if not HAS_TG_PROXY:
            tk.Label(desc_inner, text="⚠ Нужны дополнительные библиотеки", font=T.FB, bg=T.CARD, fg=T.WARN).pack(anchor="w")
            if getattr(sys, "frozen", False):
                msg = (
                    "В этой сборке отсутствует встроенная библиотека cryptography.\n"
                    "Это ошибка упаковки релиза, а не проблема пользователя.\n"
                    "Скачайте полный Win10/11 билд приложения."
                )
            else:
                msg = "Установите: pip install cryptography\nЗатем перезапустите приложение."
            tk.Label(desc_inner, text=msg, font=T.F, bg=T.CARD, fg=T.DIM, justify="left").pack(anchor="w", pady=(4, 0))
            return

        tk.Label(
            desc_inner,
            text="Ускоряет Telegram, направляя трафик через WebSocket (TLS)\n"
                 "к серверам kws*.web.telegram.org. Работает параллельно с zapret.",
            font=T.F, bg=T.CARD, fg=T.DIM, justify="left",
        ).pack(anchor="w")
        tk.Label(
            desc_inner,
            text="Telegram -> SOCKS5 (127.0.0.1) -> WS Proxy -> WSS -> Telegram DC",
            font=("Consolas", 10), bg=T.CARD, fg=T.INFO,
        ).pack(anchor="w", pady=(6, 0))

        ctrl_card = self._card(content)
        ctrl_card.pack(fill="x", pady=(0, 8))
        ctrl_inner = tk.Frame(ctrl_card, bg=T.CARD)
        ctrl_inner.pack(fill="x", padx=16, pady=12)

        btn_row = tk.Frame(ctrl_inner, bg=T.CARD)
        btn_row.pack(fill="x", pady=(0, 8))
        self.tg_toggle_btn = self._abtn(btn_row, "▶ Запустить WS Proxy", T.OK, self._tg_toggle)
        self.tg_toggle_btn.pack(side="left", padx=(0, 8))
        self.tg_link_btn = self._abtn(btn_row, "📲 Открыть в Telegram", T.ACC, self._tg_open_link)
        self.tg_link_btn.pack(side="left", padx=(0, 8))
        self._sbtn(btn_row, "📋 Копировать ссылку", self._tg_copy_link).pack(side="left", padx=(0, 8))
        self._sbtn(btn_row, "⚙ Открыть настройки Telegram", self._tg_open_settings).pack(side="left")

        self.tg_status_text = tk.Label(ctrl_inner, text="● Не запущен", font=T.FB, bg=T.CARD, fg=T.ERR)
        self.tg_status_text.pack(anchor="w", pady=(4, 0))

        port_row = tk.Frame(ctrl_inner, bg=T.CARD)
        port_row.pack(fill="x", pady=(8, 0))
        tk.Label(port_row, text="Порт:", font=T.FB, bg=T.CARD, fg=T.DIM).pack(side="left")
        self.tg_port_var = tk.StringVar(value=str(DEFAULT_PORT))
        port_entry = self._entry(port_row, self.tg_port_var)
        port_entry.configure(width=8)
        port_entry.pack(side="left", padx=(4, 12), ipady=3)
        tk.Label(port_row, text="(по умолчанию 1080)", font=T.FS, bg=T.CARD, fg=T.DIM).pack(side="left")

        help_card = self._card(content)
        help_card.pack(fill="x", pady=(0, 8))
        help_inner = tk.Frame(help_card, bg=T.CARD)
        help_inner.pack(fill="x", padx=16, pady=12)
        tk.Label(help_inner, text="Как подключить", font=T.FB, bg=T.CARD, fg=T.FG).pack(anchor="w")
        for step in [
            "1. Нажмите «Запустить WS Proxy» выше",
            "2. Нажмите «Открыть в Telegram» — Telegram предложит добавить прокси",
            "3. Подтвердите в Telegram — настройка сохранится",
            "",
            "После остановки локального WS Proxy Telegram может продолжать хранить SOCKS5 как активный.",
            "Если Telegram перестал подключаться, откройте его настройки и нажмите Disable proxy.",
        ]:
            fg = T.FG if step and step[:1].isdigit() else T.DIM
            tk.Label(help_inner, text=step, font=T.F, bg=T.CARD, fg=fg, anchor="w", justify="left").pack(anchor="w", pady=1)

        stats_card = self._card(content)
        stats_card.pack(fill="both", expand=True)
        stats_inner = tk.Frame(stats_card, bg=T.CARD)
        stats_inner.pack(fill="both", expand=True, padx=16, pady=12)
        tk.Label(stats_inner, text="Статистика", font=T.FB, bg=T.CARD, fg=T.FG).pack(anchor="w")
        self.tg_stats_label = tk.Label(
            stats_inner, text="Прокси не запущен", font=T.FM, bg=T.CARD, fg=T.DIM,
            anchor="w", justify="left",
        )
        self.tg_stats_label.pack(anchor="w", fill="x", pady=(4, 0))
        self._tg_poll()

    def _tg_toggle(self):
        if is_tg_proxy_running():
            ok, msg = stop_tg_proxy()
            self._log_ui(f"TG Proxy: {msg}", "warning" if ok else "error")
            if ok and messagebox.askyesno(
                "TG Proxy остановлен",
                "Локальный Telegram WS Proxy выключен.\n\n"
                "Telegram хранит SOCKS5 отдельно и может продолжать пытаться подключаться через него.\n"
                "Открыть настройки Telegram, чтобы вы могли нажать Disable proxy?"
            ):
                self._tg_open_settings()
        else:
            try:
                port = int(self.tg_port_var.get())
            except ValueError:
                port = DEFAULT_PORT
            ok, msg = start_tg_proxy(port)
            self._log_ui(f"TG Proxy: {msg}", "success" if ok else "error")
            if not ok:
                messagebox.showerror("Ошибка", msg)
        self._tg_update_ui()

    def _tab_set(self):
        t = self._make_scrollable_tab("  Настройки  ")
        c = self._card(t)
        c.pack(fill="both", expand=True, padx=12, pady=12)
        inn = tk.Frame(c, bg=T.CARD)
        inn.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(inn, text="Пути", font=T.FL, bg=T.CARD, fg=T.BR).pack(anchor="w", pady=(0, 12))
        self.svars = {}
        for k, lb in [
            ("winws_bin", "Путь к winws2.exe:"),
            ("lua_dir", "Lua скрипты:"),
            ("lists_dir", "Файлы / списки:"),
            ("winws_dir", "Рабочая директория:"),
        ]:
            tk.Label(inn, text=lb, font=T.FB, bg=T.CARD, fg=T.DIM).pack(anchor="w", pady=(6, 0))
            v = tk.StringVar(value=self.settings.get(k, ""))
            self.svars[k] = v
            r = tk.Frame(inn, bg=T.CARD)
            r.pack(fill="x", pady=(2, 4))
            self._entry(r, v).pack(side="left", fill="x", expand=True, ipady=5)
            tk.Button(
                r, text="...", font=T.FB, bg=T.HOV, fg=T.FG, bd=0, padx=10, pady=3,
                cursor="hand2", command=lambda v=v: v.set(filedialog.askdirectory() or v.get())
            ).pack(side="right", padx=(6, 0))

        tk.Label(inn, text="Автоматизация", font=T.FL, bg=T.CARD, fg=T.BR).pack(anchor="w", pady=(16, 8))
        self.autostart_var = tk.BooleanVar(value=self.settings.get("autostart_enabled", False))
        self.monthly_sync_var = tk.BooleanVar(value=self.settings.get("monthly_auto_sync", True))

        tk.Checkbutton(
            inn,
            text="Запускать приложение при входе в Windows (через Планировщик задач, с правами администратора)",
            variable=self.autostart_var,
            bg=T.CARD, fg=T.FG, selectcolor=T.INP, activebackground=T.CARD,
            activeforeground=T.FG, font=T.F, wraplength=760, justify="left",
        ).pack(anchor="w")
        self.autostart_state_lbl = tk.Label(inn, text="", font=T.FS, bg=T.CARD, fg=T.DIM, justify="left", wraplength=760)
        self.autostart_state_lbl.pack(anchor="w", pady=(2, 8))

        tk.Checkbutton(
            inn,
            text=f"Раз в {AUTO_SYNC_INTERVAL_DAYS} дней проверять апдейты upstream при запуске приложения",
            variable=self.monthly_sync_var,
            bg=T.CARD, fg=T.FG, selectcolor=T.INP, activebackground=T.CARD,
            activeforeground=T.FG, font=T.F, wraplength=760, justify="left",
        ).pack(anchor="w")
        self.auto_sync_state_lbl = tk.Label(inn, text="", font=T.FS, bg=T.CARD, fg=T.DIM, justify="left", wraplength=760)
        self.auto_sync_state_lbl.pack(anchor="w", pady=(2, 8))

        tk.Label(inn, text="Обслуживание", font=T.FL, bg=T.CARD, fg=T.BR).pack(anchor="w", pady=(16, 8))
        mr = tk.Frame(inn, bg=T.CARD)
        mr.pack(fill="x")
        self._abtn(mr, "Сохранить", T.OK, self._saveset).pack(side="left", padx=(0, 6), pady=(0, 6))
        self._abtn(mr, "Синхронизировать upstream", T.WARN, self._update_bundle).pack(side="left", padx=(0, 6), pady=(0, 6))
        self._abtn(mr, "Удалить WinDivert", T.ERR, self._del_wd).pack(side="left", padx=(0, 6), pady=(0, 6))
        if not is_admin():
            self._abtn(mr, "Запросить админ", T.ACC, request_admin).pack(side="left", pady=(0, 6))
        self._refresh_automation_state()

    def _saveset(self):
        for k, v in self.svars.items():
            self.settings[k] = v.get()

        autostart_ok = True
        autostart_msg = ""
        desired_autostart = bool(self.autostart_var.get())
        if desired_autostart != bool(self.settings.get("autostart_enabled", False)):
            autostart_ok, autostart_msg = set_autostart_enabled(desired_autostart)

        self.settings["autostart_enabled"] = is_autostart_enabled()
        self.autostart_var.set(self.settings["autostart_enabled"])
        self.settings["monthly_auto_sync"] = bool(self.monthly_sync_var.get())

        save_settings(self.settings)
        self.backend.settings = self.settings
        self._refresh_automation_state()

        if autostart_ok:
            self._log_ui("Настройки сохранены", "success")
        else:
            self._log_ui(f"Автозапуск: {autostart_msg}", "error")
            self._log_ui("Остальные настройки сохранены", "warning")
    def _del_wd(self):
        wd = os.path.join(WINWS_DIR, "windivert_delete.cmd")
        if os.path.isfile(wd):
            if messagebox.askyesno("WinDivert", "Выгрузить WinDivert?"):
                subprocess.run(["cmd", "/c", wd], cwd=WINWS_DIR,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self._log_ui("WinDivert удалён", "warning")
        else:
            messagebox.showinfo("Инфо", "windivert_delete.cmd не найден")
