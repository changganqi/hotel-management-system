from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


APP_NAME = "山海宾馆房量同步台"
DIST_NAME = "ShanhaiHotelSync"
UNINSTALL_REG_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{DIST_NAME}"
KEEP_ON_PARTIAL_UNINSTALL = {".env", "data", "sessions"}


def default_install_root() -> Path:
    local_appdata = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return local_appdata / DIST_NAME


def resolve_install_root(raw_target: str = "") -> Path:
    if raw_target:
        return Path(raw_target).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return default_install_root()


def desktop_dir() -> Path:
    try:
        import ctypes
        from ctypes import wintypes

        CSIDL_DESKTOPDIRECTORY = 0x0010
        SHGFP_TYPE_CURRENT = 0
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, SHGFP_TYPE_CURRENT, buf)
        return Path(buf.value)
    except Exception:
        return Path.home() / "Desktop"


def programs_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def message_box(text: str, flags: int) -> int:
    try:
        import ctypes

        return int(ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags))
    except Exception:
        return 0


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def delete_file_later(path: Path) -> None:
    if not path.exists():
        return
    script = (
        "@echo off\r\n"
        "ping 127.0.0.1 -n 3 > nul\r\n"
        f'del /f /q "{path}"\r\n'
        'del /f /q "%~f0"\r\n'
    )
    temp_script = Path(tempfile.gettempdir()) / f"{DIST_NAME}-delete-file.cmd"
    temp_script.write_text(script, encoding="utf-8")
    subprocess.Popen(
        ["cmd.exe", "/c", str(temp_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def remove_shortcuts() -> None:
    remove_path(desktop_dir() / f"{APP_NAME}.lnk")
    start_menu_dir = programs_dir() / APP_NAME
    remove_path(start_menu_dir / f"{APP_NAME}.lnk")
    remove_path(start_menu_dir / f"卸载 {APP_NAME}.lnk")
    try:
        start_menu_dir.rmdir()
    except OSError:
        pass


def unregister_uninstall_entry() -> None:
    try:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_KEY)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def stop_running_app() -> None:
    subprocess.run(
        ["taskkill.exe", "/IM", "ShanhaiHotelSync.exe", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def delete_install_root_later(install_root: Path) -> None:
    script = (
        "@echo off\r\n"
        "ping 127.0.0.1 -n 3 > nul\r\n"
        f'rmdir /s /q "{install_root}"\r\n'
        'del /f /q "%~f0"\r\n'
    )
    temp_script = Path(tempfile.gettempdir()) / f"{DIST_NAME}-cleanup.cmd"
    temp_script.write_text(script, encoding="utf-8")
    subprocess.Popen(
        ["cmd.exe", "/c", str(temp_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def partial_remove_install_root(install_root: Path) -> None:
    if not install_root.exists():
        return
    current_exe = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None
    for child in install_root.iterdir():
        if child.name in KEEP_ON_PARTIAL_UNINSTALL:
            continue
        if current_exe is not None and child.resolve() == current_exe:
            continue
        remove_path(child)
    if current_exe is not None and current_exe.exists():
        delete_file_later(current_exe)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--target", default="")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--delete-data", action="store_true")
    parser.add_argument("--keep-data", action="store_true")
    return parser.parse_known_args()[0]


def main() -> int:
    args = parse_args()
    install_root = resolve_install_root(args.target)

    delete_all = bool(args.delete_data)
    if not args.quiet and not args.delete_data and not args.keep_data:
        result = message_box(
            "是否同时删除库存数据和平台登录状态？\n\n"
            "选择“是”：完全卸载并删除 data、sessions、.env。\n"
            "选择“否”：只卸载程序，保留数据，方便以后重装恢复。\n"
            "选择“取消”：不卸载。",
            0x23,
        )
        if result == 2:
            return 0
        delete_all = result == 6

    try:
        stop_running_app()
        remove_shortcuts()
        unregister_uninstall_entry()

        if delete_all:
            delete_install_root_later(install_root)
        else:
            partial_remove_install_root(install_root)

        if not args.quiet:
            message_box("卸载完成。", 0x40)
        return 0
    except Exception as exc:
        if not args.quiet:
            message_box(f"卸载失败：{exc}", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
