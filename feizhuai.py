import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

# --- 基础配置 ---
BASE_DIR = Path(__file__).resolve().parent
SESSION_ROOT = BASE_DIR / "sessions"
FLIGGY_HOME_URL = "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk/homeV1"

def launch_context(playwright):
    """使用高阶防拦截配置启动本地浏览器"""
    profile_dir = SESSION_ROOT / "fliggy"  # 数据保存在 fliggy 文件夹
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel="msedge",  # 使用本地 Edge 浏览器
        headless=False,    # 必须显示界面
        no_viewport=True,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"], # 核心防拦截
        ignore_default_args=["--enable-automation"] # 隐藏自动化提示
    )

def run_fliggy_task(page: Page, start_date: str, end_date: str, room_count: str, room_type: str):
    """执行飞猪 AI 助理改房量核心逻辑 - 智能多轮确认版"""
    print("\n[1/4] 正在跳转至 AI 助理页面...")
    page.goto("https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk/agent")
    
    page.wait_for_timeout(3000) 
    print("[2/4] 正在穿透 iframe 并注入文本...")
    
    ai_frame = page.frame_locator("iframe[src*='xbot']").first
    textarea_locator = ai_frame.locator("textarea.FullscreenComposer-input").last
    
    try:
        textarea_locator.wait_for(state="attached", timeout=15000)
    except Exception:
        raise Exception("15秒超时：无法在 iframe 中捕获输入框。")

    change_text = f"时间段 {start_date} 至 {end_date}，房量改为{room_count}，{room_type}"
    
    textarea_locator.evaluate(
        """
        (el, text) => {
            let nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
            if (nativeSetter) {
                nativeSetter.call(el, text);
            } else {
                el.value = text;
            }
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """, change_text
    )
    print(f"      -> ✅ 已成功注入内容: {change_text}")
    
    page.wait_for_timeout(1500) 
    
    # ---------------------------------------------------------
    print("[3/4] 正在精准点击发送按钮...")
    send_btn_xpath = "/html/body/div/div/div[3]/div[4]/div/div/button[2]"
    send_btn_locator = ai_frame.locator(f"xpath={send_btn_xpath}")
    
    try:
        send_btn_locator.click(force=True)
        print("      -> ✅ 发送指令成功！")
    except Exception as e:
        print(f"      -> ❌ 发送按钮点击失败: {e}")
    
    # ---------------------------------------------------------
    print("[4/4] ⏳ 开启智能轮询，处理 AI 多轮确认...")
    
    # 最多允许 AI 弹出 3 次确认（防止陷入死循环）
    for step in range(3):
        print(f"\n      ▶️ 等待并检测第 {step + 1} 轮确认...")
        
        # 给 AI 留出基础的“思考”和“打字”时间
        page.wait_for_timeout(4000)
        
        try:
            # 【核心策略 1】：锁定聊天界面的“最后一条 AI 回复气泡” (从你的截图中可以看到类名包含 Message left)
            # 这样可以确保我们绝不会点到历史聊天记录里失效的旧按钮！
            last_ai_message = ai_frame.locator("div[class*='Message left']").last
            
            # 【核心策略 2】：在这个最新的气泡里，寻找包含 '确认' 文本且类名带 btn 的元素
            confirm_btn = last_ai_message.locator("div[class*='btn']").filter(has_text="确认").first
            
            # 等待按钮出现（如果 10 秒内没出现，说明 AI 这一轮没有发按钮，直接触发 except）
            confirm_btn.wait_for(state="visible", timeout=10000)
            
            print(f"      -> 发现确认按钮！正在执行物理+JS双重点击...")
            
            # 将按钮滚动到屏幕中间
            confirm_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            
            # 物理点击
            box = confirm_btn.bounding_box()
            if box:
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.wait_for_timeout(500)
                
            # JS 兜底点击
            confirm_btn.evaluate(
                "(el) => { el.click(); el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); }"
            )
            
            print(f"      -> 第 {step + 1} 轮确认已点击完成，等待 AI 下一步动作...")
            
        except Exception:
            # 如果在这个过程中抛出了超时异常，说明最新的消息里没有“确认”按钮了。
            # 这通常意味着修改已经完成，AI 回复了一段纯文本。
            if step == 0:
                print("      -> ⚠️ 第一轮就没有检测到确认按钮，可能是页面卡顿或指令直接执行了。")
            else:
                print("      -> ✅ 最新回复中已无确认按钮，多轮交互顺利结束！")
            break # 跳出循环，完成任务

    print("\n🎉 房量修改自动化流程彻底完毕！")
    page.wait_for_timeout(3000)

def main():
    with sync_playwright() as playwright:
        context = launch_context(playwright)
        page = context.pages[0] if context.pages else context.new_page()
        # 设置页面全局超时
        page.set_default_timeout(36000)
        
        print("正在打开飞猪 ebooking 首页...")
        page.goto(FLIGGY_HOME_URL)
        
        print("\n" + "="*50)
        print("⏸️ 程序已暂停！")
        print("请在弹出的 Edge 浏览器中确认是否已登录飞猪。")
        input(">> 确认进入后台首页后，请按回车开始自动化测试：")
        
        try:
            # 在这里配置你的改价信息
            run_fliggy_task(
                page,
                start_date="2026-04-27", 
                end_date="2026-04-27", 
                room_count="1", 
                room_type="家庭大床房"
            )
        except Exception as e:
            print(f"\n❌ 执行失败: {e}")

        print("\n浏览器保持开启中...")
        while True: 
            time.sleep(1)

if __name__ == "__main__":
    main()