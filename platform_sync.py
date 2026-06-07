from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Final

BASE_DIR = Path(__file__).resolve().parent
SESSION_ROOT = BASE_DIR / "sessions"
CTRIP_PROFILE_DIR = SESSION_ROOT / "ctrip"
FLIGGY_PROFILE_DIR = SESSION_ROOT / "fliggy"
MEITUAN_PROFILE_DIR = SESSION_ROOT / "meituan"

CTRIP_RATEPLAN_URL: Final[str] = (
    "https://ebooking.trip.com/rateplan/batchSetRoomStatusAndQuantity?microJump=true"
)
CTRIP_ROOM_TYPE_XPATHS: Final[dict[str, str]] = {
    "度假大床房": "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/form/div/div[1]/div/div[2]/div/div[1]/div/div/div/div[1]/div/div/div[3]/div[3]/div[1]/div/div/div[1]/span[3]/span",
    "豪华双床房": "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/form/div/div[1]/div/div[2]/div/div[1]/div/div/div/div[1]/div/div/div[3]/div[3]/div[1]/div/div/div[3]/span[3]/span",
    "度假双床房": "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/form/div/div[1]/div/div[2]/div/div[1]/div/div/div/div[1]/div/div/div[3]/div[3]/div[1]/div/div/div[5]/span[3]/span",
    "家庭房": "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/form/div/div[1]/div/div[2]/div/div[1]/div/div/div/div[1]/div/div/div[3]/div[3]/div[1]/div/div/div[7]/span[3]/span",
}
CTRIP_DATE_START_XPATH: Final[str] = (
    "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/form/div/div[2]/div/div/div/div/div/div/div[2]/div/div[2]/div/div/div[1]/div[1]/div/input"
)
CTRIP_DATE_END_XPATH: Final[str] = (
    "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/form/div/div[2]/div/div/div/div/div/div/div[2]/div/div[2]/div/div/div[2]/div/div/input"
)
CTRIP_REMAINING_MODE_XPATH: Final[str] = (
    "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/form/div/div[4]/div/div[2]/div[2]/div/div/div/label[4]/span[1]/input"
)
CTRIP_REMAINING_INPUT_XPATH: Final[str] = (
    "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/form/div/div[4]/div/div[2]/div[2]/div/div/div/label[4]/span[2]/div/div[2]/div/div/div/div/div/div/div/div/div[2]/input"
)
CTRIP_SUBMIT_XPATH: Final[str] = "/html/body/div[1]/div[4]/main/div[1]/div/div/div/section/div[3]/button"
CTRIP_SUBMIT_DONE_POPUP_XPATH: Final[str] = "/html/body/div[4]/div/div[2]/div/div[2]/div/div/div[1]/div"
CTRIP_SUBMIT_SUCCESS_TITLE_XPATH: Final[str] = "/html/body/div[4]/div/div[2]/div/div[2]/div/div/div[1]/span[2]"
CTRIP_SUBMIT_SUCCESS_SELECTORS: Final[tuple[str, ...]] = (
    f"xpath={CTRIP_SUBMIT_SUCCESS_TITLE_XPATH}",
    f"xpath={CTRIP_SUBMIT_DONE_POPUP_XPATH}",
    "text=提交成功",
    "text=设置成功",
    "text=操作成功",
    "text=保存成功",
)
CTRIP_SUBMIT_FAILURE_SELECTORS: Final[tuple[str, ...]] = (
    "text=提交失败",
    "text=设置失败",
    "text=操作失败",
    "text=保存失败",
    "text=请重试",
)

SYNC_BROWSER_CDP_PORT = int(os.getenv("SYNC_BROWSER_CDP_PORT", "9333"))
FLIGGY_SYNC_BROWSER_CDP_PORT = int(os.getenv("FLIGGY_SYNC_BROWSER_CDP_PORT", "9334"))
MEITUAN_SYNC_BROWSER_CDP_PORT = int(os.getenv("MEITUAN_SYNC_BROWSER_CDP_PORT", "9335"))

# Keep references to manual handoff sessions so GC does not close browser windows immediately.
_KEEP_ALIVE_BROWSER_HANDLES: list[tuple[object | None, object | None, object | None]] = []
_MAX_KEEP_ALIVE_BROWSER_HANDLES: Final[int] = 4

FLIGGY_BATCH_STATUS_URL: Final[str] = (
    "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk-rp/batchRoomStatusUpdate?type=status"
)
FLIGGY_HOME_URL: Final[str] = "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk/homeV1"
FLIGGY_AGENT_URL: Final[str] = "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk/agent"
FLIGGY_ROOMS_MANAGE_WARMUP_URL: Final[str] = (
    "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk-rp/roomsVsManage"
)
FLIGGY_ROOMS_MANAGE_ROUTE_KEYWORD: Final[str] = "/ebk-rp/roomsvsmanage"
FLIGGY_BATCH_STATUS_ROUTE_KEYWORD: Final[str] = "/ebk-rp/batchroomstatusupdate"
FLIGGY_HOME_ROUTE_KEYWORD: Final[str] = "/ebk/homev1"
FLIGGY_AGENT_ROUTE_KEYWORD: Final[str] = "/ebk/agent"
FLIGGY_AGENT_TEXTAREA_XPATH: Final[str] = "/html/body/div/div/div[3]/div[4]/div/textarea"
FLIGGY_AGENT_SEND_BUTTON_XPATH: Final[str] = "/html/body/div/div/div[3]/div[4]/div/div[2]/button[2]"
FLIGGY_AGENT_CONFIRM_BUTTON_XPATH: Final[str] = (
    "/html/body/div/div/div[2]/div/div/div/div[3]/div[2]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/div[2]/div"
)
FLIGGY_AGENT_GENERATED_CONFIRM_BUTTON_XPATH: Final[str] = (
    "/html/body/div/div/div[2]/div/div/div/div[3]/div[4]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/div[2]/div"
)
FLIGGY_AGENT_CONFIRM_BUTTON_XPATHS: Final[tuple[str, ...]] = (
    FLIGGY_AGENT_CONFIRM_BUTTON_XPATH,
    FLIGGY_AGENT_GENERATED_CONFIRM_BUTTON_XPATH,
)
FLIGGY_AGENT_IFRAME_SELECTOR: Final[str] = "iframe[src*='xbot']"
FLIGGY_AGENT_SEND_XPATH_IN_FRAME: Final[str] = "/html/body/div/div/div[3]/div[4]/div/div/button[2]"
FLIGGY_AGENT_PRE_CONFIRM_XPATH_IN_FRAME: Final[str] = (
    "/html/body/div/div/div[2]/div/div/div/div[3]/div[2]/div/div/div/div/div/div[1]/div/div[2]/div[3]/div/div/div"
)
FLIGGY_AGENT_FINAL_CONFIRM_XPATH_IN_FRAME: Final[str] = (
    "/html/body/div/div/div[2]/div/div/div/div[3]/div[2]/div/div/div/div/div/div[1]/div/div[2]/div[2]/div/div[2]/div"
)
FLIGGY_AGENT_TEXTAREA_SELECTORS: Final[tuple[str, ...]] = (
    "textarea.FullscreenComposer-input",
    "div.FullscreenComposer-inputWrap textarea",
    "textarea[enterkeyhint='send']",
)
FLIGGY_AGENT_INPUT_ACTIVATE_SELECTORS: Final[tuple[str, ...]] = (
    "div.FullscreenComposer-placeholderWrap",
    "div.FullscreenComposer-inputWrap",
    "div.AliCardInputComposer",
)
FLIGGY_AGENT_SEND_SELECTORS: Final[tuple[str, ...]] = (
    "div.FullscreenComposer-actions button",
    "div.FullscreenComposer-actions [role='button']",
    "div.FullscreenComposer-actions > *",
)
FLIGGY_AGENT_CONFIRM_SELECTORS: Final[tuple[str, ...]] = (
    "div.ant-modal-confirm-btns button.ant-btn-primary",
    "div.ant-modal-confirm-btns button:last-child",
    "button.ant-btn.ant-btn-primary",
)
FLIGGY_ROOM_TYPE_XPATHS: Final[dict[str, tuple[str, ...]]] = {
    "度假大床房": (
        "/html/body/div/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[1]/div[2]/div[2]/div/div/div/div/div[2]/table/tbody/tr[2]/td[1]/label/span/input",
    ),
    "豪华双床房": (
        "/html/body/div/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[1]/div[2]/div[2]/div/div/div/div/div[2]/table/tbody/tr[3]/td[1]/label/span/input",
    ),
    "家庭房": (
        "/html/body/div/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[1]/div[2]/div[2]/div/div/div/div/div[2]/table/tbody/tr[4]/td[1]/label/span/input",
        "/html/body/div/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[1]/div[2]/div[2]/div/div/div/div/div[2]/table/tbody/tr[4]/td[1]",
    ),
    "度假双床房": (
        "/html/body/div/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[1]/div[2]/div[2]/div/div/div/div/div[2]/table/tbody/tr[5]/td[1]/label/span/input",
    ),
}
FLIGGY_DATE_START_XPATH: Final[str] = (
    "/html/body/div[1]/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[2]/div[2]/div/div/form/div[1]/div[2]/div/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[1]/input"
)
FLIGGY_DATE_END_XPATH: Final[str] = (
    "/html/body/div[1]/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[2]/div[2]/div/div/form/div[1]/div[2]/div/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[3]/input"
)
FLIGGY_REMAINING_MODE_XPATH: Final[str] = (
    "/html/body/div[1]/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[2]/div[2]/div/div/form/div[4]/div[2]/div/div/div/div[2]/div/div[2]/div[4]/div/label/span[1]/input"
)
FLIGGY_REMAINING_MODE_XPATHS: Final[tuple[str, ...]] = (
    FLIGGY_REMAINING_MODE_XPATH,
    "(//label[.//span[contains(normalize-space(.),'剩余房量')]]//input)[last()]",
)
FLIGGY_REMAINING_INPUT_XPATH: Final[str] = (
    "/html/body/div[1]/section/section/main/div[1]/div/div/div/div/div[1]/div/div/div/div/div[1]/div/div[2]/div/div/div/div/div[2]/div[2]/div/div/form/div[4]/div[2]/div/div/div/div[2]/div/div[2]/div[4]/div/div/div[1]/div/div[2]/input"
)
FLIGGY_REMAINING_INPUT_XPATHS: Final[tuple[str, ...]] = (
    FLIGGY_REMAINING_INPUT_XPATH,
    "(//input[@type='text' and not(@readonly)])[last()]",
)

MEITUAN_BATCH_INVENTORY_URL: Final[str] = "https://me.meituan.com/ebooking/merchant/product/batch-inventory"
MEITUAN_ROOM_TYPE_XPATHS: Final[dict[str, tuple[str, ...]]] = {
    "度假大床房": (
        "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/div/div[1]/div[2]/div/div[2]/div/div[2]/div/div/div/div/div[2]/div/div/div[1]/label/span[1]/input",
    ),
    "度假双床房": (
        "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/div/div[1]/div[2]/div/div[2]/div/div[2]/div/div/div/div/div[2]/div/div/div[2]/label/span[1]/input",
    ),
    "豪华双床房": (
        "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/div/div[1]/div[2]/div/div[2]/div/div[2]/div/div/div/div/div[2]/div/div/div[3]/label/span[1]/input",
    ),
    "家庭房": (
        "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/div/div[1]/div[2]/div/div[2]/div/div[2]/div/div/div/div/div[2]/div/div/div[4]/label/span[1]/input",
    ),
}
MEITUAN_DATE_START_XPATH: Final[str] = (
    "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/div/div[2]/div[2]/div/div[1]/div[2]/div/div/div/div/div/div/div/div/div[2]/div/div/div/div/div/div[1]/div/input"
)
MEITUAN_DATE_END_XPATH: Final[str] = (
    "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/div/div[2]/div[2]/div/div[1]/div[2]/div/div/div/div/div/div/div/div/div[2]/div/div/div/div/div/div[2]/div/input"
)
MEITUAN_REMAINING_MODE_XPATH: Final[str] = (
    "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/div/div[2]/div[2]/div/div[3]/div[2]/div[2]/div/div/div[2]/div[2]/div/label[2]/span[1]/input"
)
MEITUAN_REMAINING_INPUT_XPATH: Final[str] = (
    "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[1]/div/div[2]/div[2]/div/div[3]/div[2]/div[2]/div/div/div[2]/div[2]/div/label[2]/span[2]/div/div/div[1]/div/input"
)
MEITUAN_SUBMIT_XPATHS: Final[tuple[str, ...]] = (
    "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[2]/span[2]/button[2]",
    "/html/body/div[2]/div[3]/div/div[1]/div/div/div/div[2]/span[2]/button[2]/span",
)
MEITUAN_SUCCESS_XPATHS: Final[tuple[str, ...]] = (
    "/html/body/div[83]/div/div/div/span",
    "(//span[contains(normalize-space(.), '修改提交成功')])[last()]",
)


@dataclass(frozen=True)
class CtripQuantityUpdate:
    room_type: str
    check_in_date: str
    check_out_date: str
    remaining_quantity: int


@dataclass(frozen=True)
class FliggyQuantityUpdate:
    room_type: str
    check_in_date: str
    check_out_date: str
    remaining_quantity: int


@dataclass(frozen=True)
class MeituanQuantityUpdate:
    room_type: str
    check_in_date: str
    check_out_date: str
    remaining_quantity: int


class _SyncSessionBase:
    def __init__(
        self,
        *,
        headless: bool,
        slow_mo: int,
        timeout_ms: int,
        profile_dir: Path,
        cdp_endpoints: tuple[str, ...],
        timing_envs: tuple[str, ...],
        require_existing_browser: bool = False,
        page_url_keywords: tuple[str, ...] = (),
    ):
        self._headless = headless
        self._slow_mo = slow_mo
        self._timeout_ms = timeout_ms
        self._profile_dir = profile_dir
        self._cdp_endpoints = tuple(item for item in cdp_endpoints if str(item).strip())
        self._require_existing_browser = bool(require_existing_browser)
        self._page_url_keywords = tuple(
            str(item).strip().lower() for item in page_url_keywords if str(item).strip()
        )

        self._timing_factor = 0.5
        for env_name in timing_envs:
            raw = os.getenv(env_name)
            if raw is None:
                continue
            try:
                self._timing_factor = max(0.25, min(8.0, float(raw)))
                break
            except ValueError:
                continue

        self._playwright_manager = None
        self._playwright = None
        self._cdp_browser = None
        self._reused_external_browser = False
        self._keep_browser_open = False
        self._owns_page = False
        self._context = None
        self._page = None

    def _scaled_delay(self, base_ms: int) -> int:
        return int(max(0, round(base_ms * self._timing_factor)))

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        SESSION_ROOT.mkdir(parents=True, exist_ok=True)
        self._profile_dir.mkdir(parents=True, exist_ok=True)

        self._playwright_manager = sync_playwright()
        self._playwright = self._playwright_manager.start()

        if self._try_attach_existing_login_browser():
            self._prepare_page_for_reused_browser()
            self._page.set_default_timeout(self._timeout_ms)
            return self

        if self._require_existing_browser:
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            self._playwright_manager = None
            self._playwright = None
            raise RuntimeError("未检测到可复用的登录浏览器，请先点击跳转打开平台页面")

        preferred_channel = os.getenv(
            "SYNC_BROWSER_CHANNEL",
            os.getenv("LOGIN_BROWSER_CHANNEL", "msedge"),
        ).strip().lower()
        launch_kwargs = {
            "user_data_dir": str(self._profile_dir),
            "headless": self._headless,
            "no_viewport": True,
            "slow_mo": self._slow_mo,
            "args": ["--start-maximized", "--disable-extensions"],
        }

        try:
            if preferred_channel:
                try:
                    self._context = self._playwright.chromium.launch_persistent_context(
                        channel=preferred_channel,
                        **launch_kwargs,
                    )
                except Exception:
                    self._context = self._playwright.chromium.launch_persistent_context(
                        **launch_kwargs,
                    )
            else:
                self._context = self._playwright.chromium.launch_persistent_context(
                    **launch_kwargs,
                )
        except Exception:
            if self._headless and self._try_attach_existing_login_browser():
                self._prepare_page_for_reused_browser()
                self._page.set_default_timeout(self._timeout_ms)
                return self
            raise

        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._owns_page = True
        self._page.set_default_timeout(self._timeout_ms)
        return self

    @staticmethod
    def _is_local_page_url(raw_url: str) -> bool:
        url = str(raw_url or "").lower()
        return ("127.0.0.1:" in url) or ("localhost:" in url)

    def _is_target_platform_page_url(self, raw_url: str) -> bool:
        url = str(raw_url or "").lower()
        if not self._page_url_keywords:
            return False
        return any(keyword in url for keyword in self._page_url_keywords)

    def _prepare_page_for_reused_browser(self) -> None:
        if not self._reused_external_browser or self._context is None:
            return

        pages = [item for item in self._context.pages if not item.is_closed()]

        # Reuse an existing target-platform tab first to prevent endless tab growth.
        for page in pages:
            page_url = str(page.url or "")
            if self._is_local_page_url(page_url):
                continue
            if self._is_target_platform_page_url(page_url):
                self._page = page
                self._owns_page = False
                return

        # Target tab missing: create a new dedicated tab to avoid overwriting other platform tabs.
        try:
            self._page = self._context.new_page()
            # Keep this tab after run so next focus/retry can reuse it.
            self._owns_page = False
            return
        except Exception:
            # Last fallback: reuse any non-local tab only when tab creation fails.
            for page in pages:
                if not self._is_local_page_url(str(page.url or "")):
                    self._page = page
                    self._owns_page = False
                    return

            if pages:
                self._page = pages[0]
                self._owns_page = False

    def _try_attach_existing_login_browser(self) -> bool:
        if self._playwright is None:
            return False

        fallback_browser = None
        fallback_context = None

        for endpoint in self._cdp_endpoints:
            try:
                browser = self._playwright.chromium.connect_over_cdp(
                    endpoint,
                    timeout=min(self._timeout_ms, 4000),
                )
            except Exception:
                continue

            contexts = list(browser.contexts)
            if not contexts:
                try:
                    browser.close()
                except Exception:
                    pass
                continue

            context = contexts[0]
            pages = [item for item in context.pages if not item.is_closed()]
            has_target_page = any(
                self._is_target_platform_page_url(str(item.url or ""))
                for item in pages
            )

            if has_target_page:
                if fallback_browser is not None:
                    try:
                        fallback_browser.close()
                    except Exception:
                        pass

                self._cdp_browser = browser
                self._context = context
                self._page = pages[0] if pages else self._context.new_page()
                self._reused_external_browser = True
                return True

            if fallback_browser is None:
                fallback_browser = browser
                fallback_context = context
                continue

            try:
                browser.close()
            except Exception:
                pass

        if fallback_browser is not None and fallback_context is not None:
            self._cdp_browser = fallback_browser
            self._context = fallback_context
            pages = [item for item in self._context.pages if not item.is_closed()]
            self._page = pages[0] if pages else self._context.new_page()
            self._reused_external_browser = True
            return True

        return False

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._keep_browser_open:
            _KEEP_ALIVE_BROWSER_HANDLES.append(
                (self._playwright_manager, self._cdp_browser, self._context)
            )
            if len(_KEEP_ALIVE_BROWSER_HANDLES) > _MAX_KEEP_ALIVE_BROWSER_HANDLES:
                del _KEEP_ALIVE_BROWSER_HANDLES[:-_MAX_KEEP_ALIVE_BROWSER_HANDLES]

            self._playwright_manager = None
            self._playwright = None
            self._cdp_browser = None
            self._context = None
            self._page = None
            return

        if self._reused_external_browser and self._owns_page and self._page is not None:
            try:
                if not self._page.is_closed():
                    self._page.close()
            except Exception:
                pass

        if self._context is not None and not self._reused_external_browser and not self._keep_browser_open:
            try:
                self._context.close()
            except Exception:
                pass

        if self._cdp_browser is not None:
            try:
                self._cdp_browser.close()
            except Exception:
                pass

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass

        self._playwright_manager = None
        self._playwright = None
        self._cdp_browser = None
        self._context = None
        self._page = None

    def keep_browser_open(self) -> None:
        self._keep_browser_open = True

    def _ensure_ready(self) -> None:
        if self._page is None:
            raise RuntimeError("同步会话未初始化")

    def _list_open_pages(self):
        if self._context is None:
            return []
        return [item for item in self._context.pages if not item.is_closed()]

    def _find_local_management_page(self):
        for page in self._list_open_pages():
            if page is self._page:
                continue
            if self._is_local_page_url(str(page.url or "")):
                return page
        return None

    @staticmethod
    def _bring_page_to_front(page) -> None:
        if page is None:
            return
        try:
            if not page.is_closed():
                page.bring_to_front()
        except Exception:
            pass

    def _before_set_date_input(self) -> None:
        # Platforms can override this hook for special date widget preparation.
        return

    def _click_xpath(self, xpath: str, action_name: str, *, timeout_ms: int | None = None) -> None:
        self._ensure_ready()
        click_timeout = timeout_ms if timeout_ms is not None else self._timeout_ms
        locator = self._page.locator(f"xpath={xpath}").first
        locator.wait_for(state="visible", timeout=click_timeout)
        locator.scroll_into_view_if_needed(timeout=click_timeout)

        last_error: Exception | None = None
        for force in (False, True):
            try:
                locator.click(timeout=click_timeout, force=force)
                return
            except Exception as exc:
                last_error = exc

        try:
            locator.evaluate("(el) => el.click()")
            return
        except Exception as exc:
            last_error = exc

        raise RuntimeError(f"{action_name}失败，请稍后重试") from last_error

    def _click_any_xpath(
        self,
        xpaths: tuple[str, ...],
        action_name: str,
        *,
        timeout_ms: int | None = None,
    ) -> None:
        self._ensure_ready()
        last_error: Exception | None = None
        for xpath in xpaths:
            try:
                self._click_xpath(xpath, action_name, timeout_ms=timeout_ms)
                return
            except Exception as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise RuntimeError(f"{action_name}失败，请检查页面结构是否变化") from last_error
        raise RuntimeError(f"{action_name}失败，未提供可用选择器")

    def _wait_xpath_visible(self, xpath: str, field_name: str, *, timeout_ms: int | None = None):
        self._ensure_ready()
        wait_timeout = timeout_ms if timeout_ms is not None else self._timeout_ms
        locator = self._page.locator(f"xpath={xpath}").first
        locator.wait_for(state="visible", timeout=wait_timeout)
        return locator

    def _wait_any_xpath_visible(
        self,
        xpaths: tuple[str, ...],
        field_name: str,
        *,
        timeout_ms: int | None = None,
    ):
        if not xpaths:
            raise RuntimeError(f"{field_name}未提供可用选择器")

        wait_timeout = timeout_ms if timeout_ms is not None else self._timeout_ms
        each_timeout = max(600, int(wait_timeout / max(1, len(xpaths))))

        last_error: Exception | None = None
        for xpath in xpaths:
            try:
                return self._wait_xpath_visible(xpath, field_name, timeout_ms=each_timeout)
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(f"{field_name}未出现，请检查页面结构是否变化") from last_error

    def _wait_xpath_enabled(self, xpath: str, field_name: str, *, timeout_ms: int | None = None):
        locator = self._wait_xpath_visible(xpath, field_name, timeout_ms=timeout_ms)
        wait_timeout = timeout_ms if timeout_ms is not None else self._timeout_ms
        deadline = time.time() + max(0.2, wait_timeout / 1000)

        while time.time() < deadline:
            try:
                if locator.is_enabled():
                    return locator
            except Exception:
                pass
            self._page.wait_for_timeout(self._scaled_delay(100))

        if field_name == "提交按钮":
            raise RuntimeError("提交按钮未就绪，可能前置字段尚未全部生效，请稍后重试")
        raise RuntimeError(f"{field_name}未就绪，请稍后重试")

    def _read_locator_value(self, locator) -> str:
        try:
            return str(locator.input_value(timeout=self._timeout_ms)).strip()
        except Exception:
            pass

        try:
            return str(locator.evaluate("(el) => String(el.value ?? '').trim()") or "").strip()
        except Exception:
            return ""

    def _read_locator_display_text(self, locator) -> str:
        parts: list[str] = []

        value = self._read_locator_value(locator)
        if value:
            parts.append(value)

        for attr in ("title", "value", "data-value"):
            try:
                attr_value = str(locator.get_attribute(attr, timeout=self._timeout_ms) or "").strip()
            except Exception:
                attr_value = ""
            if attr_value:
                parts.append(attr_value)

        return " | ".join(parts)

    def _wait_locator_value(self, locator, expected: str, *, wait_ms: int | None = None) -> bool:
        self._ensure_ready()

        expected_text = str(expected).strip()
        timeout_ms = wait_ms if wait_ms is not None else self._scaled_delay(1800)
        deadline = time.time() + max(0.2, timeout_ms / 1000)

        while time.time() < deadline:
            if self._read_locator_value(locator) == expected_text:
                return True
            self._page.wait_for_timeout(self._scaled_delay(120))
        return False

    def _fill_xpath(
        self,
        xpath: str,
        value: str,
        field_name: str,
        *,
        press_enter: bool = False,
    ) -> None:
        self._ensure_ready()
        locator = self._page.locator(f"xpath={xpath}").first
        locator.wait_for(state="visible", timeout=self._timeout_ms)
        locator.click(timeout=self._timeout_ms)

        text = str(value)

        try:
            locator.press("Control+A")
            locator.press("Delete")
        except Exception:
            self._page.keyboard.press("Control+A")
            self._page.keyboard.press("Delete")

        try:
            locator.type(text, delay=max(10, int(45 * self._timing_factor)))
        except Exception:
            self._page.keyboard.type(text, delay=max(10, int(45 * self._timing_factor)))

        if not self._wait_locator_value(locator, text):
            locator.evaluate(
                """
                (el, v) => {
                  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                  if (nativeSetter) {
                    nativeSetter.call(el, v);
                  } else {
                    el.value = v;
                  }
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                  el.dispatchEvent(new Event('blur', { bubbles: true }));
                }
                """,
                text,
            )
            if not self._wait_locator_value(locator, text, wait_ms=self._scaled_delay(1200)):
                current = self._read_locator_display_text(locator)
                raise RuntimeError(f"{field_name}填写失败，当前值为: {current or '空'}")

        if press_enter:
            try:
                locator.press("Enter")
            except Exception:
                self._page.keyboard.press("Enter")

    def _set_xpath_value_direct(self, xpath: str, value: str, field_name: str) -> None:
        self._before_set_date_input()
        locator = self._wait_xpath_visible(xpath, field_name)
        text = str(value)

        try:
            locator.evaluate(
                """
                (el) => {
                  el.removeAttribute('readonly');
                  el.removeAttribute('disabled');
                  el.style.display = 'block';
                  el.style.visibility = 'visible';
                  el.style.opacity = '1';
                }
                """
            )
        except Exception:
            pass

        try:
            locator.click(timeout=self._timeout_ms, force=True)
        except Exception:
            pass

        try:
            locator.press("Control+A")
            locator.press("Delete")
            locator.type(text, delay=max(10, int(45 * self._timing_factor)))
            locator.press("Enter")
        except Exception:
            self._page.keyboard.press("Control+A")
            self._page.keyboard.press("Delete")
            self._page.keyboard.type(text, delay=max(10, int(45 * self._timing_factor)))
            self._page.keyboard.press("Enter")

        locator.evaluate(
            """
            (el, v) => {
              const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
              const currentVal = String(el.value ?? '').trim();
              if (currentVal !== String(v).trim()) {
                if (nativeSetter) {
                  nativeSetter.call(el, v);
                } else {
                  el.value = v;
                }
                if (el.hasAttribute('title')) {
                  el.setAttribute('title', v);
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
              }
              el.dispatchEvent(new Event('blur', { bubbles: true }));
            }
            """,
            text,
        )

        if not self._wait_locator_value(locator, text, wait_ms=max(self._scaled_delay(1800), 1800)):
            current = self._read_locator_display_text(locator)
            raise RuntimeError(f"{field_name}填写失败，当前值为: {current or '空'}")

    @staticmethod
    def _date_match_tokens(date_iso: str) -> tuple[str, ...]:
        dt = date.fromisoformat(str(date_iso))
        return (
            f"{dt.year}年{dt.month}月{dt.day}日",
            f"{dt.year}-{dt.month:02d}-{dt.day:02d}",
            f"{dt.year}-{dt.month}-{dt.day}",
            f"{dt.year}/{dt.month:02d}/{dt.day:02d}",
            f"{dt.year}/{dt.month}/{dt.day}",
        )

    def _wait_date_xpath_applied(
        self,
        xpath: str,
        expected_date_iso: str,
        field_name: str,
        *,
        timeout_ms: int | None = None,
    ) -> None:
        locator = self._wait_xpath_visible(xpath, field_name, timeout_ms=timeout_ms)
        wait_timeout = timeout_ms if timeout_ms is not None else max(self._scaled_delay(2500), 2500)
        deadline = time.time() + max(0.2, wait_timeout / 1000)
        tokens = self._date_match_tokens(expected_date_iso)

        while time.time() < deadline:
            display_text = self._read_locator_display_text(locator)
            if any(token in display_text for token in tokens):
                return
            self._page.wait_for_timeout(self._scaled_delay(120))

        current_text = self._read_locator_display_text(locator)
        raise RuntimeError(f"{field_name}未生效，当前值为: {current_text or '空'}")


class CtripSyncSession(_SyncSessionBase):
    def __init__(
        self,
        *,
        headless: bool = False,
        slow_mo: int = 0,
        timeout_ms: int = 36000,
        require_existing_browser: bool = False,
    ):
        cdp_primary = os.getenv("SYNC_BROWSER_CDP_ENDPOINT", f"http://127.0.0.1:{SYNC_BROWSER_CDP_PORT}")
        super().__init__(
            headless=headless,
            slow_mo=slow_mo,
            timeout_ms=timeout_ms,
            profile_dir=CTRIP_PROFILE_DIR,
            cdp_endpoints=(cdp_primary,),
            timing_envs=("CTRIP_TIMING_FACTOR",),
            require_existing_browser=require_existing_browser,
            page_url_keywords=("ebooking.trip.com",),
        )
        self._rateplan_opened = False

    def _before_set_date_input(self) -> None:
        self._ensure_ready()
        self._page.evaluate(
            """
            () => {
              const styleId = 'sync-ctrip-date-force-visible';
              if (!document.getElementById(styleId)) {
                const styleSheet = document.createElement('style');
                styleSheet.id = styleId;
                styleSheet.type = 'text/css';
                styleSheet.innerText = '.assist-block-dom, .assist-flex-dom, .assist-ib-dom { display: block !important; visibility: visible !important; opacity: 1 !important; }';
                document.head.appendChild(styleSheet);
              }
            }
            """
        )

    def _wait_rateplan_page_ready(self) -> None:
        first_room_type_xpath = next(iter(CTRIP_ROOM_TYPE_XPATHS.values()))
        self._wait_xpath_visible(first_room_type_xpath, "房型列表")
        self._wait_xpath_visible(CTRIP_DATE_START_XPATH, "起始日期输入框")
        self._wait_xpath_visible(CTRIP_DATE_END_XPATH, "终止日期输入框")

    def _open_ctrip_room_status_page(self) -> None:
        self._ensure_ready()
        self._bring_page_to_front(self._page)
        self._page.goto(CTRIP_RATEPLAN_URL, wait_until="domcontentloaded")

        if "login" in str(self._page.url or "").lower():
            raise RuntimeError("携程会话未登录，请先在登录引导页完成携程登录")

        self._wait_rateplan_page_ready()
        self._rateplan_opened = True

    def open_rateplan_page(self) -> None:
        self._bring_page_to_front(self._page)
        self._open_ctrip_room_status_page()

    def _scroll_to_ctrip_date_section(self) -> None:
        self._ensure_ready()
        scroll_timeout = max(self._scaled_delay(5000), 5000)
        settle_timeout = max(self._scaled_delay(1000), 1000)

        anchors = (
            self._page.get_by_text("设置房态", exact=True).first,
            self._page.get_by_text("选择日期", exact=True).first,
            self._page.locator("text=选择日期").first,
        )

        for anchor in anchors:
            try:
                anchor.wait_for(state="visible", timeout=scroll_timeout)
                anchor.scroll_into_view_if_needed(timeout=scroll_timeout)
                self._page.wait_for_timeout(settle_timeout)
                return
            except Exception:
                continue

        # Fallback: nudge page scroll to help lazy-rendered calendar widgets appear.
        try:
            self._page.mouse.wheel(0, 900)
            self._page.wait_for_timeout(max(self._scaled_delay(700), 700))
        except Exception:
            pass

    @staticmethod
    def _build_ctrip_date_range(check_in_date: str, check_out_date: str) -> tuple[str, str]:
        check_in = date.fromisoformat(str(check_in_date))
        check_out = date.fromisoformat(str(check_out_date))
        if check_out <= check_in:
            raise ValueError("离店日期必须晚于到店日期")
        return check_in.isoformat(), (check_out - timedelta(days=1)).isoformat()

    @staticmethod
    def _format_ctrip_date_text(date_iso: str) -> str:
        dt = date.fromisoformat(str(date_iso))
        return f"{dt.year}年{dt.month}月{dt.day}日"

    @staticmethod
    def _format_ctrip_month_text(date_iso: str) -> str:
        dt = date.fromisoformat(str(date_iso))
        return f"{dt.month}月"

    def _try_switch_ctrip_calendar_month(self, active_dropdown, target_date_iso: str) -> None:
        self._ensure_ready()
        target_month_text = self._format_ctrip_month_text(target_date_iso)
        month_timeout = max(self._scaled_delay(4000), 4000)

        month_selector = active_dropdown.locator(".he-trip-kit-ui-select-selection-item").filter(
            has_text="月"
        ).first

        try:
            month_selector.wait_for(state="visible", timeout=month_timeout)
        except Exception:
            return

        try:
            current_month_text = str(month_selector.inner_text(timeout=month_timeout) or "").strip()
        except Exception:
            current_month_text = ""

        if target_month_text and target_month_text in current_month_text:
            return

        try:
            month_selector.click(timeout=month_timeout, force=True)
            self._page.wait_for_timeout(max(self._scaled_delay(500), 500))
        except Exception:
            return

        option_candidates = (
            self._page.locator(".he-trip-kit-ui-select-item-option-content", has_text=target_month_text).first,
            self._page.get_by_text(target_month_text, exact=True).first,
        )

        for option in option_candidates:
            try:
                option.wait_for(state="visible", timeout=month_timeout)
                option.click(timeout=month_timeout, force=True)
                self._page.wait_for_timeout(max(self._scaled_delay(700), 700))
                return
            except Exception:
                continue

    def _pick_ctrip_date_by_visible_dropdown(self, picker_index: int, target_date_iso: str) -> None:
        self._ensure_ready()

        picker_wrapper = self._page.locator(".he-trip-kit-ui-picker").nth(picker_index)
        picker_wrapper.wait_for(state="visible", timeout=max(self._scaled_delay(12000), 12000))
        picker_input = picker_wrapper.locator("input").first
        picker_input.wait_for(state="visible", timeout=max(self._scaled_delay(5000), 5000))

        # 先确保外层 wrapper 进入 focused 状态（蓝色边框），再进行日期点击。
        focused_class = "he-trip-kit-ui-picker-focused"
        for _ in range(5):
            try:
                picker_wrapper.click(timeout=max(self._scaled_delay(5000), 5000), force=True)
            except Exception:
                try:
                    picker_input.click(timeout=max(self._scaled_delay(5000), 5000), force=True)
                except Exception:
                    pass

            self._page.wait_for_timeout(max(self._scaled_delay(400), 400))
            try:
                wrapper_class = str(picker_wrapper.get_attribute("class") or "")
            except Exception:
                wrapper_class = ""

            if focused_class in wrapper_class:
                break

        active_dropdown = self._page.locator(
            ".he-trip-kit-ui-picker-dropdown:not(.he-trip-kit-ui-picker-dropdown-hidden)"
        ).last
        try:
            active_dropdown.wait_for(state="visible", timeout=max(self._scaled_delay(5000), 5000))
        except Exception:
            try:
                picker_input.click(timeout=max(self._scaled_delay(5000), 5000), force=True)
            except Exception:
                pass
            active_dropdown.wait_for(state="visible", timeout=max(self._scaled_delay(5000), 5000))

        # Cross-month scenarios need explicit month switch before day selection.
        self._try_switch_ctrip_calendar_month(active_dropdown, target_date_iso)

        target_cell = active_dropdown.locator(f"td[title='{target_date_iso}']").first
        try:
            target_cell.wait_for(state="visible", timeout=max(self._scaled_delay(4000), 4000))
            target_cell.dispatch_event("click")
            return
        except Exception:
            pass

        day_text = str(int(target_date_iso[-2:]))
        fallback_cell = active_dropdown.locator(".he-trip-kit-ui-picker-cell-inner").get_by_text(
            day_text,
            exact=True,
        ).first
        fallback_cell.wait_for(state="visible", timeout=max(self._scaled_delay(4000), 4000))
        fallback_cell.click(timeout=max(self._scaled_delay(5000), 5000), force=True)

    def _pick_ctrip_date_range_by_calendar(self, start_date: str, end_date: str) -> None:
        self._pick_ctrip_date_by_visible_dropdown(0, start_date)
        self._page.wait_for_timeout(max(self._scaled_delay(400), 400))
        self._pick_ctrip_date_by_visible_dropdown(1, end_date)

    def _any_selector_visible(self, selectors: tuple[str, ...], *, timeout_ms: int = 250) -> bool:
        self._ensure_ready()
        for selector in selectors:
            try:
                if self._page.locator(selector).first.is_visible(timeout=timeout_ms):
                    return True
            except Exception:
                continue
        return False

    def _wait_submit_done_popup(self, on_success=None) -> dict[str, str | bool]:
        self._ensure_ready()
        wait_timeout_ms = max(self._timeout_ms, self._scaled_delay(7000))
        deadline = time.time() + (wait_timeout_ms / 1000)

        success_title_selector = f"xpath={CTRIP_SUBMIT_SUCCESS_TITLE_XPATH}"
        success_popup_selector = f"xpath={CTRIP_SUBMIT_DONE_POPUP_XPATH}"

        def trigger_success_hook() -> None:
            if callable(on_success):
                try:
                    on_success()
                except Exception:
                    pass

        while time.time() < deadline:
            # Highest priority: explicit success modal title XPath.
            try:
                if self._page.locator(success_title_selector).first.is_visible(timeout=self._scaled_delay(150)):
                    trigger_success_hook()
                    self._page.wait_for_timeout(self._scaled_delay(200))
                    return {
                        "confirmed": True,
                        "confirmation": "success-title-xpath",
                    }
            except Exception:
                pass

            try:
                if self._page.locator(success_popup_selector).first.is_visible(timeout=self._scaled_delay(120)):
                    trigger_success_hook()
                    self._page.wait_for_timeout(self._scaled_delay(200))
                    return {
                        "confirmed": True,
                        "confirmation": "success-popup-xpath",
                    }
            except Exception:
                pass

            if self._any_selector_visible(CTRIP_SUBMIT_SUCCESS_SELECTORS, timeout_ms=self._scaled_delay(220)):
                trigger_success_hook()
                self._page.wait_for_timeout(self._scaled_delay(250))
                return {
                    "confirmed": True,
                    "confirmation": "success-toast",
                }

            if self._any_selector_visible(CTRIP_SUBMIT_FAILURE_SELECTORS, timeout_ms=self._scaled_delay(180)):
                raise RuntimeError("携程页面提示提交失败，请人工核对后重试")

            self._page.wait_for_timeout(self._scaled_delay(150))

        if self._any_selector_visible(CTRIP_SUBMIT_FAILURE_SELECTORS, timeout_ms=self._scaled_delay(220)):
            raise RuntimeError("携程页面提示提交失败，请人工核对后重试")

        self._page.wait_for_timeout(self._scaled_delay(250))
        return {
            "confirmed": False,
            "confirmation": "uncertain-no-toast",
            "warning": "未稳定捕获完成弹窗，按已提交处理",
        }

    def _settle_after_submit(self, wait_ms: int = 2000) -> None:
        self._ensure_ready()
        self._page.wait_for_timeout(max(self._scaled_delay(wait_ms), wait_ms))

    def _finish_submit_without_long_wait(self) -> dict[str, str | bool]:
        self._settle_after_submit(2000)
        if self._any_selector_visible(CTRIP_SUBMIT_FAILURE_SELECTORS, timeout_ms=self._scaled_delay(250)):
            raise RuntimeError("携程页面提示提交失败，请人工核对后重试")
        return {
            "confirmed": False,
            "confirmation": "submitted-short-wait",
            "warning": "已提交，未长时间等待成功提示",
        }

    def update_room_quantity(
        self,
        update: CtripQuantityUpdate,
        *,
        open_page: bool = True,
        apply_date: bool = True,
        auto_submit: bool = True,
        restore_management_tab: bool = True,
    ) -> dict[str, str | int | bool]:
        if update.room_type not in CTRIP_ROOM_TYPE_XPATHS:
            supported = ", ".join(CTRIP_ROOM_TYPE_XPATHS.keys())
            raise ValueError(f"携程暂不支持该房型: {update.room_type}，支持: {supported}")

        if int(update.remaining_quantity) < 0:
            raise ValueError("剩余房量不能小于 0")

        range_start, range_end = self._build_ctrip_date_range(
            update.check_in_date,
            update.check_out_date,
        )

        should_restore_management_tab = bool(auto_submit and restore_management_tab)
        management_page = self._find_local_management_page() if should_restore_management_tab else None

        self._bring_page_to_front(self._page)
        try:
            if open_page or not self._rateplan_opened:
                self._open_ctrip_room_status_page()

            self._bring_page_to_front(self._page)
            self._click_xpath(CTRIP_ROOM_TYPE_XPATHS[update.room_type], "选择房型")

            if apply_date:
                self._scroll_to_ctrip_date_section()
                try:
                    self._pick_ctrip_date_range_by_calendar(range_start, range_end)
                except Exception:
                    self._wait_xpath_visible(CTRIP_DATE_START_XPATH, "起始日期输入框")
                    self._set_xpath_value_direct(
                        CTRIP_DATE_START_XPATH,
                        self._format_ctrip_date_text(range_start),
                        "起始日期",
                    )
                    self._wait_xpath_visible(CTRIP_DATE_END_XPATH, "终止日期输入框")
                    self._set_xpath_value_direct(
                        CTRIP_DATE_END_XPATH,
                        self._format_ctrip_date_text(range_end),
                        "终止日期",
                    )
                    try:
                        self._page.keyboard.press("Escape")
                    except Exception:
                        pass
                self._wait_date_xpath_applied(CTRIP_DATE_START_XPATH, range_start, "起始日期")
                self._wait_date_xpath_applied(CTRIP_DATE_END_XPATH, range_end, "终止日期")

            self._wait_xpath_enabled(CTRIP_REMAINING_MODE_XPATH, "剩余房量模式")
            self._click_xpath(CTRIP_REMAINING_MODE_XPATH, "切换剩余房量模式")
            self._wait_xpath_enabled(CTRIP_REMAINING_INPUT_XPATH, "剩余房量输入框")
            self._fill_xpath(
                CTRIP_REMAINING_INPUT_XPATH,
                str(int(update.remaining_quantity)),
                "剩余房量",
                press_enter=False,
            )

            submit_result: dict[str, str | bool]
            if auto_submit:
                self._wait_xpath_enabled(CTRIP_SUBMIT_XPATH, "提交按钮")
                self._click_xpath(CTRIP_SUBMIT_XPATH, "提交")
                submit_result = self._finish_submit_without_long_wait()
            else:
                submit_result = {
                    "confirmed": False,
                    "confirmation": "manual-pending",
                    "warning": "已预填非日期项，请手动设置日期并提交",
                }

            return {
                "roomType": update.room_type,
                "startDate": range_start,
                "endDate": range_end,
                "remainingQuantity": int(update.remaining_quantity),
                "submitConfirmed": bool(submit_result.get("confirmed", False)),
                "submitConfirmation": str(submit_result.get("confirmation") or "unknown"),
                "submitWarning": str(submit_result.get("warning") or ""),
            }
        finally:
            if (
                should_restore_management_tab
                and management_page is not None
                and management_page is not self._page
            ):
                self._bring_page_to_front(management_page)


class FliggySyncSession(_SyncSessionBase):
    def __init__(self, *, headless: bool = False, slow_mo: int = 0, timeout_ms: int = 36000):
        cdp_primary = os.getenv(
            "FLIGGY_SYNC_BROWSER_CDP_ENDPOINT",
            f"http://127.0.0.1:{FLIGGY_SYNC_BROWSER_CDP_PORT}",
        )
        cdp_fallback = os.getenv("SYNC_BROWSER_CDP_ENDPOINT", f"http://127.0.0.1:{SYNC_BROWSER_CDP_PORT}")
        super().__init__(
            headless=headless,
            slow_mo=slow_mo,
            timeout_ms=timeout_ms,
            profile_dir=FLIGGY_PROFILE_DIR,
            cdp_endpoints=(cdp_fallback, cdp_primary),
            timing_envs=("FLIGGY_TIMING_FACTOR", "CTRIP_TIMING_FACTOR"),
            require_existing_browser=headless,
            page_url_keywords=("hotel.fliggy.com",),
        )
        self._batch_page_opened = False

    def _wait_batch_page_ready(self) -> None:
        self._get_fliggy_agent_frame()

    def _get_fliggy_agent_frame(self):
        self._ensure_ready()
        frame = self._page.frame_locator(FLIGGY_AGENT_IFRAME_SELECTOR).first
        textarea = frame.locator("textarea.FullscreenComposer-input").last
        textarea.wait_for(state="attached", timeout=max(self._scaled_delay(15000), 15000))
        return frame

    def _fill_fliggy_agent_textarea_via_frame(self, ai_frame, text: str) -> None:
        self._ensure_ready()
        expected = str(text)
        textarea = ai_frame.locator("textarea.FullscreenComposer-input").last
        textarea.wait_for(state="attached", timeout=max(self._scaled_delay(15000), 15000))

        deadline = time.time() + (max(self._scaled_delay(14000), 14000) / 1000)
        last_error: Exception | None = None

        while time.time() < deadline:
            try:
                # This input is refreshed frequently; always click to activate before injection.
                textarea.click(timeout=max(self._scaled_delay(2000), 2000), force=True)
                textarea.evaluate(
                    """
                    (el, text) => {
                      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
                      if (nativeSetter) {
                        nativeSetter.call(el, text);
                      } else {
                        el.value = text;
                      }
                      el.dispatchEvent(new Event('input', { bubbles: true }));
                      el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    """,
                    expected,
                )

                current = str(textarea.input_value(timeout=max(self._scaled_delay(1500), 1500)) or "")
                if current == expected:
                    # Cross one refresh cycle and verify text still exists.
                    self._page.wait_for_timeout(max(self._scaled_delay(1200), 1200))
                    stable = str(textarea.input_value(timeout=max(self._scaled_delay(1500), 1500)) or "")
                    if stable == expected:
                        return
            except Exception as exc:
                last_error = exc

            self._page.wait_for_timeout(max(self._scaled_delay(260), 260))

        raise RuntimeError("飞猪AI输入框填写失败，请稍后重试") from last_error

    def _click_fliggy_agent_send_via_frame(self, ai_frame) -> None:
        self._ensure_ready()
        last_error: Exception | None = None

        try:
            send_btn = ai_frame.locator(f"xpath={FLIGGY_AGENT_SEND_XPATH_IN_FRAME}").first
            send_btn.wait_for(state="visible", timeout=max(self._scaled_delay(12000), 12000))
            send_btn.click(timeout=max(self._scaled_delay(3000), 3000), force=True)
            return
        except Exception as exc:
            last_error = exc

        for selector in FLIGGY_AGENT_SEND_SELECTORS:
            try:
                locator = ai_frame.locator(selector).last
                locator.wait_for(state="visible", timeout=max(self._scaled_delay(2500), 2500))
                locator.click(timeout=max(self._scaled_delay(2500), 2500), force=True)
                return
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError("飞猪AI发送按钮点击失败，请检查页面结构是否变化") from last_error

    def _click_fliggy_confirm_xpath_in_frame(self, ai_frame, xpath: str, *, timeout_ms: int = 1200) -> bool:
        self._ensure_ready()
        try:
            locator = ai_frame.locator(f"xpath={xpath}").first
            locator.wait_for(state="visible", timeout=timeout_ms)
            try:
                locator.scroll_into_view_if_needed(timeout=timeout_ms)
            except Exception:
                pass
            locator.click(timeout=timeout_ms, force=True)
            return True
        except Exception:
            return False

    def _click_latest_fliggy_confirm_in_frame(self, ai_frame, *, timeout_ms: int = 3000) -> bool:
        self._ensure_ready()

        try:
            locator = ai_frame.locator(
                "div[class*='Message left'] "
                "div[class*='bottom-btn'], "
                "div[class*='Message left'] div:has(> div.RichText:text-is('【确认】')), "
                "div[class*='Message left'] div:has(> div.RichText:text-is('确认')), "
                "div[class*='Message left'] div[class*='btn']"
            ).filter(has_text="确认").last
            locator.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            return False

        try:
            locator.scroll_into_view_if_needed(timeout=timeout_ms)
        except Exception:
            pass

        try:
            locator.click(timeout=timeout_ms, force=True)
            return True
        except Exception:
            return False

    def _run_fliggy_agent_confirm_rounds(self, ai_frame, *, max_rounds: int = 3) -> int:
        self._ensure_ready()
        rounds_clicked = 0

        for _ in range(max(1, int(max_rounds))):
            # Give AI enough time for response rendering.
            self._page.wait_for_timeout(max(self._scaled_delay(3500), 3500))

            clicked_any = False

            # Optional intermediate confirm may appear before the final confirm.
            if self._click_fliggy_confirm_xpath_in_frame(
                ai_frame,
                FLIGGY_AGENT_PRE_CONFIRM_XPATH_IN_FRAME,
                timeout_ms=max(self._scaled_delay(1500), 1500),
            ):
                clicked_any = True
                self._page.wait_for_timeout(max(self._scaled_delay(6000), 6000))

            if self._click_latest_fliggy_confirm_in_frame(
                ai_frame,
                timeout_ms=max(self._scaled_delay(5000), 5000),
            ):
                clicked_any = True
                rounds_clicked += 1
                self._page.wait_for_timeout(max(self._scaled_delay(500), 500))
                return rounds_clicked

            # Fallback: click confirm from the latest AI message bubble.
            if self._click_latest_fliggy_confirm_in_frame(
                ai_frame,
                timeout_ms=max(self._scaled_delay(3000), 3000),
            ):
                clicked_any = True
                rounds_clicked += 1
                self._page.wait_for_timeout(max(self._scaled_delay(500), 500))
                return rounds_clicked

            if not clicked_any:
                break

            rounds_clicked += 1

        return rounds_clicked

    def _click_fliggy_agent_confirm_once(self, ai_frame) -> bool:
        self._ensure_ready()
        self._page.wait_for_timeout(max(self._scaled_delay(1800), 1800))

        clicked_any = False

        if self._click_fliggy_confirm_xpath_in_frame(
            ai_frame,
            FLIGGY_AGENT_PRE_CONFIRM_XPATH_IN_FRAME,
            timeout_ms=max(self._scaled_delay(700), 700),
        ):
            clicked_any = True
            self._page.wait_for_timeout(max(self._scaled_delay(250), 250))

        if self._click_latest_fliggy_confirm_in_frame(
            ai_frame,
            timeout_ms=max(self._scaled_delay(1200), 1200),
        ):
            clicked_any = True

        if clicked_any:
            return True

        return self._click_latest_fliggy_confirm_in_frame(
            ai_frame,
            timeout_ms=max(self._scaled_delay(1200), 1200),
        )

    def _wait_fliggy_agent_textarea_ready(self) -> None:
        self._ensure_ready()
        total_timeout = max(self._scaled_delay(14000), 14000)
        each_timeout = max(1200, int(total_timeout / max(1, len(FLIGGY_AGENT_TEXTAREA_SELECTORS) + 1)))

        last_error: Exception | None = None
        for selector in FLIGGY_AGENT_TEXTAREA_SELECTORS:
            try:
                self._page.locator(selector).last.wait_for(state="visible", timeout=each_timeout)
                return
            except Exception as exc:
                last_error = exc

        try:
            self._wait_xpath_visible(FLIGGY_AGENT_TEXTAREA_XPATH, "飞猪AI输入框", timeout_ms=each_timeout)
            return
        except Exception as exc:
            last_error = exc

        raise RuntimeError("飞猪AI输入框未就绪，请稍后重试") from last_error

    def _wait_fliggy_agent_send_ready(self) -> None:
        self._ensure_ready()
        total_timeout = max(self._scaled_delay(12000), 12000)
        each_timeout = max(1000, int(total_timeout / max(1, len(FLIGGY_AGENT_SEND_SELECTORS) + 1)))

        try:
            self._wait_xpath_visible(FLIGGY_AGENT_SEND_BUTTON_XPATH, "飞猪AI发送按钮", timeout_ms=each_timeout)
            return
        except Exception:
            pass

        last_error: Exception | None = None
        for selector in FLIGGY_AGENT_SEND_SELECTORS:
            try:
                self._page.locator(selector).last.wait_for(state="visible", timeout=each_timeout)
                return
            except Exception as exc:
                last_error = exc

        raise RuntimeError("飞猪AI发送按钮未就绪，请稍后重试") from last_error

    def _activate_fliggy_agent_textarea(self) -> None:
        self._ensure_ready()
        deadline = time.time() + (max(self._scaled_delay(10000), 10000) / 1000)
        last_error: Exception | None = None

        while time.time() < deadline:
            for selector in FLIGGY_AGENT_INPUT_ACTIVATE_SELECTORS:
                try:
                    anchor = self._page.locator(selector).last
                    anchor.wait_for(state="visible", timeout=max(self._scaled_delay(1200), 1200))
                    anchor.click(timeout=max(self._scaled_delay(1200), 1200), force=True)
                    self._page.wait_for_timeout(max(self._scaled_delay(120), 120))
                except Exception as exc:
                    last_error = exc
                    continue

            for selector in FLIGGY_AGENT_TEXTAREA_SELECTORS:
                try:
                    locator = self._page.locator(selector).last
                    locator.wait_for(state="visible", timeout=max(self._scaled_delay(1200), 1200))
                    locator.click(timeout=max(self._scaled_delay(1200), 1200), force=True)
                    self._page.wait_for_timeout(max(self._scaled_delay(120), 120))
                    try:
                        focused = bool(locator.evaluate("(el) => document.activeElement === el"))
                    except Exception:
                        focused = False
                    if focused:
                        return
                except Exception as exc:
                    last_error = exc
                    continue

            self._page.wait_for_timeout(max(self._scaled_delay(180), 180))

        raise RuntimeError("飞猪AI输入框激活失败，请稍后重试") from last_error

    def _is_fliggy_agent_textarea_value(self, expected: str) -> bool:
        self._ensure_ready()
        target = str(expected)

        try:
            return bool(
                self._page.evaluate(
                    """
                    (expectedText) => {
                      const isVisible = (el) => {
                        if (!el || !el.isConnected) {
                          return false;
                        }
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') {
                          return false;
                        }
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                      };

                      const nodes = Array.from(
                        document.querySelectorAll('textarea.FullscreenComposer-input, div.FullscreenComposer-inputWrap textarea, textarea[enterkeyhint="send"]')
                      ).filter((el) => isVisible(el));
                      if (!nodes.length) {
                        return false;
                      }

                      const targetNode = nodes[nodes.length - 1];
                      return String(targetNode.value || '') === String(expectedText || '');
                    }
                    """,
                    target,
                )
            )
        except Exception:
            return False

    def _fill_fliggy_agent_textarea(self, text: str) -> None:
        self._ensure_ready()
        self._bring_page_to_front(self._page)
        expected = str(text)
        deadline = time.time() + (max(self._scaled_delay(16000), 16000) / 1000)
        last_error: Exception | None = None

        while time.time() < deadline:
            try:
                self._activate_fliggy_agent_textarea()
            except Exception as exc:
                last_error = exc

            # Priority 1: real click + keyboard typing, because this textarea refreshes frequently.
            for selector in FLIGGY_AGENT_TEXTAREA_SELECTORS:
                try:
                    locator = self._page.locator(selector).last
                    locator.wait_for(state="visible", timeout=max(self._scaled_delay(1800), 1800))
                    locator.click(timeout=max(self._scaled_delay(1800), 1800), force=True)

                    try:
                        locator.press("Control+A")
                        locator.press("Delete")
                    except Exception:
                        self._page.keyboard.press("Control+A")
                        self._page.keyboard.press("Delete")

                    try:
                        locator.type(expected, delay=max(8, int(25 * self._timing_factor)))
                    except Exception:
                        self._page.keyboard.type(expected, delay=max(8, int(25 * self._timing_factor)))

                    if self._wait_locator_value(locator, expected, wait_ms=max(self._scaled_delay(1200), 1200)):
                        # Cross one refresh cycle to ensure text is not immediately overwritten.
                        self._page.wait_for_timeout(max(self._scaled_delay(1200), 1200))
                        if self._is_fliggy_agent_textarea_value(expected):
                            return
                except Exception as exc:
                    last_error = exc
                    continue

            # Priority 2: native setter fallback (without blur, avoid leaving edit state).
            try:
                filled = bool(
                    self._page.evaluate(
                        """
                        (value) => {
                          const isVisible = (el) => {
                            if (!el || !el.isConnected) {
                              return false;
                            }
                            const style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden') {
                              return false;
                            }
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                          };

                          const candidates = Array.from(
                            document.querySelectorAll('textarea.FullscreenComposer-input, div.FullscreenComposer-inputWrap textarea, textarea[enterkeyhint="send"]')
                          ).filter((el) => isVisible(el) && !el.disabled && !el.readOnly);

                          if (!candidates.length) {
                            return false;
                          }

                          const target = candidates[candidates.length - 1];
                          target.focus();
                          target.click();

                          const setValue = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
                          if (setValue) {
                            setValue.call(target, value);
                          } else {
                            target.value = value;
                          }

                          try {
                            target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
                          } catch (e) {
                            target.dispatchEvent(new Event('input', { bubbles: true }));
                          }
                          target.dispatchEvent(new Event('change', { bubbles: true }));

                          return String(target.value || '') === String(value || '');
                        }
                        """,
                        expected,
                    )
                )
                if filled:
                    self._page.wait_for_timeout(max(self._scaled_delay(1200), 1200))
                    if self._is_fliggy_agent_textarea_value(expected):
                        return
            except Exception as exc:
                last_error = exc

            try:
                self._fill_xpath(FLIGGY_AGENT_TEXTAREA_XPATH, expected, "飞猪AI输入框", press_enter=False)
                self._page.wait_for_timeout(max(self._scaled_delay(1200), 1200))
                if self._is_fliggy_agent_textarea_value(expected):
                    return
            except Exception as exc:
                last_error = exc

            self._page.wait_for_timeout(max(self._scaled_delay(260), 260))

        raise RuntimeError("飞猪AI输入框填写失败，请稍后重试") from last_error

    def _click_fliggy_agent_send(self) -> None:
        self._ensure_ready()

        try:
            self._click_xpath(FLIGGY_AGENT_SEND_BUTTON_XPATH, "飞猪AI发送按钮")
            return
        except Exception:
            pass

        last_error: Exception | None = None
        for selector in FLIGGY_AGENT_SEND_SELECTORS:
            try:
                locator = self._page.locator(selector).last
                locator.wait_for(state="visible", timeout=max(self._scaled_delay(2500), 2500))
                locator.click(timeout=max(self._scaled_delay(2500), 2500), force=True)
                return
            except Exception as exc:
                last_error = exc
                continue

        try:
            clicked = bool(
                self._page.evaluate(
                    """
                    () => {
                      const isVisible = (el) => {
                        if (!el || !el.isConnected) {
                          return false;
                        }
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') {
                          return false;
                        }
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                      };

                      const actions = Array.from(document.querySelectorAll('div.FullscreenComposer-actions')).filter(isVisible);
                      if (!actions.length) {
                        return false;
                      }

                      const action = actions[actions.length - 1];
                      const clickable = Array.from(action.querySelectorAll('button, [role="button"], span, div, svg')).filter(isVisible);
                      if (!clickable.length) {
                        return false;
                      }

                      clickable[clickable.length - 1].click();
                      return true;
                    }
                    """
                )
            )
            if clicked:
                return
        except Exception as exc:
            last_error = exc

        raise RuntimeError("飞猪AI发送按钮点击失败，请检查页面结构是否变化") from last_error

    def _click_fliggy_agent_confirm(self) -> None:
        self._ensure_ready()

        for confirm_xpath in FLIGGY_AGENT_CONFIRM_BUTTON_XPATHS:
            try:
                self._click_xpath(
                    confirm_xpath,
                    "飞猪AI确认按钮",
                    timeout_ms=max(self._scaled_delay(20000), 20000),
                )
                return
            except Exception:
                pass

        last_error: Exception | None = None
        for selector in FLIGGY_AGENT_CONFIRM_SELECTORS:
            try:
                locator = self._page.locator(selector).last
                locator.wait_for(state="visible", timeout=max(self._scaled_delay(9000), 9000))
                locator.click(timeout=max(self._scaled_delay(9000), 9000), force=True)
                return
            except Exception as exc:
                last_error = exc
                continue

        for button_name in ("确定", "确 定", "确认"):
            try:
                locator = self._page.get_by_role("button", name=button_name).last
                locator.wait_for(state="visible", timeout=max(self._scaled_delay(4000), 4000))
                locator.click(timeout=max(self._scaled_delay(4000), 4000), force=True)
                return
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError("飞猪AI确认按钮点击失败，请检查页面结构是否变化") from last_error

    def _wait_fliggy_route_ready(self, route_keyword: str, *, timeout_ms: int, step_name: str) -> None:
        self._ensure_ready()
        keyword = str(route_keyword or "").strip().lower()
        deadline = time.time() + max(0.2, timeout_ms / 1000)

        while time.time() < deadline:
            current_url = str(self._page.url or "").lower()
            if "login" in current_url:
                raise RuntimeError("飞猪会话未登录，请先在登录引导页完成飞猪登录")

            if keyword and keyword in current_url:
                return

            self._page.wait_for_timeout(self._scaled_delay(120))

        current_url = str(self._page.url or "").strip() or "未知"
        raise RuntimeError(f"{step_name}未完成，当前页面: {current_url}")

    def _open_batch_status_page(self) -> None:
        self._ensure_ready()
        self._bring_page_to_front(self._page)

        self._page.goto(
            FLIGGY_HOME_URL,
            wait_until="domcontentloaded",
            timeout=self._timeout_ms,
        )
        self._wait_fliggy_route_ready(
            FLIGGY_HOME_ROUTE_KEYWORD,
            timeout_ms=max(self._scaled_delay(10000), 10000),
            step_name="飞猪首页预热",
        )
        self._page.reload(wait_until="domcontentloaded", timeout=self._timeout_ms)
        self._wait_fliggy_route_ready(
            FLIGGY_HOME_ROUTE_KEYWORD,
            timeout_ms=max(self._scaled_delay(10000), 10000),
            step_name="飞猪首页刷新",
        )
        self._page.wait_for_timeout(max(self._scaled_delay(2500), 2500))

        self._page.goto(
            FLIGGY_AGENT_URL,
            wait_until="domcontentloaded",
            timeout=self._timeout_ms,
        )
        self._wait_fliggy_route_ready(
            FLIGGY_AGENT_ROUTE_KEYWORD,
            timeout_ms=max(self._scaled_delay(10000), 10000),
            step_name="飞猪AI助理页",
        )
        # Agent page may render textarea asynchronously; wait a bit before touching input.
        self._page.wait_for_timeout(max(self._scaled_delay(3500), 3500))

        self._wait_batch_page_ready()
        self._batch_page_opened = True

    def open_batch_status_page(self) -> None:
        self._open_batch_status_page()

    @staticmethod
    def _format_fliggy_date(dt: date) -> str:
        return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"

    @classmethod
    def _build_fliggy_date_range(cls, check_in_date: str, check_out_date: str) -> tuple[str, str]:
        check_in = date.fromisoformat(str(check_in_date))
        check_out = date.fromisoformat(str(check_out_date))
        if check_out <= check_in:
            raise ValueError("离店日期必须晚于到店日期")
        return cls._format_fliggy_date(check_in), cls._format_fliggy_date(check_out - timedelta(days=1))

    def _fill_remaining_quantity_with_retry(self, quantity: int) -> None:
        last_error: Exception | None = None
        for attempt in range(2):
            for xpath in FLIGGY_REMAINING_INPUT_XPATHS:
                try:
                    locator = self._wait_xpath_enabled(
                        xpath,
                        "剩余房量输入框",
                        timeout_ms=max(self._scaled_delay(9000), 9000),
                    )
                    self._fill_xpath(xpath, str(int(quantity)), "剩余房量", press_enter=False)
                    if self._read_locator_value(locator) == str(int(quantity)):
                        return
                except Exception as exc:
                    last_error = exc
                    continue
            self._page.wait_for_timeout(self._scaled_delay(500))
            if attempt == 1:
                break

        raise RuntimeError("剩余房量输入框未就绪，请稍后重试") from last_error

    def _select_room_type_by_table(self, room_type: str) -> None:
        self._ensure_ready()

        try:
            room_row = self._page.get_by_role("row").filter(has_text=room_type).first
            room_row.wait_for(state="visible", timeout=max(self._scaled_delay(12000), 12000))
            checkbox = room_row.get_by_role("checkbox").first
            checkbox.click(timeout=max(self._scaled_delay(5000), 5000), force=True)
            return
        except Exception:
            pass

        # Fallback: keep XPath selectors for compatibility with older page structures.
        self._click_any_xpath(FLIGGY_ROOM_TYPE_XPATHS[room_type], "选择房型")

    def _pick_date_range_by_calendar(self, start_date: str, end_date: str) -> None:
        self._ensure_ready()

        date_picker = self._page.get_by_placeholder("开始日期").first
        date_picker.wait_for(state="visible", timeout=max(self._scaled_delay(12000), 12000))
        date_picker.click(timeout=max(self._scaled_delay(6000), 6000), force=True)

        start_cell = self._page.locator(f"td[title='{start_date}']").first
        start_cell.wait_for(state="visible", timeout=max(self._scaled_delay(12000), 12000))
        start_cell.click(timeout=max(self._scaled_delay(6000), 6000), force=True)

        end_cell = self._page.locator(f"td[title='{end_date}']").first
        end_cell.wait_for(state="visible", timeout=max(self._scaled_delay(12000), 12000))
        end_cell.click(timeout=max(self._scaled_delay(6000), 6000), force=True)

    def _select_change_mode_and_fill_quantity(self, quantity: int) -> None:
        self._ensure_ready()

        target_radio_label = self._page.locator("label").filter(has_text="改为").nth(1)
        target_radio_label.wait_for(state="visible", timeout=max(self._scaled_delay(15000), 15000))

        # Give the page enough time to finish delayed re-render and release overlays.
        self._page.wait_for_timeout(max(self._scaled_delay(5000), 5000))
        target_radio_label.click(timeout=max(self._scaled_delay(6000), 6000), force=True)

        amount_input = target_radio_label.locator("..").locator("input").last
        amount_input.wait_for(state="visible", timeout=max(self._scaled_delay(12000), 12000))
        amount_input.click(timeout=max(self._scaled_delay(5000), 5000), force=True)
        amount_input.fill(str(int(quantity)), timeout=max(self._scaled_delay(6000), 6000))

        if self._read_locator_value(amount_input) != str(int(quantity)):
            amount_input.evaluate(
                """
                (el, v) => {
                  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                  if (nativeSetter) {
                    nativeSetter.call(el, v);
                  } else {
                    el.value = v;
                  }
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                }
                """,
                str(int(quantity)),
            )

        if self._read_locator_value(amount_input) != str(int(quantity)):
            raise RuntimeError("飞猪房量输入后未生效")

    @staticmethod
    def _build_fliggy_agent_prompt(update: FliggyQuantityUpdate, *, range_start: str, range_end: str) -> str:
        return (
            f"时间段 {range_start} 至 {range_end}，"
            f"房量改为{int(update.remaining_quantity)}，"
            f"{update.room_type}"
        )

    def _wait_submit_success(self, update: FliggyQuantityUpdate, *, range_start: str, range_end: str) -> str:
        self._wait_batch_page_ready()

        prompt = self._build_fliggy_agent_prompt(
            update,
            range_start=range_start,
            range_end=range_end,
        )

        ai_frame = self._get_fliggy_agent_frame()
        self._fill_fliggy_agent_textarea_via_frame(ai_frame, prompt)
        self._page.wait_for_timeout(max(self._scaled_delay(1500), 1500))
        self._click_fliggy_agent_send_via_frame(ai_frame)
        confirm_rounds = self._run_fliggy_agent_confirm_rounds(ai_frame, max_rounds=3)
        self._page.wait_for_timeout(max(self._scaled_delay(2000), 2000))

        if confirm_rounds > 0:
            return f"已通过飞猪AI助理提交: {prompt}（已处理{confirm_rounds}轮确认）"
        return f"已通过飞猪AI助理提交: {prompt}"

    def update_room_quantity(
        self,
        update: FliggyQuantityUpdate,
        *,
        open_page: bool = True,
        apply_date: bool = True,
        auto_submit: bool = True,
    ) -> dict[str, str | int]:
        if not str(update.room_type or "").strip():
            raise ValueError("飞猪房型不能为空")

        if int(update.remaining_quantity) < 0:
            raise ValueError("剩余房量不能小于 0")

        range_start, range_end = self._build_fliggy_date_range(
            update.check_in_date,
            update.check_out_date,
        )

        self._bring_page_to_front(self._page)

        if open_page or not self._batch_page_opened:
            self._open_batch_status_page()

        if auto_submit:
            submit_result = self._wait_submit_success(
                update,
                range_start=range_start,
                range_end=range_end,
            )
        else:
            prompt = self._build_fliggy_agent_prompt(
                update,
                range_start=range_start,
                range_end=range_end,
            )
            submit_result = f"已打开飞猪AI助理，请手动发送并确认: {prompt}"

        return {
            "roomType": update.room_type,
            "startDate": range_start,
            "endDate": range_end,
            "remainingQuantity": int(update.remaining_quantity),
            "submitResult": submit_result,
        }


class MeituanSyncSession(_SyncSessionBase):
    def __init__(self, *, headless: bool = False, slow_mo: int = 0, timeout_ms: int = 36000):
        cdp_primary = os.getenv(
            "MEITUAN_SYNC_BROWSER_CDP_ENDPOINT",
            f"http://127.0.0.1:{MEITUAN_SYNC_BROWSER_CDP_PORT}",
        )
        cdp_fallback = os.getenv("SYNC_BROWSER_CDP_ENDPOINT", f"http://127.0.0.1:{SYNC_BROWSER_CDP_PORT}")
        super().__init__(
            headless=headless,
            slow_mo=slow_mo,
            timeout_ms=timeout_ms,
            profile_dir=MEITUAN_PROFILE_DIR,
            cdp_endpoints=(cdp_fallback, cdp_primary),
            timing_envs=("MEITUAN_TIMING_FACTOR", "CTRIP_TIMING_FACTOR"),
            require_existing_browser=headless,
            page_url_keywords=("me.meituan.com",),
        )
        self._batch_page_opened = False

    def _wait_batch_page_ready(self) -> None:
        first_room_type_xpath = next(iter(MEITUAN_ROOM_TYPE_XPATHS.values()))[0]
        self._wait_xpath_visible(first_room_type_xpath, "房型列表")
        self._wait_xpath_visible(MEITUAN_DATE_START_XPATH, "起始日期输入框")
        self._wait_xpath_visible(MEITUAN_DATE_END_XPATH, "终止日期输入框")

    def _open_batch_inventory_page(self) -> None:
        self._ensure_ready()
        self._bring_page_to_front(self._page)
        self._page.goto(MEITUAN_BATCH_INVENTORY_URL, wait_until="domcontentloaded")

        current_url = str(self._page.url or "").lower()
        if "login" in current_url:
            raise RuntimeError("美团会话未登录，请先在登录引导页完成美团登录")

        self._wait_batch_page_ready()
        self._batch_page_opened = True

    def open_batch_inventory_page(self) -> None:
        self._open_batch_inventory_page()

    @staticmethod
    def _format_meituan_date(dt: date) -> str:
        return f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}"

    @classmethod
    def _build_meituan_date_range(cls, check_in_date: str, check_out_date: str) -> tuple[str, str]:
        check_in = date.fromisoformat(str(check_in_date))
        check_out = date.fromisoformat(str(check_out_date))
        if check_out <= check_in:
            raise ValueError("离店日期必须晚于到店日期")
        return cls._format_meituan_date(check_in), cls._format_meituan_date(check_out - timedelta(days=1))

    def _fill_remaining_quantity_with_retry(self, quantity: int) -> None:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                self._wait_xpath_enabled(
                    MEITUAN_REMAINING_INPUT_XPATH,
                    "剩余房量输入框",
                    timeout_ms=max(self._scaled_delay(9000), 9000),
                )
                self._fill_xpath(
                    MEITUAN_REMAINING_INPUT_XPATH,
                    str(int(quantity)),
                    "剩余房量",
                    press_enter=False,
                )
                return
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    self._page.wait_for_timeout(self._scaled_delay(500))

        raise RuntimeError("剩余房量输入框未就绪，请稍后重试") from last_error

    def _wait_submit_success(self) -> str:
        submit_timeout = min(self._timeout_ms, 20000)

        self._wait_any_xpath_visible(MEITUAN_SUBMIT_XPATHS, "提交按钮", timeout_ms=submit_timeout)
        self._click_any_xpath(MEITUAN_SUBMIT_XPATHS, "提交")
        self._page.wait_for_timeout(max(self._scaled_delay(2000), 2000))

        for selector in ("text=提交失败", "text=修改提交失败", "text=操作失败", "text=请重试"):
            try:
                if self._page.locator(selector).first.is_visible(timeout=self._scaled_delay(180)):
                    raise RuntimeError("美团页面提示提交失败，请人工核对后重试")
            except RuntimeError:
                raise
            except Exception:
                continue

        return "已提交，未长时间等待成功提示"

    def update_room_quantity(
        self,
        update: MeituanQuantityUpdate,
        *,
        open_page: bool = True,
        restore_management_tab: bool = True,
    ) -> dict[str, str | int]:
        if update.room_type not in MEITUAN_ROOM_TYPE_XPATHS:
            supported = ", ".join(MEITUAN_ROOM_TYPE_XPATHS.keys())
            raise ValueError(f"美团暂不支持该房型: {update.room_type}，支持: {supported}")

        if int(update.remaining_quantity) < 0:
            raise ValueError("剩余房量不能小于 0")

        range_start, range_end = self._build_meituan_date_range(
            update.check_in_date,
            update.check_out_date,
        )

        management_page = self._find_local_management_page() if restore_management_tab else None
        self._bring_page_to_front(self._page)

        try:
            if open_page or not self._batch_page_opened:
                self._open_batch_inventory_page()

            self._click_any_xpath(MEITUAN_ROOM_TYPE_XPATHS[update.room_type], "选择房型")
            self._wait_xpath_visible(MEITUAN_DATE_START_XPATH, "起始日期输入框")

            self._set_xpath_value_direct(MEITUAN_DATE_START_XPATH, range_start, "起始日期")
            self._wait_xpath_visible(MEITUAN_DATE_END_XPATH, "终止日期输入框")
            self._set_xpath_value_direct(MEITUAN_DATE_END_XPATH, range_end, "终止日期")

            try:
                self._wait_xpath_enabled(
                    MEITUAN_REMAINING_MODE_XPATH,
                    "剩余房量模式",
                    timeout_ms=max(self._scaled_delay(6000), 6000),
                )
                self._click_xpath(MEITUAN_REMAINING_MODE_XPATH, "切换剩余房量模式")
            except Exception:
                pass

            self._fill_remaining_quantity_with_retry(int(update.remaining_quantity))
            success_text = self._wait_submit_success()

            return {
                "roomType": update.room_type,
                "startDate": range_start,
                "endDate": range_end,
                "remainingQuantity": int(update.remaining_quantity),
                "submitResult": success_text,
            }
        finally:
            if restore_management_tab and management_page is not None and management_page is not self._page:
                self._bring_page_to_front(management_page)
