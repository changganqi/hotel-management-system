import argparse
import getpass
import os
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from dotenv import load_dotenv
from playwright.sync_api import BrowserContext, Page, Playwright, TimeoutError, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SESSION_ROOT = BASE_DIR / "sessions"
DEFAULT_TIMEOUT_MS = 8000
SYNC_BROWSER_CDP_PORT = int(os.getenv("SYNC_BROWSER_CDP_PORT", "9333"))
FLIGGY_SYNC_BROWSER_CDP_PORT = int(os.getenv("FLIGGY_SYNC_BROWSER_CDP_PORT", "9334"))
MEITUAN_SYNC_BROWSER_CDP_PORT = int(os.getenv("MEITUAN_SYNC_BROWSER_CDP_PORT", "9335"))
FLIGGY_LOGIN_URL = "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk/accountsmanage/manage"
CTRIP_BATCH_PAGE_URL = "https://ebooking.trip.com/rateplan/batchSetRoomStatusAndQuantity?microJump=true"
FLIGGY_ROOMS_MANAGE_URL = "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk-rp/roomsVsManage"
FLIGGY_BATCH_STATUS_URL = "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk-rp/batchRoomStatusUpdate?type=status"
MEITUAN_BATCH_PAGE_URL = "https://me.meituan.com/ebooking/merchant/product/batch-inventory"


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    display_name: str
    login_url: str
    runner: Callable[[Page, Optional[Credentials], str], bool]


def has_any_visible(page: Page, selectors: Iterable[str], timeout_ms: int = 1200) -> bool:
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=timeout_ms):
                return True
        except Exception:
            continue
    return False


def try_fill(page: Page, selectors: Iterable[str], value: str, field_name: str) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
            locator.click(timeout=DEFAULT_TIMEOUT_MS)
            try:
                locator.fill("")
                locator.type(value, delay=25)
            except Exception:
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                page.keyboard.type(value, delay=25)
            print(f"  - Filled {field_name} with selector: {selector}")
            return True
        except Exception:
            continue

    print(f"  - Could not auto-fill {field_name}; please fill manually.")
    return False


def try_click(page: Page, selectors: Iterable[str], action_name: str) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
            locator.click(timeout=DEFAULT_TIMEOUT_MS)
            print(f"  - Clicked {action_name} with selector: {selector}")
            return True
        except Exception:
            continue

    print(f"  - Could not click {action_name}; please click manually.")
    return False


def wait_for_manual_step(display_name: str) -> None:
    print(f"[{display_name}] If captcha/slider appears, complete it in the browser.")
    input(f"[{display_name}] Press Enter here after captcha/login is complete... ")


def likely_logged_in(page: Page, login_url_keywords: Iterable[str]) -> bool:
    current_url = page.url.lower()
    return not any(keyword in current_url for keyword in login_url_keywords)


def launch_context(
    playwright: Playwright,
    profile_name: str,
    *,
    remote_debug_port: int | None = None,
    hide_automation_banner: bool = True,
    inject_anti_bot_script: bool = False,
) -> BrowserContext:
    profile_dir = SESSION_ROOT / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    launch_args = [
        "--start-maximized",
        "--disable-blink-features=AutomationControlled",
        "--disable-extensions",
    ]
    if remote_debug_port is not None:
        launch_args.append(f"--remote-debugging-port={int(remote_debug_port)}")

    preferred_channel = os.getenv("LOGIN_BROWSER_CHANNEL", "msedge").strip().lower()

    launch_kwargs = {
        "user_data_dir": str(profile_dir),
        "headless": False,
        "no_viewport": True,
        "args": launch_args,
    }
    if hide_automation_banner:
        launch_kwargs["ignore_default_args"] = ["--enable-automation"]

    context: BrowserContext
    if preferred_channel:
        try:
            context = playwright.chromium.launch_persistent_context(
                channel=preferred_channel,
                **launch_kwargs,
            )
        except Exception:
            context = playwright.chromium.launch_persistent_context(**launch_kwargs)
    else:
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
    if inject_anti_bot_script:
        # Reduce obvious webdriver fingerprints for strict anti-bot pages.
        context.add_init_script(
            """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
"""
        )
    return context


def ensure_chromium_installed() -> bool:
    preferred_channel = os.getenv("LOGIN_BROWSER_CHANNEL", "msedge").strip().lower()
    if preferred_channel and preferred_channel != "chromium":
        # When using branded channels (e.g., msedge), browser binaries are provided by system install.
        return True

    with sync_playwright() as playwright:
        executable_path = Path(playwright.chromium.executable_path)

    if executable_path.exists():
        return True

    print("Playwright Chromium browser is missing.")
    print("Run this once:")
    print("  python -m playwright install chromium")
    return False


def read_credentials_from_env(platform_key: str) -> Optional[Credentials]:
    env_prefix = platform_key.upper()
    username = os.getenv(f"{env_prefix}_USERNAME", "").strip()
    password = os.getenv(f"{env_prefix}_PASSWORD", "").strip()

    if username and password:
        return Credentials(username=username, password=password)
    return None


def prompt_for_credentials(display_name: str) -> Credentials:
    username = input(f"[{display_name}] Username: ").strip()
    password = getpass.getpass(f"[{display_name}] Password: ").strip()
    return Credentials(username=username, password=password)


def ensure_credentials(credentials: Optional[Credentials], display_name: str) -> Credentials:
    if credentials is not None:
        return credentials
    return prompt_for_credentials(display_name)


def wait_for_any_visible(page: Page, selectors: Iterable[str], timeout_ms: int = 12000) -> bool:
    end_time = time.time() + timeout_ms / 1000
    while time.time() < end_time:
        if has_any_visible(page, selectors, timeout_ms=500):
            return True
        page.wait_for_timeout(250)
    return False


def login_ctrip(page: Page, credentials: Optional[Credentials], display_name: str) -> bool:
    print(f"\n[{display_name}] Opening login page...")
    page.goto("https://ebooking.trip.com/login/index", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    login_keywords = ("login", "signin")
    if likely_logged_in(page, login_keywords):
        print(f"[{display_name}] Existing session detected. Skipping login.")
        return True

    credentials = ensure_credentials(credentials, display_name)

    username_selectors = [
        "input[type='text']",
        "input[placeholder*='phone']",
        "input[placeholder*='account']",
        "xpath=/html/body/div[1]/div/div[1]/div/div[1]/div/div[2]/div/div[1]/div[1]/div/span[1]/div/div[2]/span",
        "xpath=/html/body/div[1]/div/div[1]/div/div[1]/div/div[2]/div/div[1]/div[1]//input",
    ]
    password_selectors = [
        "input[type='password']",
        "xpath=/html/body/div[1]/div/div[1]/div/div[1]/div/div[2]/div/div[1]/div[2]/div[2]/span/input",
    ]
    login_button_selectors = [
        "button:has-text('Login')",
        "button:has-text('登录')",
        "xpath=/html/body/div[1]/div/div[1]/div/div[1]/div/div[2]/div/button",
    ]

    try_fill(page, username_selectors, credentials.username, "username")
    try_fill(page, password_selectors, credentials.password, "password")
    try_click(page, login_button_selectors, "login button")

    wait_for_manual_step(display_name)

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except TimeoutError:
        pass

    success = likely_logged_in(page, login_keywords)
    print(f"[{display_name}] Login {'success' if success else 'status uncertain, please verify in browser'}.")
    return success


def login_fliggy(page: Page, credentials: Optional[Credentials], display_name: str) -> bool:
    print(f"\n[{display_name}] Opening login page...")
    page.goto(FLIGGY_LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    username_selectors = [
        "input[type='text']",
        "input[placeholder*='account']",
        "xpath=/html/body/div/div/div/div[2]/div[2]/div/div/div[2]/input",
    ]
    next_button_selectors = [
        "button:has-text('Next')",
        "button:has-text('下一步')",
        "xpath=/html/body/div/div/div/div[2]/div[2]/div/div/div[3]/button",
    ]
    password_selectors = [
        "input[type='password']",
        "xpath=/html/body/div/div/div[2]/div/form/div[2]/div[2]/input",
    ]
    submit_selectors = [
        "button:has-text('登录')",
        "button:has-text('Login')",
        "xpath=/html/body/div/div/div[2]/div/form/div[4]/button",
    ]

    current_url = page.url.lower()
    if "login" not in current_url and not has_any_visible(page, username_selectors):
        print(f"[{display_name}] Existing session detected. Skipping login.")
        return True

    if not wait_for_any_visible(page, username_selectors, timeout_ms=12000):
        print(f"[{display_name}] Login form not detected. Please login manually in browser.")
        wait_for_manual_step(display_name)
        return "login" not in page.url.lower()

    credentials = ensure_credentials(credentials, display_name)

    try_fill(page, username_selectors, credentials.username, "username")
    print(f"[{display_name}] To reduce risk-control failures, click Next and complete slider manually.")
    wait_for_manual_step(display_name)

    if wait_for_any_visible(page, password_selectors, timeout_ms=10000):
        try_fill(page, password_selectors, credentials.password, "password")
        print(f"[{display_name}] Please click login manually and complete any verification.")
        wait_for_manual_step(display_name)
    else:
        print(f"[{display_name}] Password field was not detected; continuing in manual mode.")

    _ = next_button_selectors, submit_selectors

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except TimeoutError:
        pass

    success = not has_any_visible(page, username_selectors)
    print(f"[{display_name}] Login {'success' if success else 'status uncertain, please verify in browser'}.")
    return success


def login_meituan(page: Page, credentials: Optional[Credentials], display_name: str) -> bool:
    login_url = "https://me.meituan.com/login/index.html"
    protected_home_url = "https://me.meituan.com/ebooking/merchant/home"

    print(f"\n[{display_name}] Opening login page...")
    page.goto(login_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    username_selectors = [
        "input[type='text']",
        "input[placeholder*='phone']",
        "input[placeholder*='账号']",
        "xpath=/html/body/div[1]/div/div[1]/div/div/form/div[1]/div/input",
    ]
    password_selectors = [
        "input[type='password']",
        "xpath=/html/body/div[1]/div/div[1]/div/div/form/div[2]/div/input",
    ]
    agree_selectors = [
        "xpath=/html/body/div[1]/div/div[1]/div/div/form/div[4]/div/div/label",
    ]
    login_button_selectors = [
        "button[type='submit']",
        "button:has-text('登录')",
        "xpath=/html/body/div[1]/div/div[1]/div/div/form/button",
    ]

    # Meituan sometimes redirects asynchronously; wait for either login form or URL change.
    username_visible = wait_for_any_visible(page, username_selectors, timeout_ms=12000)
    current_url = page.url.lower()

    if not username_visible and "login" not in current_url:
        # Confirm with a protected page to avoid false positive session detection.
        page.goto(protected_home_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        verify_url = page.url.lower()
        if "login" not in verify_url:
            print(f"[{display_name}] Existing session detected. Skipping login.")
            return True

        print(f"[{display_name}] Session looks expired, switching back to login page.")
        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        username_visible = wait_for_any_visible(page, username_selectors, timeout_ms=12000)

    if not username_visible:
        print(f"[{display_name}] Login page opened but input is not ready. Please login manually.")
        wait_for_manual_step(display_name)
        return "login" not in page.url.lower()

    credentials = ensure_credentials(credentials, display_name)

    try_fill(page, username_selectors, credentials.username, "username")
    try_fill(page, password_selectors, credentials.password, "password")
    try_click(page, agree_selectors, "agreement checkbox")
    try_click(page, login_button_selectors, "login button")

    wait_for_manual_step(display_name)

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except TimeoutError:
        pass

    success = not has_any_visible(page, username_selectors)
    print(f"[{display_name}] Login {'success' if success else 'status uncertain, please verify in browser'}.")
    return success


PLATFORMS: dict[str, PlatformSpec] = {
    "ctrip": PlatformSpec(
        key="ctrip",
        display_name="Ctrip",
        login_url="https://ebooking.trip.com/login/index",
        runner=login_ctrip,
    ),
    "fliggy": PlatformSpec(
        key="fliggy",
        display_name="Fliggy",
        login_url=FLIGGY_LOGIN_URL,
        runner=login_fliggy,
    ),
    "meituan": PlatformSpec(
        key="meituan",
        display_name="Meituan",
        login_url="https://me.meituan.com/login/index.html",
        runner=login_meituan,
    ),
}


def run(selected_platforms: list[str], close_after_login: bool) -> int:
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    load_dotenv(BASE_DIR / ".env")

    contexts: list[BrowserContext] = []

    with sync_playwright() as playwright:
        for platform_key in selected_platforms:
            spec = PLATFORMS[platform_key]
            credentials = read_credentials_from_env(platform_key)
            context = launch_context(playwright, platform_key)
            contexts.append(context)
            page = context.pages[0] if context.pages else context.new_page()

            try:
                spec.runner(page, credentials, spec.display_name)
            except Exception as exc:
                print(f"[{spec.display_name}] Login flow failed: {exc}")

        if not close_after_login:
            print("\nBrowser windows are kept open. Press Ctrl+C in terminal when you want to close all windows.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down browser windows...")

        for context in contexts:
            try:
                context.close()
            except Exception:
                continue

    return 0


def run_single_browser_tabs(selected_platforms: list[str], close_after_login: bool) -> int:
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    # Reuse ctrip profile so Ctrip sync automation can directly consume the same login session.
    profile_name = "ctrip"

    with sync_playwright() as playwright:
        context = launch_context(
            playwright,
            profile_name,
            remote_debug_port=SYNC_BROWSER_CDP_PORT,
        )
        try:
            for index, platform_key in enumerate(selected_platforms):
                spec = PLATFORMS[platform_key]
                page = context.pages[0] if index == 0 and context.pages else context.new_page()
                try:
                    page.goto(spec.login_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(500)
                except Exception as exc:
                    print(f"[{spec.display_name}] 打开登录页失败: {exc}")

            if close_after_login:
                return 0

            print("\n已在单浏览器窗口中打开平台登录页（多标签）。")
            print(f"CDP复用地址: http://127.0.0.1:{SYNC_BROWSER_CDP_PORT}")
            print("请在浏览器中完成登录，关闭所有标签页后本进程会自动退出。")

            while True:
                alive_pages = [page for page in context.pages if not page.is_closed()]
                if not alive_pages:
                    break
                time.sleep(1)
        finally:
            try:
                context.close()
            except Exception:
                pass

    return 0


def open_login_url(page: Page, login_url: str, display_name: str) -> None:
    page.goto(login_url, wait_until="domcontentloaded")

    print(f"[{display_name}] 登录页已打开")


def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return BASE_DIR


def find_bundled_browser_executable() -> str | None:
    roots = [runtime_base_dir(), runtime_base_dir() / "_internal"]
    fixed_relatives = [
        ("chrome", "chrome.exe"),
        ("browser", "chrome.exe"),
        ("GoogleChrome", "chrome.exe"),
        ("Google", "Chrome", "Application", "chrome.exe"),
    ]

    for root in roots:
        for relative in fixed_relatives:
            candidate = root.joinpath(*relative)
            if candidate.exists():
                return str(candidate)

    for root in roots:
        browsers_root = root / "ms-playwright"
        if not browsers_root.exists():
            continue
        for candidate in sorted(browsers_root.glob("chromium-*/chrome-win/chrome.exe")):
            if candidate.exists():
                return str(candidate)

    return None


def allow_system_default_browser_fallback() -> bool:
    raw = os.getenv("ALLOW_DEFAULT_BROWSER_FALLBACK", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def find_native_browser_executable() -> str | None:
    env_path = os.getenv("LOGIN_NATIVE_BROWSER_PATH", "").strip()
    bundled_path = find_bundled_browser_executable()
    candidates = [
        env_path,
        bundled_path,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]

    for candidate in candidates:
        if not candidate:
            continue
        if Path(candidate).exists():
            return candidate

    return None


def open_native_browser_window(
    login_url: str,
    display_name: str,
    *,
    profile_name: str | None = None,
    cdp_port: int | None = None,
) -> None:
    browser_exe = find_native_browser_executable()
    if browser_exe:
        args = [browser_exe, "--new-window"]
        args.append("--disable-extensions")
        if profile_name:
            profile_dir = SESSION_ROOT / profile_name
            profile_dir.mkdir(parents=True, exist_ok=True)
            args.append(f"--user-data-dir={str(profile_dir)}")
        if cdp_port is not None:
            args.append(f"--remote-debugging-port={int(cdp_port)}")
        args.append(login_url)

        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[{display_name}] 已在原生浏览器新窗口打开登录页")
        return

    if allow_system_default_browser_fallback():
        webbrowser.open_new(login_url)
        print(f"[{display_name}] 未找到指定浏览器，已调用系统默认浏览器打开登录页")
        return

    print(f"[{display_name}] 未找到可用 Chrome/Edge 可执行文件，已跳过自动打开。")
    print(f"[{display_name}] 请在 .env 中配置 LOGIN_NATIVE_BROWSER_PATH 指向压缩包里的 chrome.exe。")


def open_native_browser_tabs(
    urls: Iterable[str],
    display_name: str,
    *,
    profile_name: str | None = None,
    cdp_port: int | None = None,
) -> bool:
    tab_urls = [str(url).strip() for url in urls if str(url).strip()]
    if not tab_urls:
        return False

    browser_exe = find_native_browser_executable()
    if browser_exe:
        args = [browser_exe, "--new-window"]
        args.append("--disable-extensions")
        if profile_name:
            profile_dir = SESSION_ROOT / profile_name
            profile_dir.mkdir(parents=True, exist_ok=True)
            args.append(f"--user-data-dir={str(profile_dir)}")
        if cdp_port is not None:
            args.append(f"--remote-debugging-port={int(cdp_port)}")

        args.extend(tab_urls)
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[{display_name}] 已在单浏览器窗口打开 {len(tab_urls)} 个标签页")
        return True

    if allow_system_default_browser_fallback():
        for idx, url in enumerate(tab_urls):
            if idx == 0:
                webbrowser.open_new(url)
            else:
                webbrowser.open_new_tab(url)
        print(f"[{display_name}] 未找到指定浏览器，已调用系统默认浏览器打开标签页")
        return False

    print(f"[{display_name}] 未找到可用 Chrome/Edge 可执行文件，已跳过自动打开标签页。")
    print(f"[{display_name}] 请在 .env 中配置 LOGIN_NATIVE_BROWSER_PATH 指向压缩包里的 chrome.exe。")
    return False


def build_platform_tab_urls(selected_platforms: list[str]) -> list[str]:
    ordered_platforms: list[str] = []
    for key in ("ctrip", "fliggy", "meituan"):
        if key in selected_platforms and key not in ordered_platforms:
            ordered_platforms.append(key)
    for key in selected_platforms:
        if key not in ordered_platforms:
            ordered_platforms.append(key)

    tab_urls: list[str] = []
    if "ctrip" in ordered_platforms:
        tab_urls.append(CTRIP_BATCH_PAGE_URL)
    if "fliggy" in ordered_platforms:
        tab_urls.append(FLIGGY_ROOMS_MANAGE_URL)
    if "meituan" in ordered_platforms:
        tab_urls.append(MEITUAN_BATCH_PAGE_URL)

    return tab_urls


def run_bootstrap_browser_windows(selected_platforms: list[str]) -> int:
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)

    tab_urls = build_platform_tab_urls(selected_platforms)
    open_native_browser_tabs(
        tab_urls,
        "平台页面",
        profile_name="ctrip",
        cdp_port=SYNC_BROWSER_CDP_PORT,
    )
    print("\n已按携程、飞猪、美团顺序一次打开平台页面（单浏览器多标签）。")
    print("请在浏览器中完成登录，并保持窗口开启以便同步模块直接复用会话。")
    time.sleep(0.5)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Hotel platform login helper with persistent browser sessions "
            "for Ctrip, Fliggy, and Meituan."
        )
    )
    parser.add_argument(
        "--platform",
        choices=["all", "ctrip", "fliggy", "meituan"],
        default="all",
        help="Pick one platform or all.",
    )
    parser.add_argument(
        "--close-after-login",
        action="store_true",
        help="Close browser windows after login. By default windows stay open.",
    )
    parser.add_argument(
        "--single-browser-tabs",
        action="store_true",
        help="Open selected platforms in one browser window with multiple tabs.",
    )
    parser.add_argument(
        "--bootstrap-open-only",
        action="store_true",
        help="Open independent platform login browser windows only (no terminal interaction).",
    )
    return parser.parse_args()


def main() -> int:
    if not ensure_chromium_installed():
        return 2

    args = parse_args()
    if args.platform == "all":
        selected = ["ctrip", "fliggy", "meituan"]
    else:
        selected = [args.platform]

    if args.single_browser_tabs:
        return run_single_browser_tabs(selected, close_after_login=args.close_after_login)

    if args.bootstrap_open_only:
        return run_bootstrap_browser_windows(selected)

    return run(selected, close_after_login=args.close_after_login)


if __name__ == "__main__":
    raise SystemExit(main())
