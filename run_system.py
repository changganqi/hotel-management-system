from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from inventory_app import app
from login_manager import (
    SYNC_BROWSER_CDP_PORT,
    build_platform_tab_urls,
    ensure_chromium_installed,
    open_native_browser_tabs,
    run as run_login,
)


def resolve_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def log_runtime(message: str, exc: BaseException | None = None) -> None:
    try:
        log_dir = resolve_app_base_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "runtime.log"

        lines = [f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"]
        if exc is not None:
            lines.append(f"{type(exc).__name__}: {exc}")
            lines.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip())

        with log_file.open("a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
    except Exception:
        pass

    try:
        print(message if exc is None else f"{message}: {exc}")
    except Exception:
        pass


def resolve_runtime_asset_path(*relative_parts: str) -> Path:
    base_dir = resolve_app_base_dir()
    candidate_roots = [base_dir, base_dir / "_internal"]

    for root in candidate_roots:
        candidate = root.joinpath(*relative_parts)
        if candidate.exists():
            return candidate

    return base_dir.joinpath(*relative_parts)


def find_bundled_chrome_executable(app_base: Path) -> Path | None:
    candidate_roots = [app_base, app_base / "_internal"]
    fixed_relatives = [
        ("chrome", "chrome.exe"),
        ("browser", "chrome.exe"),
        ("GoogleChrome", "chrome.exe"),
        ("Google", "Chrome", "Application", "chrome.exe"),
    ]

    for root in candidate_roots:
        for relative in fixed_relatives:
            candidate = root.joinpath(*relative)
            if candidate.exists():
                return candidate

    for root in candidate_roots:
        browsers_root = root / "ms-playwright"
        if not browsers_root.exists():
            continue
        for candidate in sorted(browsers_root.glob("chromium-*/chrome-win/chrome.exe")):
            if candidate.exists():
                return candidate

    return None


def configure_packaged_browser_runtime() -> None:
    preferred_channel = os.getenv("LOGIN_BROWSER_CHANNEL", "").strip().lower()

    app_base = resolve_app_base_dir()
    bundled_browsers = app_base / "ms-playwright"
    has_bundled = bundled_browsers.exists()
    bundled_chrome = find_bundled_chrome_executable(app_base)

    if bundled_chrome is not None:
        os.environ.setdefault("LOGIN_NATIVE_BROWSER_PATH", str(bundled_chrome))

    if not preferred_channel:
        # Slim package defaults to Edge on Windows. If bundled browsers exist, prefer Chromium runtime.
        os.environ["LOGIN_BROWSER_CHANNEL"] = "chromium" if has_bundled else "msedge"

    if has_bundled:
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(bundled_browsers))


def tray_enabled_by_default() -> bool:
    return bool(getattr(sys, "frozen", False) and os.name == "nt")


def resolve_tray_enabled(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "no_tray", False)):
        return False
    if bool(getattr(args, "tray", False)):
        return True

    raw_env = os.getenv("ENABLE_SYSTEM_TRAY", "").strip().lower()
    if raw_env in {"1", "true", "yes", "on"}:
        return True
    if raw_env in {"0", "false", "no", "off"}:
        return False

    return tray_enabled_by_default()


def run_tray_icon(local_host: str, port: int) -> bool:
    try:
        import pystray
        from PIL import Image
    except Exception as exc:
        log_runtime("托盘组件不可用，程序已继续在后台运行", exc)
        return False

    dashboard_url = f"http://{local_host}:{int(port)}/dashboard"
    icon_path = resolve_runtime_asset_path("static", "favicon.ico")

    image = None
    if icon_path.exists():
        try:
            image = Image.open(icon_path)
            image = image.convert("RGBA")
            resample = getattr(Image, "Resampling", None)
            if resample is not None:
                image = image.resize((64, 64), resample.LANCZOS)
            else:
                image = image.resize((64, 64), Image.LANCZOS)
        except Exception as exc:
            log_runtime(f"托盘图标读取失败: {icon_path}", exc)
            image = None

    if image is None:
        image = Image.new("RGB", (64, 64), color=(19, 111, 99))

    def on_open_dashboard(icon, item) -> None:
        try:
            open_native_browser_tabs(
                [dashboard_url],
                "管理系统",
                profile_name="ctrip",
                cdp_port=SYNC_BROWSER_CDP_PORT,
            )
        except Exception:
            pass

    def on_exit_app(icon, item) -> None:
        try:
            icon.stop()
        finally:
            os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("打开管理系统", on_open_dashboard, default=True),
        pystray.MenuItem("退出软件", on_exit_app),
    )
    icon = pystray.Icon("ShanhaiHotelSync", image, "山海宾馆房量同步台", menu)
    try:
        icon.run()
    except Exception as exc:
        log_runtime("托盘启动失败，程序已继续在后台运行", exc)
        return False
    return True


def run_flask_server(host: str, port: int) -> None:
    app.run(host=host, port=port, debug=False, use_reloader=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-command startup: login platforms, persist sessions, then run management system."
    )
    parser.add_argument(
        "--login-platform",
        choices=["all", "none", "ctrip", "fliggy", "meituan"],
        default="none",
        help="Optional pre-login in terminal mode before starting Flask app.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Flask bind host.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Flask bind port.",
    )
    parser.add_argument(
        "--disable-auto-ctrip-sync",
        action="store_true",
        help="Disable auto execution of pending Ctrip sync queue after each change.",
    )
    parser.add_argument(
        "--auto-ctrip-sync-headless",
        dest="auto_ctrip_sync_headless",
        action="store_true",
        help="Run Ctrip sync automation in headless mode.",
    )
    parser.add_argument(
        "--auto-ctrip-sync-visible",
        dest="auto_ctrip_sync_headless",
        action="store_false",
        help="Run Ctrip sync automation with visible browser window.",
    )
    parser.set_defaults(auto_ctrip_sync_headless=True)
    parser.add_argument(
        "--auto-ctrip-sync-limit",
        type=int,
        default=20,
        help="Max pending Ctrip tasks to process per change request.",
    )
    parser.add_argument(
        "--no-startup-tabs",
        action="store_true",
        help="Do not auto-open startup browser tabs when the system launches.",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Enable system tray icon with quick exit menu.",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Disable system tray icon.",
    )
    return parser.parse_args()


def resolve_login_targets(login_platform: str) -> list[str]:
    if login_platform == "none":
        return []
    if login_platform == "all":
        return ["ctrip", "fliggy", "meituan"]
    return [login_platform]


def browser_host_for_local_url(host: str) -> str:
    host_text = str(host or "").strip()
    if host_text in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"
    return host_text


def wait_for_local_ready(url: str, *, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + max(1.0, float(timeout_seconds))
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(url, timeout=0.8) as response:
                status_code = int(getattr(response, "status", 200))
                if status_code < 500:
                    return True
        except (urllib_error.URLError, TimeoutError, ValueError):
            pass
        time.sleep(0.3)
    return False


def start_startup_tabs_worker(host: str, port: int) -> None:
    local_host = browser_host_for_local_url(host)
    dashboard_url = f"http://{local_host}:{int(port)}/dashboard"
    tab_urls = [dashboard_url, *build_platform_tab_urls(["ctrip", "fliggy", "meituan"])]

    def worker() -> None:
        wait_for_local_ready(dashboard_url, timeout_seconds=20.0)
        open_native_browser_tabs(
            tab_urls,
            "系统启动",
            profile_name="ctrip",
            cdp_port=SYNC_BROWSER_CDP_PORT,
        )
        print("已自动打开单浏览器四标签页：管理系统、携程、飞猪、美团")

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def main() -> int:
    configure_packaged_browser_runtime()

    args = parse_args()

    login_targets = resolve_login_targets(args.login_platform)
    if login_targets:
        if not ensure_chromium_installed():
            return 2

        print(f"准备登录平台: {', '.join(login_targets)}")
        print("登录成功后会自动关闭浏览器并持久化会话。")
        exit_code = run_login(selected_platforms=login_targets, close_after_login=True)
        if exit_code != 0:
            return exit_code

    os.environ["AUTO_SYNC_CTRIP_ENABLED"] = "0" if args.disable_auto_ctrip_sync else "1"
    os.environ["AUTO_SYNC_CTRIP_HEADLESS"] = "1" if args.auto_ctrip_sync_headless else "0"
    os.environ["AUTO_SYNC_CTRIP_LIMIT"] = str(max(1, min(200, int(args.auto_ctrip_sync_limit))))
    os.environ["AUTO_SYNC_ENABLED"] = os.environ["AUTO_SYNC_CTRIP_ENABLED"]
    os.environ["AUTO_SYNC_HEADLESS"] = os.environ["AUTO_SYNC_CTRIP_HEADLESS"]
    os.environ["AUTO_SYNC_LIMIT"] = os.environ["AUTO_SYNC_CTRIP_LIMIT"]

    local_host = browser_host_for_local_url(args.host)
    print(f"管理系统启动中... http://{local_host}:{int(args.port)}")
    print("启动后会自动打开单浏览器标签页：管理系统、携程、飞猪、美团。")

    use_tray = resolve_tray_enabled(args)
    log_runtime(f"管理系统启动: http://{local_host}:{int(args.port)} tray={int(use_tray)}")
    if use_tray:
        server_thread = threading.Thread(
            target=run_flask_server,
            args=(args.host, args.port),
            daemon=True,
        )
        server_thread.start()

        if not args.no_startup_tabs:
            start_startup_tabs_worker(args.host, args.port)

        if wait_for_local_ready(f"http://{local_host}:{int(args.port)}/dashboard", timeout_seconds=25.0):
            print("托盘已启动，可通过托盘菜单“退出软件”安全关闭。")

        if run_tray_icon(local_host, args.port):
            return 0

        # Tray creation failed. Keep service alive to avoid immediate process exit.
        try:
            while server_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return 0

    if not args.no_startup_tabs:
        start_startup_tabs_worker(args.host, args.port)

    run_flask_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
