const dom = {
  openLoginTabsBtn: document.getElementById("openLoginTabsBtn"),
  refreshLoginStateBtn: document.getElementById("refreshLoginStateBtn"),
  loginTabsStatus: document.getElementById("loginTabsStatus"),
  toast: document.getElementById("toast"),
};

function showToast(message, isError = false) {
  dom.toast.textContent = message;
  dom.toast.classList.remove("hidden", "error");
  if (isError) {
    dom.toast.classList.add("error");
  }
  setTimeout(() => {
    dom.toast.classList.add("hidden");
  }, 2800);
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.message || "请求失败");
  }
  return data;
}

function renderLoginWindowState(running, browserReachable) {
  if (running && browserReachable) {
    dom.loginTabsStatus.textContent = "登录窗口状态：运行中（请在单浏览器多标签页完成登录；请勿关闭飞猪相关标签）";
    return;
  }

  if (running && !browserReachable) {
    dom.loginTabsStatus.textContent = "登录窗口状态：进程运行但浏览器未就绪，可点击重新打开";
    return;
  }

  dom.loginTabsStatus.textContent = "登录窗口状态：未运行（可点击按钮重新打开）";
}

async function refreshLoginWindowState() {
  const result = await requestJSON("/api/bootstrap/login-tabs-status");
  renderLoginWindowState(Boolean(result.running), Boolean(result.browserReachable));
}

async function openLoginTabs() {
  dom.openLoginTabsBtn.disabled = true;
  try {
    const result = await requestJSON("/api/bootstrap/open-login-tabs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        platforms: ["ctrip", "fliggy", "meituan"],
        forceRestart: false,
      }),
    });

    await refreshLoginWindowState();
    showToast(result.message || "已打开登录浏览器");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    dom.openLoginTabsBtn.disabled = false;
  }
}

function wireEvents() {
  dom.openLoginTabsBtn.addEventListener("click", openLoginTabs);
  dom.refreshLoginStateBtn.addEventListener("click", async () => {
    try {
      await refreshLoginWindowState();
      showToast("已刷新登录窗口状态");
    } catch (error) {
      showToast(error.message, true);
    }
  });
}

async function bootstrap() {
  wireEvents();
  try {
    await refreshLoginWindowState();
  } catch (error) {
    showToast(error.message, true);
  }

  setInterval(() => {
    refreshLoginWindowState().catch(() => {});
  }, 3000);
}

bootstrap();
