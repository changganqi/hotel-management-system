import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

# --- 基础配置 ---
BASE_DIR = Path(__file__).resolve().parent
SESSION_ROOT = BASE_DIR / "sessions"
CTRIP_URL = "https://ebooking.trip.com/rateplan/batchSetRoomStatusAndQuantity?microJump=true"

def launch_context(playwright):
    profile_dir = SESSION_ROOT / "ctrip"
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel="msedge",
        headless=False,
        no_viewport=True,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"]
    )

def run_ctrip_task(page: Page):
    # --- 任务配置参数 ---
    target_room = "豪华双床房"
    target_month = "4月"  # 目标月份
    start_day = "14"
    end_day = "17"
    room_count = "6"

    print(f"\n[任务开始] 目标: {target_room} | 时间: {target_month} {start_day}-{end_day}")

    # 1. 勾选房型
    print("[1/5] 正在勾选房型...")
    room_checkbox = page.locator("div").filter(has_text=target_room).locator(".he-trip-kit-ui-tree-checkbox-inner").last
    room_checkbox.scroll_into_view_if_needed()
    room_checkbox.click(force=True)
    print(f"      -> 已成功勾选: {target_room}")

    # 2. 【新增逻辑】滚动至“选择日期”区域
    # 这一步非常重要，确保日历组件被激活加载
    print("[2/5] 正在拉取滚动条至日期修改区域...")
    date_section_header = page.get_by_text("设置房态", exact=True)
    date_section_header.scroll_into_view_if_needed()
    page.wait_for_timeout(1000) # 等待滚动平稳

    # 3. 操作日历（含月份修改）
    def open_and_set_calendar(index, day, month):
        # 定位包裹容器
        picker_wrapper = page.locator(".he-trip-kit-ui-picker").nth(index)
        print(f"      -> 正在激活第 {index+1} 个日历框...")
        
        # 激活蓝色边框与面板
        for _ in range(3):
            picker_wrapper.click(force=True)
            page.wait_for_timeout(600)
            if page.locator(".he-trip-kit-ui-picker-dropdown:not(.he-trip-kit-ui-picker-dropdown-hidden)").is_visible():
                break

        active_panel = page.locator(".he-trip-kit-ui-picker-dropdown:not(.he-trip-kit-ui-picker-dropdown-hidden)")
        active_panel.wait_for(state="visible", timeout=5000)

        # --- 修改月份逻辑 ---
        print(f"      -> 检查月份是否为: {month}")
        # 在当前弹出的面板中找到月份显示器
        month_selector = active_panel.locator(".he-trip-kit-ui-select-selection-item").filter(has_text="月")
        
        current_month = month_selector.inner_text()
        if month not in current_month:
            print(f"      -> 当前月份 {current_month} 不匹配，正在切换至 {month}...")
            month_selector.click(force=True)
            page.wait_for_timeout(500)
            # 在弹出的月份下拉菜单中点击目标月份
            page.locator(".he-trip-kit-ui-select-item-option-content").filter(has_text=f"^{month}$").click(force=True)
            page.wait_for_timeout(800) # 等待日历天数刷新

        # --- 选择日期 ---
        date_id = f"2026-04-{str(day).zfill(2)}" # 注意：年份建议根据实际获取
        print(f"      -> 正在选择日期: {day}日")
        target_cell = active_panel.locator(f"td[title='{date_id}']")
        
        if target_cell.count() > 0:
            target_cell.first.dispatch_event("click")
        else:
            active_panel.locator(".he-trip-kit-ui-picker-cell-inner").filter(has_text=f"^{day}$").first.click(force=True)

    print("[3/5] 正在设置起始与终止日期（含月份校对）...")
    open_and_set_calendar(0, start_day, target_month)
    page.wait_for_timeout(1000)
    open_and_set_calendar(1, end_day, target_month)

    # 4. 设置房量
    print("[4/5] 正在设置房量数值...")
    page.get_by_text("设置房量").scroll_into_view_if_needed()
    page.wait_for_timeout(1000)
    
    change_radio = page.locator("label").filter(has_text="改为").first
    change_radio.click(force=True)
    
    amount_input = change_radio.locator("..").locator("input").last
    amount_input.fill(room_count)
    print(f"      -> 已将数量改为: {room_count}")

    # 5. 提交
    print("[5/5] 准备提交...")
    # submit_btn = page.get_by_role("button", name="提交").first
    # submit_btn.click()
    print("\n🎉 自动化流程测试完毕！")

def main():
    with sync_playwright() as playwright:
        context = launch_context(playwright)
        page = context.pages[0] if context.pages else context.new_page()
        
        page.goto(CTRIP_URL)
        print("\n" + "="*50)
        print("请确认已登录携程，并处于『批量修改房态房量』页面。")
        input(">> 确认就绪后请按回车开始自动化测试：")

        try:
            run_ctrip_task(page)
        except Exception as e:
            print(f"\n❌ 执行失败: {e}")

        print("\n浏览器保持开启中...")
        while True: time.sleep(1)

if __name__ == "__main__":
    main()