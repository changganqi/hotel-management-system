from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import argparse
from pathlib import Path


APP_NAME = "山海宾馆房量同步台"
DIST_NAME = "ShanhaiHotelSync"
PAYLOAD_NAME = "ShanhaiHotelSync-bundled.zip"


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


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


def create_shortcut(shortcut_path: Path, target: Path, working_dir: Path, icon: Path) -> None:
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    icon_value = str(icon) if icon.exists() else str(target)
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut({str(shortcut_path)!r}); "
        f"$shortcut.TargetPath = {str(target)!r}; "
        f"$shortcut.WorkingDirectory = {str(working_dir)!r}; "
        f"$shortcut.IconLocation = {icon_value!r}; "
        "$shortcut.Save()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def copy_user_state(old_root: Path, new_root: Path) -> None:
    for name in ("data", "sessions", ".env"):
        source = old_root / name
        target = new_root / name
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            if target.exists():
                continue
            shutil.copy2(source, target)


def install(*, target_root: Path | None = None) -> Path:
    payload = resource_path(PAYLOAD_NAME)
    if not payload.exists():
        raise FileNotFoundError(f"安装包缺少资源：{PAYLOAD_NAME}")

    if target_root is None:
        local_appdata = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        install_root = local_appdata / DIST_NAME
    else:
        install_root = target_root
    temp_root = Path(tempfile.mkdtemp(prefix="ShanhaiHotelSync-install-"))

    try:
        with zipfile.ZipFile(payload, "r") as archive:
            archive.extractall(temp_root)

        extracted_root = temp_root / DIST_NAME
        exe_path = extracted_root / "ShanhaiHotelSync.exe"
        if not exe_path.exists():
            raise FileNotFoundError("安装包内容不完整：未找到 ShanhaiHotelSync.exe")

        if install_root.exists():
            copy_user_state(install_root, extracted_root)
            backup_root = install_root.with_name(install_root.name + ".old")
            if backup_root.exists():
                shutil.rmtree(backup_root)
            install_root.rename(backup_root)

        install_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted_root), str(install_root))

        (install_root / "data").mkdir(exist_ok=True)
        (install_root / "sessions").mkdir(exist_ok=True)

        env_path = install_root / ".env"
        env_example = install_root / ".env.example"
        if not env_path.exists() and env_example.exists():
            shutil.copy2(env_example, env_path)

        target = install_root / "ShanhaiHotelSync.exe"
        icon = install_root / "static" / "favicon.ico"
        create_shortcut(desktop_dir() / f"{APP_NAME}.lnk", target, install_root, icon)
        create_shortcut(programs_dir() / APP_NAME / f"{APP_NAME}.lnk", target, install_root, icon)

        return target
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--target", default="")
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_known_args()[0]


def main() -> int:
    args = parse_args()
    try:
        target_root = Path(args.target).resolve() if args.target else None
        target = install(target_root=target_root)
        if not args.no_launch:
            subprocess.Popen([str(target)], cwd=str(target.parent))
        if not args.quiet:
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(None, "安装完成，已创建桌面快捷方式。", APP_NAME, 0x40)
            except Exception:
                pass
        return 0
    except Exception as exc:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, f"安装失败：{exc}", APP_NAME, 0x10)
        except Exception:
            print(f"安装失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
