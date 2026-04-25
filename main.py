"""
Entry point for Zapret2 Manager.
"""

import atexit
import logging
import os
import sys
import traceback

_single_instance_handle = None


def _release_single_instance():
    global _single_instance_handle
    if _single_instance_handle and sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_single_instance_handle)
        except Exception:
            pass
    _single_instance_handle = None


def _restore_existing_instance():
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, "Zapret2 Manager")
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def _acquire_single_instance():
    global _single_instance_handle
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, r"Local\Zapret2Manager_SingleInstance")
        if not mutex:
            return True
        if kernel32.GetLastError() == 183:
            _restore_existing_instance()
            ctypes.windll.user32.MessageBoxW(
                None,
                "Zapret2 Manager уже запущен.\nПроверьте окно приложения или значок в системном трее.",
                "Zapret2 Manager",
                0x00000030,
            )
            kernel32.CloseHandle(mutex)
            return False
        _single_instance_handle = mutex
        atexit.register(_release_single_instance)
    except Exception:
        return True
    return True


def main():
    if getattr(sys, "frozen", False):
        app_path = os.path.abspath(sys.executable)
        script_dir = os.path.dirname(app_path)
    else:
        app_path = os.path.abspath(__file__)
        script_dir = os.path.dirname(app_path)

    print("[main] Starting...")
    print(f"[main] Python: {sys.version}")
    print(f"[main] Platform: {sys.platform}")
    print(f"[main] CWD: {os.getcwd()}")
    print(f"[main] App path: {app_path}")

    if sys.platform != "win32":
        print("This build is Windows-only.")
        sys.exit(1)

    if not _acquire_single_instance():
        sys.exit(0)

    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    os.chdir(script_dir)
    print(f"[main] Script dir: {script_dir}")

    try:
        print("[main] Importing core...")
        from core import Bootstrap, APP_NAME, APP_VERSION, is_admin
        print("[main] core imported OK")
    except Exception as e:
        print(f"[main] FATAL: Failed to import core: {e}")
        traceback.print_exc()
        input("Press Enter...")
        sys.exit(1)

    log = logging.getLogger("main")
    log.info("=" * 40)
    log.info(f"{APP_NAME} v{APP_VERSION}")
    log.info(f"Admin: {is_admin()}")

    try:
        print("[main] Checking tkinter...")
        import tkinter  # noqa: F401
        print("[main] tkinter OK")
    except ImportError:
        print("[main] FATAL: tkinter not found!")
        input("Press Enter...")
        sys.exit(1)

    try:
        print("[main] Importing ui...")
        from ui import SetupWindow, MainApp
        print("[main] ui imported OK")
    except Exception as e:
        print(f"[main] FATAL: Failed to import ui: {e}")
        traceback.print_exc()
        log.error(f"Failed to import ui: {traceback.format_exc()}")
        input("Press Enter...")
        sys.exit(1)

    bootstrap = Bootstrap()

    if not bootstrap.check_bundle():
        log.info("Bundle not found, running setup")
        print("[main] zapret-win-bundle not found, starting setup...")

        try:
            setup = SetupWindow(bootstrap)
            success = setup.run()
        except Exception as e:
            print(f"[main] Setup error: {e}")
            traceback.print_exc()
            log.error(f"Setup error: {traceback.format_exc()}")
            input("Press Enter...")
            sys.exit(1)

        if not success:
            log.warning("Setup returned success=False, rechecking bundle...")
            if bootstrap.check_bundle():
                log.info("Bundle found despite success=False, proceeding!")
                print("[main] Bundle found, continuing...")
            else:
                log.warning("Setup not completed and bundle not found")
                print("[main] Setup incomplete. Check logs in data/logs/")
                input("Press Enter...")
                sys.exit(1)

    log.info("Starting main app")
    print("[main] Launching main window...")

    bootstrap = Bootstrap()
    log.info(f"Post-setup winws2: {bootstrap.find_winws2()}")
    log.info(f"Post-setup lua: {bootstrap.find_lua_dir()}")

    try:
        app = MainApp(bootstrap)
        app.run()
    except Exception as e:
        print(f"[main] FATAL ERROR: {e}")
        traceback.print_exc()
        log.error(f"MainApp error: {traceback.format_exc()}")
        input("Press Enter...")
        sys.exit(1)
    finally:
        _release_single_instance()

    log.info("App closed normally")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n{'=' * 50}")
        print(f"UNHANDLED ERROR: {e}")
        print(f"{'=' * 50}")
        traceback.print_exc()
        print("\nCheck logs in data/logs/")
        input("Press Enter to exit...")
