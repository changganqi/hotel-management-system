const state = {
  roomTypes: [],
  localOnlyRoomTypes: ["普通大床房", "普通双床房"],
  platforms: [],
  statuses: [],
  calendarWindowDays: 7,
  pendingPreferredRoomIds: [],
  lastSyncReport: null,
  lastSyncSourcePlatform: "",
  isRetrying: false,
  asyncSyncJobId: "",
  asyncSyncPollingTimer: null,
  asyncSyncPollingBusy: false,
  syncGuardTimer: null,
  syncGuardDeadline: 0,
  syncGuardBaseMessage: "",
  platformFocusBusy: false,
  pendingDatePickerField: "",
};

const dom = {
  viewDate: document.getElementById("viewDate"),
  inventoryCalendar: document.getElementById("inventoryCalendar"),
  historyTableBody: document.querySelector("#historyTable tbody"),
  inventoryHint: document.getElementById("inventoryHint"),
  openAdjustBtn: document.getElementById("openAdjustBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  initModal: document.getElementById("initModal"),
  closeInitModalBtn: document.getElementById("closeInitModalBtn"),
  cancelInitBtn: document.getElementById("cancelInitBtn"),
  initForm: document.getElementById("initForm"),
  initRoomTypeText: document.getElementById("initRoomTypeText"),
  bookingDetailModal: document.getElementById("bookingDetailModal"),
  closeBookingDetailBtn: document.getElementById("closeBookingDetailBtn"),
  bookingDetailContent: document.getElementById("bookingDetailContent"),
  syncProgressModal: document.getElementById("syncProgressModal"),
  closeSyncProgressBtn: document.getElementById("closeSyncProgressBtn"),
  syncProgressTitle: document.getElementById("syncProgressTitle"),
  syncProgressSpinner: document.getElementById("syncProgressSpinner"),
  syncProgressList: document.getElementById("syncProgressList"),
  retrySyncBtn: document.getElementById("retrySyncBtn"),
  giveUpSyncBtn: document.getElementById("giveUpSyncBtn"),
  syncGuardOverlay: document.getElementById("syncGuardOverlay"),
  syncGuardMessage: document.getElementById("syncGuardMessage"),
  syncGuardCountdown: document.getElementById("syncGuardCountdown"),
  platformGuidePanel: document.getElementById("platformGuidePanel"),
  platformGuideHint: document.getElementById("platformGuideHint"),
  platformGuideTasks: document.getElementById("platformGuideTasks"),
  modal: document.getElementById("adjustModal"),
  closeModalBtn: document.getElementById("closeModalBtn"),
  cancelBtn: document.getElementById("cancelBtn"),
  adjustForm: document.getElementById("adjustForm"),
  bookingIdLabel: document.getElementById("bookingIdLabel"),
  bookingIdTitle: document.getElementById("bookingIdTitle"),
  quantityLabel: document.getElementById("quantityLabel"),
  roomPickerSection: document.getElementById("roomPickerSection"),
  roomPickerList: document.getElementById("roomPickerList"),
  toast: document.getElementById("toast"),
};

const DATA_HEALTH_ALERT_ACK_PREFIX = "hotel-db-alert-ack:";


function calcWindowDays() {
  return window.innerWidth < 2200 ? 7 : 14;
}

function todayString() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function toIsoDateString(dt) {
  const yyyy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function isValidIsoDate(dateStr) {
  const raw = String(dateStr || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    return false;
  }
  const dt = new Date(`${raw}T00:00:00`);
  if (Number.isNaN(dt.getTime())) {
    return false;
  }
  return toIsoDateString(dt) === raw;
}

function normalizeFlexibleDateInput(rawValue) {
  const raw = String(rawValue || "").trim();
  if (!raw) {
    return "";
  }

  const compact = raw.replace(/\s+/g, "");
  if (/^\d{8}$/.test(compact)) {
    const yyyy = compact.slice(0, 4);
    const mm = compact.slice(4, 6);
    const dd = compact.slice(6, 8);
    const formatted = `${yyyy}-${mm}-${dd}`;
    return isValidIsoDate(formatted) ? formatted : "";
  }

  const normalizedSep = compact.replace(/\//g, "-").replace(/\./g, "-");
  const match = normalizedSep.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (!match) {
    return "";
  }

  const yyyy = match[1];
  const mm = String(match[2]).padStart(2, "0");
  const dd = String(match[3]).padStart(2, "0");
  const formatted = `${yyyy}-${mm}-${dd}`;
  return isValidIsoDate(formatted) ? formatted : "";
}

function addDays(dateStr, days) {
  const base = normalizeFlexibleDateInput(dateStr);
  if (!base) {
    return "";
  }
  const dt = new Date(`${base}T00:00:00`);
  dt.setDate(dt.getDate() + days);
  return toIsoDateString(dt);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function platformKey(platform) {
  const text = String(platform || "").trim().toLowerCase();
  if (text.includes("携程") || text === "ctrip") {
    return "ctrip";
  }
  if (text.includes("飞猪") || text === "fliggy") {
    return "fliggy";
  }
  if (text.includes("美团") || text === "meituan") {
    return "meituan";
  }
  if (text.includes("抖音") || text === "douyin") {
    return "direct";
  }
  return "direct";
}

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

function showDataHealthAlertIfNeeded(alert) {
  if (!alert || typeof alert !== "object") {
    return;
  }

  const alertId = String(alert.id || "").trim();
  if (!alertId) {
    return;
  }

  const storageKey = `${DATA_HEALTH_ALERT_ACK_PREFIX}${alertId}`;
  try {
    if (window.localStorage.getItem(storageKey) === "1") {
      return;
    }
  } catch (error) {
    // Ignore storage failures and continue with popup.
  }

  const coreMessage = String(alert.message || "数据库故障，请联系技术支持。").trim();
  const finalMessage = `${coreMessage}\n\n请寻求技术支持。`;
  showToast(coreMessage, true);

  try {
    window.alert(finalMessage);
  } catch (error) {
    // Ignore alert failures in non-browser contexts.
  }

  try {
    window.localStorage.setItem(storageKey, "1");
  } catch (error) {
    // Ignore storage failures.
  }
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.message || "请求失败");
  }
  return data;
}

function openModal(modalEl) {
  modalEl.classList.remove("hidden");
  modalEl.setAttribute("aria-hidden", "false");
}

function closeModal(modalEl) {
  modalEl.classList.add("hidden");
  modalEl.setAttribute("aria-hidden", "true");
}


const syncDisplayPlatforms = ["携程", "飞猪", "美团"];
const RETRY_BTN_TEXT_IDLE = "重新尝试";
const GIVE_UP_BTN_TEXT_IDLE = "放弃尝试";
const ASYNC_SYNC_POLL_MS = 2200;
const SYNC_GUARD_DEFAULT_SECONDS = 240;
const SYNC_GUARD_RETRY_SECONDS = 180;

function setRetrySyncButtonLoading(isLoading) {
  const loading = Boolean(isLoading);
  dom.retrySyncBtn.classList.toggle("is-loading", loading);
  dom.retrySyncBtn.disabled = loading;
  dom.retrySyncBtn.setAttribute("aria-busy", loading ? "true" : "false");
  dom.retrySyncBtn.innerHTML = loading
    ? '<span class="btn-inline-spinner" aria-hidden="true"></span><span>重试中...</span>'
    : RETRY_BTN_TEXT_IDLE;
}

function setGiveUpSyncButtonLoading(isLoading) {
  if (!dom.giveUpSyncBtn) {
    return;
  }
  const loading = Boolean(isLoading);
  dom.giveUpSyncBtn.classList.toggle("is-loading", loading);
  dom.giveUpSyncBtn.disabled = loading;
  dom.giveUpSyncBtn.setAttribute("aria-busy", loading ? "true" : "false");
  dom.giveUpSyncBtn.innerHTML = loading
    ? '<span class="btn-inline-spinner" aria-hidden="true"></span><span>放弃中...</span>'
    : GIVE_UP_BTN_TEXT_IDLE;
}

function setSyncActionButtonsBusy(action) {
  const mode = String(action || "").trim().toLowerCase();
  const retryLoading = mode === "retry";
  const giveUpLoading = mode === "giveup";
  const isBusy = retryLoading || giveUpLoading;

  setRetrySyncButtonLoading(retryLoading);
  setGiveUpSyncButtonLoading(giveUpLoading);

  if (isBusy && !retryLoading) {
    dom.retrySyncBtn.disabled = true;
  }
  if (isBusy && dom.giveUpSyncBtn && !giveUpLoading) {
    dom.giveUpSyncBtn.disabled = true;
  }
}

function stopSyncGuardTimer() {
  if (state.syncGuardTimer) {
    clearInterval(state.syncGuardTimer);
    state.syncGuardTimer = null;
  }
}

function formatSyncGuardCountdown(seconds) {
  const safeSeconds = Math.max(0, Number(seconds) || 0);
  const mins = Math.floor(safeSeconds / 60);
  const secs = safeSeconds % 60;
  if (mins <= 0) {
    return `${secs}秒`;
  }
  return `${mins}分${String(secs).padStart(2, "0")}秒`;
}

function refreshSyncGuardCountdown() {
  if (!dom.syncGuardCountdown || !dom.syncGuardMessage) {
    return;
  }

  const baseMessage = state.syncGuardBaseMessage || "脚本运行中，请勿操作浏览器中的平台标签页。";
  if (!state.syncGuardDeadline) {
    dom.syncGuardCountdown.textContent = "--";
    dom.syncGuardMessage.textContent = baseMessage;
    return;
  }

  const remainingSeconds = Math.ceil((state.syncGuardDeadline - Date.now()) / 1000);
  if (remainingSeconds > 0) {
    dom.syncGuardCountdown.textContent = formatSyncGuardCountdown(remainingSeconds);
    dom.syncGuardMessage.textContent = baseMessage;
    return;
  }

  dom.syncGuardCountdown.textContent = "已超时";
  dom.syncGuardMessage.textContent = "自动同步仍在执行，请继续不要操作平台标签页。";
}

function showSyncGuardOverlay(message, seconds = SYNC_GUARD_DEFAULT_SECONDS) {
  if (!dom.syncGuardOverlay) {
    return;
  }

  const guardSeconds = Number.isFinite(Number(seconds))
    ? Math.max(10, Number(seconds))
    : SYNC_GUARD_DEFAULT_SECONDS;
  state.syncGuardBaseMessage = String(message || "脚本运行中，请勿操作浏览器中的平台标签页。").trim();
  state.syncGuardDeadline = Date.now() + guardSeconds * 1000;

  dom.syncGuardOverlay.classList.remove("hidden");
  dom.syncGuardOverlay.setAttribute("aria-hidden", "false");
  refreshSyncGuardCountdown();
  stopSyncGuardTimer();
  state.syncGuardTimer = setInterval(refreshSyncGuardCountdown, 1000);
}

function hideSyncGuardOverlay() {
  stopSyncGuardTimer();
  state.syncGuardDeadline = 0;
  state.syncGuardBaseMessage = "";

  if (!dom.syncGuardOverlay) {
    return;
  }

  dom.syncGuardOverlay.classList.add("hidden");
  dom.syncGuardOverlay.setAttribute("aria-hidden", "true");
  if (dom.syncGuardCountdown) {
    dom.syncGuardCountdown.textContent = "--";
  }
  if (dom.syncGuardMessage) {
    dom.syncGuardMessage.textContent = "脚本运行中，请勿操作浏览器中的平台标签页。";
  }
}

function hasTimeoutReport(syncReport) {
  const reports = Array.isArray(syncReport?.platformReports) ? syncReport.platformReports : [];
  return reports.some((item) => {
    const status = String(item?.status || "").toLowerCase();
    return status === "timeout" || status === "failed";
  });
}

function hasRetryableReport(syncReport) {
  const reports = Array.isArray(syncReport?.platformReports) ? syncReport.platformReports : [];
  return reports.some((item) => {
    const status = String(item?.status || "").toLowerCase();
    return status === "timeout" || status === "failed" || status === "manual";
  });
}

function hasRunningReport(syncReport) {
  const reports = Array.isArray(syncReport?.platformReports) ? syncReport.platformReports : [];
  return reports.some((item) => String(item?.status || "").toLowerCase() === "running");
}

function collectRetryTaskIds(syncReport) {
  const result = {
    携程: [],
    飞猪: [],
    美团: [],
  };

  const reports = Array.isArray(syncReport?.platformReports) ? syncReport.platformReports : [];
  reports.forEach((report) => {
    const platform = String(report?.platform || "");
    if (!Object.prototype.hasOwnProperty.call(result, platform)) {
      return;
    }

    const status = String(report?.status || "").toLowerCase();
    if (status !== "timeout" && status !== "failed" && status !== "manual") {
      return;
    }

    const ids = Array.isArray(report?.items)
      ? report.items
        .map((item) => String(item?.id || "").trim())
        .filter((id) => Boolean(id))
      : [];

    const fallbackIds = Array.isArray(report?.taskIds)
      ? report.taskIds
        .map((item) => String(item || "").trim())
        .filter((id) => Boolean(id))
      : [];

    const mergedIds = ids.length > 0 ? ids : fallbackIds;
    result[platform] = Array.from(new Set(mergedIds));
  });

  return result;
}

function findPlatformSyncReport(syncReport, platform) {
  const reports = Array.isArray(syncReport?.platformReports) ? syncReport.platformReports : [];
  return reports.find((item) => String(item?.platform || "") === platform) || null;
}

function collectPlatformActionDetails(syncReport, platform) {
  const report = findPlatformSyncReport(syncReport, platform);
  const items = Array.isArray(report?.items) ? report.items : [];
  const detailMap = new Map();

  items.forEach((item) => {
    const details = item && typeof item.details === "object" ? item.details : null;
    if (!details) {
      return;
    }

    const startDate = String(details.startDate || details.checkInDate || "").trim();
    let endDate = String(details.endDate || "").trim();
    if (!endDate) {
      const checkOutDate = String(details.checkOutDate || "").trim();
      if (checkOutDate) {
        endDate = addDays(checkOutDate, -1);
      }
    }
    if (!endDate) {
      endDate = startDate;
    }
    const quantityRaw = details.remainingQuantity;
    const quantity = Number.isFinite(Number(quantityRaw)) ? Number(quantityRaw) : null;

    if (!startDate && !endDate && quantity === null) {
      return;
    }

    const key = `${startDate}|${endDate}|${quantity ?? ""}`;
    if (detailMap.has(key)) {
      return;
    }

    detailMap.set(key, {
      startDate,
      endDate,
      quantity,
    });
  });

  return Array.from(detailMap.values());
}

function formatPlatformActionDetail(detail) {
  const rangeText = detail.startDate && detail.endDate
    ? `${detail.startDate} 至 ${detail.endDate}`
    : (detail.startDate || detail.endDate || "日期待确认");
  const qtyText = detail.quantity === null ? "房量待确认" : `房量 ${detail.quantity}`;
  return `时间段 ${rangeText}，${qtyText}`;
}

function collectGuideSummaryDetails(syncReport, targets) {
  const summaryMap = new Map();
  targets.forEach((platform) => {
    const details = collectPlatformActionDetails(syncReport, platform);
    details.forEach((detail) => {
      const key = `${detail.startDate}|${detail.endDate}|${detail.quantity ?? ""}`;
      if (!summaryMap.has(key)) {
        summaryMap.set(key, detail);
      }
    });
  });
  return Array.from(summaryMap.values());
}

function collectGuideSummaryMessages(syncReport, targets) {
  const messages = [];
  const seen = new Set();

  targets.forEach((platform) => {
    const report = findPlatformSyncReport(syncReport, platform);
    if (!report) {
      return;
    }

    const reportMessage = String(report.message || "").trim();
    if (reportMessage && !seen.has(reportMessage)) {
      seen.add(reportMessage);
      messages.push(reportMessage);
    }

    const items = Array.isArray(report.items) ? report.items : [];
    items.forEach((item) => {
      const itemMessage = String(item?.message || "").trim();
      if (!itemMessage || seen.has(itemMessage)) {
        return;
      }
      seen.add(itemMessage);
      messages.push(itemMessage);
    });
  });

  return messages;
}

function syncStatusText(platform, phase, sourcePlatform, syncReport) {
  if (platform === sourcePlatform && syncDisplayPlatforms.includes(sourcePlatform)) {
    return {
      text: "无需更新（当前下单平台）",
      className: "ok",
    };
  }

  if (phase === "running") {
    return { text: "更新中...", className: "" };
  }

  if (!syncReport || syncReport.enabled === false) {
    return { text: "自动同步未启用", className: "error" };
  }

  const platformReport = findPlatformSyncReport(syncReport, platform);
  if (!platformReport) {
    return { text: "出错了", className: "error" };
  }

  const status = String(platformReport.status || "").toLowerCase();
  if (status === "success") {
    return {
      text: Number(platformReport.success || 0) > 0
        ? `已提交 ${platformReport.success} 条`
        : "已提交",
      className: "ok",
    };
  }

  if (status === "queued") {
    return {
      text: platformReport.message || "待接入（已入队）",
      className: "ok",
    };
  }

  if (status === "noop" || status === "skipped") {
    return { text: platformReport.message || "无需更新", className: "ok" };
  }

  if (status === "manual") {
    return {
      text: "已预填非日期项，请按下方提示设置并提交",
      className: "",
    };
  }

  if (status === "running") {
    return {
      text: platformReport.message || "更新中...",
      className: "running",
    };
  }

  if (status === "timeout" || status === "failed") {
    return {
      text: "出错了",
      className: "error",
    };
  }

  return {
    text: "出错了",
    className: "error",
  };
}

function shouldShowLoginAction(platform, phase, syncReport) {
  if (phase !== "done") {
    return false;
  }

  const platformReport = findPlatformSyncReport(syncReport, platform);
  const status = String(platformReport?.status || "").toLowerCase();
  return status === "timeout" || status === "failed";
}

function collectGuidePlatforms(syncReport) {
  const reports = Array.isArray(syncReport?.platformReports) ? syncReport.platformReports : [];
  return reports
    .filter((item) => {
      const status = String(item?.status || "").toLowerCase();
      return status === "manual" || status === "running" || status === "timeout" || status === "failed";
    })
    .map((item) => String(item?.platform || "").trim())
    .filter((item) => syncDisplayPlatforms.includes(item));
}

function renderPlatformGuide(syncReport) {
  if (!dom.platformGuidePanel || !dom.platformGuideHint) {
    return;
  }

  const targets = collectGuidePlatforms(syncReport);
  const shouldShow = targets.length > 0;
  dom.platformGuidePanel.classList.toggle("hidden", !shouldShow);
  if (!shouldShow) {
    return;
  }

  dom.platformGuideHint.textContent = `待处理平台：${targets.join("、")}。点击按钮可一键切换标签。`;

  if (dom.platformGuideTasks) {
    const summaryDetails = collectGuideSummaryDetails(syncReport, targets);
    const summaryMessages = collectGuideSummaryMessages(syncReport, targets);
    const summaryText = summaryDetails.length
      ? summaryDetails.map((detail) => formatPlatformActionDetail(detail)).join("；")
      : (summaryMessages.join("；") || "请按页面提示手动处理。");
    dom.platformGuideTasks.innerHTML = `<div class="platform-guide-summary">${escapeHtml(summaryText)}</div>`;
  }

  const buttons = dom.platformGuidePanel.querySelectorAll("button[data-action='focus-platform-tab']");
  buttons.forEach((button) => {
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }

    const platform = String(button.getAttribute("data-platform") || "").trim();
    button.disabled = !targets.includes(platform);
  });
}

async function openPlatformTabs(options = {}) {
  const forceRestart = Boolean(options.forceRestart);
  const silent = Boolean(options.silent);
  const requestedPlatforms = Array.isArray(options.platforms) ? options.platforms : [];
  const platforms = [...new Set(
    requestedPlatforms
      .map((item) => platformKey(item))
      .filter((item) => item === "fliggy" || item === "ctrip" || item === "meituan")
  )];
  const targetPlatforms = platforms.length > 0 ? platforms : ["fliggy", "ctrip", "meituan"];
  const result = await requestJSON("/api/bootstrap/open-login-tabs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      platforms: targetPlatforms,
      forceRestart,
    }),
  });
  if (!silent) {
    showToast(result.message || "已按携程、飞猪、美团顺序打开平台页面");
  }
}

async function focusPlatformTab(platform, options = {}) {
  const silent = Boolean(options.silent);
  const result = await requestJSON("/api/bootstrap/focus-platform-tab", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      platform,
      openIfMissing: true,
    }),
  });
  if (!silent) {
    showToast(result.message || `已切换到${platform}`);
  }
}

function waitMs(ms) {
  const delay = Math.max(0, Number(ms) || 0);
  return new Promise((resolve) => {
    setTimeout(resolve, delay);
  });
}

async function ensurePlatformTabFocused(platform) {
  const normalizedPlatform = platformKey(platform);
  if (normalizedPlatform === "direct") {
    throw new Error("平台参数无效，无法切换标签");
  }

  if (state.platformFocusBusy) {
    throw new Error("正在切换平台标签，请稍候再试");
  }

  state.platformFocusBusy = true;

  let lastError = null;

  try {
    for (let i = 0; i < 8; i += 1) {
      if (i > 0) {
        await waitMs(420);
      }
      try {
        await focusPlatformTab(normalizedPlatform, { silent: i < 7 });
        return;
      } catch (error) {
        lastError = error;

        const message = String(error && error.message ? error.message : "");
        if (message.includes("未检测到可复用浏览器")) {
          throw new Error("未检测到可复用浏览器，请先点击“重新打开平台标签”");
        }
      }
    }

    throw lastError || new Error("切换失败，请点击跳转重新打开平台标签");
  } finally {
    state.platformFocusBusy = false;
  }
}

function stopAsyncSyncPolling() {
  if (state.asyncSyncPollingTimer) {
    clearInterval(state.asyncSyncPollingTimer);
    state.asyncSyncPollingTimer = null;
  }
  state.asyncSyncJobId = "";
  state.asyncSyncPollingBusy = false;
  hideSyncGuardOverlay();
}

async function pollAsyncSyncProgress(sourcePlatform, jobId) {
  if (state.asyncSyncPollingBusy) {
    return;
  }
  state.asyncSyncPollingBusy = true;

  try {
    const result = await requestJSON(`/api/sync/progress/${encodeURIComponent(jobId)}`);
    const syncReport = result.syncReport || null;
    finishSyncProgress(sourcePlatform, syncReport);

    const noRunningPlatform = Boolean(syncReport) && !hasRunningReport(syncReport);
    if (Boolean(result.completed) || noRunningPlatform) {
      stopAsyncSyncPolling();
      showToast(adjustSuccessMessage(syncReport));
    }
  } catch (error) {
    stopAsyncSyncPolling();
    showToast(`平台同步进度获取失败：${error.message}`, true);
  } finally {
    state.asyncSyncPollingBusy = false;
  }
}

function startAsyncSyncPolling(sourcePlatform, jobId) {
  const targetJobId = String(jobId || "").trim();
  if (!targetJobId) {
    return;
  }

  stopAsyncSyncPolling();
  state.asyncSyncJobId = targetJobId;
  void pollAsyncSyncProgress(sourcePlatform, targetJobId);
  state.asyncSyncPollingTimer = setInterval(() => {
    void pollAsyncSyncProgress(sourcePlatform, targetJobId);
  }, ASYNC_SYNC_POLL_MS);
}

function renderSyncProgressRows(sourcePlatform, phase = "running", syncReport = null) {
  const html = syncDisplayPlatforms
    .map((platform) => {
      const status = syncStatusText(platform, phase, sourcePlatform, syncReport);
      const statusClass = status.className ? `sync-progress-status ${status.className}` : "sync-progress-status";
      const showLoginAction = shouldShowLoginAction(platform, phase, syncReport);

      const statusNode = showLoginAction
        ? `<button type="button" class="sync-progress-status-btn error" data-action="open-platform-login" data-platform="${escapeHtml(platform)}">${escapeHtml(`${status.text}（点击跳转）`)}</button>`
        : `<span class="${statusClass}">${escapeHtml(status.text)}</span>`;

      return `
        <div class="sync-progress-item">
          <span class="sync-progress-name">${escapeHtml(platform)}</span>
          ${statusNode}
        </div>
      `;
    })
    .join("");

  dom.syncProgressList.innerHTML = html;
}

function openSyncProgress(sourcePlatform) {
  stopAsyncSyncPolling();
  dom.syncProgressTitle.textContent = "平台更新中";
  dom.syncProgressSpinner.classList.remove("hidden");
  dom.retrySyncBtn.classList.add("hidden");
  if (dom.giveUpSyncBtn) {
    dom.giveUpSyncBtn.classList.add("hidden");
  }
  if (dom.platformGuidePanel) {
    dom.platformGuidePanel.classList.add("hidden");
  }
  setSyncActionButtonsBusy("");
  showSyncGuardOverlay("脚本运行中，请勿操作浏览器中的平台标签页。", SYNC_GUARD_DEFAULT_SECONDS);
  renderSyncProgressRows(sourcePlatform, "running", null);
  openModal(dom.syncProgressModal);
}

function finishSyncProgress(sourcePlatform, syncReport) {
  state.lastSyncSourcePlatform = sourcePlatform;
  state.lastSyncReport = syncReport;

  const running = hasRunningReport(syncReport);

  dom.syncProgressTitle.textContent = running ? "平台更新中（部分已完成）" : "平台更新结果";
  dom.syncProgressSpinner.classList.toggle("hidden", !running);
  renderSyncProgressRows(sourcePlatform, "done", syncReport);
  renderPlatformGuide(syncReport);

  if (running) {
    showSyncGuardOverlay("脚本仍在运行，请勿操作浏览器中的平台标签页。", SYNC_GUARD_DEFAULT_SECONDS);
  } else {
    hideSyncGuardOverlay();
  }

  const showRetry = !running && hasRetryableReport(syncReport);
  setSyncActionButtonsBusy("");
  dom.retrySyncBtn.classList.toggle("hidden", !showRetry);
  if (dom.giveUpSyncBtn) {
    dom.giveUpSyncBtn.classList.toggle("hidden", !showRetry);
  }
}

function buildTimeoutSyncReport(sourcePlatform, message = "同步超时") {
  const platformReports = syncDisplayPlatforms.map((platform) => {
    if (platform === sourcePlatform) {
      return {
        platform,
        status: "skipped",
        message: "无需更新（当前下单平台）",
      };
    }
    return {
      platform,
      status: "timeout",
      message,
    };
  });

  return {
    enabled: true,
    platformReports,
  };
}

function adjustSuccessMessage(syncReport) {
  if (!syncReport || syncReport.enabled === false) {
    return "调整成功，自动平台同步未启用";
  }

  const reports = Array.isArray(syncReport.platformReports) ? syncReport.platformReports : [];
  const firstHardFailure = reports.find((item) => {
    const status = String(item?.status || "").toLowerCase();
    return status === "failed";
  });

  if (firstHardFailure) {
    return "调整成功，但平台同步失败";
  }

  const hasTimeout = reports.some((item) => {
    const status = String(item?.status || "").toLowerCase();
    return status === "timeout" || status === "failed";
  });

  if (hasTimeout) {
    return "调整成功，但平台同步超时";
  }

  const hasSuccess = reports.some((item) => String(item?.status || "").toLowerCase() === "success");
  if (hasSuccess) {
    return "调整成功，平台修改已提交";
  }

  const hasManual = reports.some((item) => String(item?.status || "").toLowerCase() === "manual");
  if (hasManual) {
    return "调整成功，部分平台已预填，需手动改日期后提交";
  }

  const hasQueued = reports.some((item) => String(item?.status || "").toLowerCase() === "queued");
  if (hasQueued) {
    return "调整成功，部分平台待接入";
  }

  return "调整成功，无需更新";
}

async function runSyncRetryAction(retryMode = "auto") {
  if (state.isRetrying) {
    return;
  }

  const sourcePlatform = state.lastSyncSourcePlatform;
  const syncReport = state.lastSyncReport;
  if (!sourcePlatform || !syncReport) {
    return;
  }

  const platformTaskIds = collectRetryTaskIds(syncReport);
  const totalRetry = Object.values(platformTaskIds).reduce((sum, ids) => sum + ids.length, 0);
  if (totalRetry <= 0) {
    showToast("没有可处理的任务，请先刷新后重试", true);
    return;
  }

  const normalizedMode = String(retryMode || "auto").trim().toLowerCase();
  const fallbackMode = normalizedMode === "manual_fallback";

  state.isRetrying = true;
  setSyncActionButtonsBusy(fallbackMode ? "giveup" : "retry");
  dom.syncProgressTitle.textContent = fallbackMode ? "平台切换备用方案中" : "平台重试中";
  dom.syncProgressSpinner.classList.remove("hidden");
  showSyncGuardOverlay(
    fallbackMode
      ? "已切换到备用处理流程，请勿操作浏览器中的平台标签页。"
      : "正在重试自动同步，请勿操作浏览器中的平台标签页。",
    SYNC_GUARD_RETRY_SECONDS,
  );

  try {
    const result = await requestJSON("/api/sync/retry", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sourcePlatform,
        platformTaskIds,
        retryMode: fallbackMode ? "manual_fallback" : "auto",
      }),
    });

    const nextReport = result.syncReport || null;
    finishSyncProgress(sourcePlatform, nextReport);

    if (fallbackMode) {
      const reports = Array.isArray(nextReport?.platformReports) ? nextReport.platformReports : [];
      const hasManual = reports.some((item) => String(item?.status || "").toLowerCase() === "manual");
      if (hasManual) {
        showToast("已切换备用方案，请按下方引导手动设置日期并提交");
      } else {
        showToast(adjustSuccessMessage(nextReport));
      }
    } else {
      showToast(adjustSuccessMessage(nextReport));
    }
  } catch (error) {
    dom.syncProgressSpinner.classList.add("hidden");
    setSyncActionButtonsBusy("");
    hideSyncGuardOverlay();
    showToast(error.message || "出错了", true);
  } finally {
    state.isRetrying = false;
  }
}


function normalizeDateInputElementValue(inputEl) {
  if (!(inputEl instanceof HTMLInputElement)) {
    return "";
  }

  const raw = String(inputEl.value || "").trim();
  if (!raw) {
    inputEl.value = "";
    return "";
  }

  const normalized = normalizeFlexibleDateInput(raw);
  if (normalized) {
    if (inputEl.value !== normalized) {
      inputEl.value = normalized;
    }
    return normalized;
  }

  return "";
}

function clearCheckOutDateValidation() {
  const checkOutInput = dom.adjustForm.elements.checkOutDate;
  if (!(checkOutInput instanceof HTMLInputElement)) {
    return;
  }
  checkOutInput.classList.remove("field-invalid");
  checkOutInput.removeAttribute("aria-invalid");
  checkOutInput.setCustomValidity("");
}

function setCheckOutDateValidation(message) {
  const checkOutInput = dom.adjustForm.elements.checkOutDate;
  if (!(checkOutInput instanceof HTMLInputElement)) {
    return;
  }
  checkOutInput.classList.add("field-invalid");
  checkOutInput.setAttribute("aria-invalid", "true");
  checkOutInput.setCustomValidity(message);
}

function validateAdjustDateRange(options = {}) {
  const { showToastOnError = false } = options;

  const checkInInput = dom.adjustForm.elements.checkInDate;
  const checkOutInput = dom.adjustForm.elements.checkOutDate;
  const checkInDate = normalizeDateInputElementValue(checkInInput);
  const checkOutDate = normalizeDateInputElementValue(checkOutInput);

  clearCheckOutDateValidation();

  const hasRawCheckIn = String(checkInInput?.value || "").trim().length > 0;
  const hasRawCheckOut = String(checkOutInput?.value || "").trim().length > 0;

  if ((hasRawCheckIn && !checkInDate) || (hasRawCheckOut && !checkOutDate)) {
    if (showToastOnError) {
      showToast("日期格式请使用 YYYY-MM-DD 或 YYYYMMDD", true);
    }
    return {
      ok: false,
      checkInDate,
      checkOutDate,
    };
  }

  if (!checkInDate || !checkOutDate) {
    return {
      ok: false,
      checkInDate,
      checkOutDate,
    };
  }

  if (checkOutDate <= checkInDate) {
    const message = "离店日期必须晚于到店日期";
    setCheckOutDateValidation(message);
    if (showToastOnError) {
      showToast(message, true);
    }
    return {
      ok: false,
      checkInDate,
      checkOutDate,
    };
  }

  return {
    ok: true,
    checkInDate,
    checkOutDate,
  };
}

function getDefaultAdjustDateRange() {
  const checkInDate = todayString();
  return {
    checkInDate,
    checkOutDate: addDays(checkInDate, 1),
  };
}

function maybeClearDateInputOnFocus(inputEl) {
  if (!(inputEl instanceof HTMLInputElement)) {
    return;
  }

  const fieldName = String(inputEl.name || "").trim();
  if (fieldName !== "checkInDate" && fieldName !== "checkOutDate") {
    return;
  }

  const raw = String(inputEl.value || "").trim();
  if (!raw) {
    return;
  }

  inputEl.value = "";
  if (fieldName === "checkOutDate") {
    clearCheckOutDateValidation();
  }
}

function restoreDateInputDefaultIfEmpty(inputEl) {
  if (!(inputEl instanceof HTMLInputElement)) {
    return false;
  }

  const fieldName = String(inputEl.name || "").trim();
  if (fieldName !== "checkInDate" && fieldName !== "checkOutDate") {
    return false;
  }

  const raw = String(inputEl.value || "").trim();
  if (raw) {
    return false;
  }

  const defaults = getDefaultAdjustDateRange();
  const fallback = fieldName === "checkInDate"
    ? defaults.checkInDate
    : defaults.checkOutDate;

  inputEl.value = fallback;
  if (fieldName === "checkOutDate") {
    clearCheckOutDateValidation();
  }
  return true;
}


function getAdjustStatus() {
  return dom.adjustForm.elements.status.value;
}

function parsePositiveInt(rawValue, fallback = 1, max = 50) {
  const parsed = Number.parseInt(String(rawValue || ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.min(parsed, max);
}

function hasSelectOption(selectEl, targetValue) {
  if (!(selectEl instanceof HTMLSelectElement)) {
    return false;
  }

  return Array.from(selectEl.options).some((opt) => String(opt.value || "") === String(targetValue || ""));
}

function setDefaultSourcePlatform() {
  const select = dom.adjustForm.elements.platform;
  if (!(select instanceof HTMLSelectElement)) {
    return;
  }

  if (hasSelectOption(select, "自接")) {
    select.value = "自接";
  }
}

function isLocalOnlyRoomType(roomTypeName) {
  const target = String(roomTypeName || "").trim();
  if (!target) {
    return false;
  }
  const localOnlySet = new Set(
    (Array.isArray(state.localOnlyRoomTypes) ? state.localOnlyRoomTypes : [])
      .map((item) => String(item || "").trim())
      .filter((item) => Boolean(item))
  );
  return localOnlySet.has(target);
}

function getRoomTypesForPlatform(platformName) {
  const platform = String(platformName || "").trim();
  if (platform === "自接" || platform === "抖音") {
    return state.roomTypes.slice();
  }
  return state.roomTypes.filter((item) => !isLocalOnlyRoomType(item?.name));
}

function refreshRoomTypeOptionsByPlatform(preferredRoomType = "") {
  const roomTypeSelect = dom.adjustForm.elements.roomType;
  if (!(roomTypeSelect instanceof HTMLSelectElement)) {
    return;
  }

  const keepValue = String(preferredRoomType || roomTypeSelect.value || "").trim();
  const platform = String(dom.adjustForm.elements.platform.value || "").trim();
  const visibleRoomTypes = getRoomTypesForPlatform(platform);

  fillSelect(dom.adjustForm, "roomType", visibleRoomTypes);

  if (keepValue && hasSelectOption(roomTypeSelect, keepValue)) {
    roomTypeSelect.value = keepValue;
    return;
  }

  if (visibleRoomTypes.length > 0) {
    roomTypeSelect.value = String(visibleRoomTypes[0].name || "");
    return;
  }

  roomTypeSelect.value = "";
}

function getSelectedBookingOption() {
  const select = dom.adjustForm.elements.bookingId;
  const selected = select.options[select.selectedIndex];
  if (!selected || !selected.value) {
    return null;
  }
  return selected;
}

function parseBookingOptionRoomIds(optionEl) {
  const raw = String(optionEl?.dataset?.roomIds || "[]");
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .map((item) => String(item || "").trim())
      .filter((item) => Boolean(item));
  } catch {
    return [];
  }
}

function collectSelectedRoomIds() {
  const selects = dom.roomPickerList.querySelectorAll("select[data-room-slot]");
  return Array.from(selects)
    .map((el) => (el instanceof HTMLSelectElement ? el.value.trim() : ""))
    .filter((value) => Boolean(value));
}

function syncAdjustModeUI() {
  const status = getAdjustStatus();
  const bookingIdSelect = dom.adjustForm.elements.bookingId;
  const quantityInput = dom.adjustForm.elements.quantity;

  const isBooking = status === "预订";
  const isCancel = status === "取消";
  const isModify = status === "修改";

  dom.bookingIdLabel.classList.toggle("hidden", isBooking);
  dom.quantityLabel.classList.toggle("hidden", !isBooking);
  dom.roomPickerSection.classList.toggle("hidden", isCancel);
  dom.bookingIdTitle.textContent = isModify ? "修改订单" : "取消订单";

  bookingIdSelect.required = !isBooking;
  bookingIdSelect.disabled = isBooking;

  quantityInput.required = isBooking;
  quantityInput.disabled = !isBooking;

  if (isBooking) {
    quantityInput.value = String(parsePositiveInt(quantityInput.value, 1));
    state.pendingPreferredRoomIds = [];
  } else if (!quantityInput.value) {
    quantityInput.value = "1";
  }
}

function fillSelect(formEl, selectName, values) {
  const select = formEl.elements[selectName];
  select.innerHTML = "";

  values.forEach((value) => {
    const opt = document.createElement("option");
    if (typeof value === "string") {
      opt.value = value;
      opt.textContent = value;
    } else {
      opt.value = value.name;
      opt.textContent = `${value.name}（总量 ${value.total}）`;
    }
    select.appendChild(opt);
  });
}

function findRoomTypeTotal(roomTypeName) {
  const hit = state.roomTypes.find((item) => item.name === roomTypeName);
  if (!hit) {
    return null;
  }
  const total = Number(hit.total);
  return Number.isFinite(total) ? total : null;
}

function formatLegacyChanges(changes) {
  const entries = Object.entries(changes || {});
  if (!entries.length) {
    return "-";
  }

  return entries
    .map(([platform, value]) => `${platform} ${value.before}→${value.after}`)
    .join(" | ");
}

function historyDateText(item) {
  if (item.type && item.type.includes("初始化")) {
    return "全局重算";
  }

  const checkIn = item.checkInDate || item.startDate;
  const checkOut = item.checkOutDate || item.endDate;

  if (checkIn && checkOut) {
    return `${checkIn} 入住 / ${checkOut} 离店`;
  }

  if (item.date) {
    return item.date;
  }

  return "-";
}

function historySourceText(item) {
  if (item.type && item.type.includes("初始化")) {
    return "本地系统";
  }
  return item.sourcePlatform || "-";
}

function historyModeText(item) {
  if (item.type && item.type.includes("初始化")) {
    return "初始化";
  }
  return item.status || "-";
}

function historyChangeText(item) {
  if (item.type && item.type.includes("初始化")) {
    const nights = item.affectedNights || item.nights || Object.keys(item.dailyChanges || {}).length;
    const syncText = item.syncRequested
      ? "已生成平台同步任务"
      : "未生成平台同步任务（默认你已手动改好）";
    return `总房量设为 ${item.quantity}（按订单重算可售）；${syncText}${nights ? `（${nights}天）` : ""}`;
  }

  if (item.dailyChanges) {
    const dates = Object.keys(item.dailyChanges);
    if (!dates.length) {
      return "-";
    }
    const first = item.dailyChanges[dates[0]];
    const platformPart = Object.entries(first.platforms || {})
      .map(([platform, value]) => `${platform} ${value.before}→${value.after}`)
      .join(" | ");
    const nights = item.nights || dates.length;
    const roomNumbers = Array.isArray(item.roomNumbers)
      ? item.roomNumbers.filter((value) => String(value || "").trim())
      : [];
    const roomText = roomNumbers.length
      ? `；房号 ${roomNumbers.join(",")}`
      : (item.roomNumber ? `；房号 ${item.roomNumber}` : "");
    return `本地 ${first.local.before}→${first.local.after}；${platformPart}${nights ? `（${nights}晚）` : ""}${roomText}`;
  }

  if (item.changes) {
    return formatLegacyChanges(item.changes);
  }

  return "-";
}

function renderHistory(items) {
  dom.historyTableBody.innerHTML = "";

  if (!items.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="7">暂无操作记录</td>';
    dom.historyTableBody.appendChild(tr);
    return;
  }

  items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(item.createdAt || "-")}</td>
      <td>${escapeHtml(historyDateText(item))}</td>
      <td>${escapeHtml(item.roomType || "-")}</td>
      <td>${escapeHtml(historySourceText(item))}</td>
      <td>${escapeHtml(historyModeText(item))}</td>
      <td>${escapeHtml(item.quantity ?? "-")}</td>
      <td>${escapeHtml(historyChangeText(item))}</td>
    `;
    dom.historyTableBody.appendChild(tr);
  });
}


function renderBookingDetailList(items, roomType, targetDate, stageLabel = "") {
  if (!items.length) {
    dom.bookingDetailContent.innerHTML = `<div class="calendar-empty">${escapeHtml(targetDate)} ${escapeHtml(roomType)} 暂无${escapeHtml(stageLabel || "订单")}详情</div>`;
    return;
  }

  const header = `
    <div class="booking-detail-head">
      <strong>${escapeHtml(roomType)}</strong>
      <span>${escapeHtml(targetDate)}${stageLabel ? ` · ${escapeHtml(stageLabel)}` : ""}</span>
    </div>
  `;

  const rows = items
    .map((item) => {
      const roomText = item.roomNumber ? `房号 ${item.roomNumber}` : "未分配房号";
      return `
        <div class="booking-detail-item">
          <div class="booking-detail-main">${escapeHtml(item.platform)} ${escapeHtml(item.stage)}${escapeHtml(item.quantity)}</div>
          <div class="booking-detail-sub">${escapeHtml(item.checkInDate)}~${escapeHtml(item.checkOutDate)} · ${escapeHtml(roomText)}</div>
        </div>
      `;
    })
    .join("");

  dom.bookingDetailContent.innerHTML = `${header}<div class="booking-detail-items">${rows}</div>`;
}

function renderCalendar(data) {
  const rows = data.rows || [];
  const dates = data.dates || [];

  if (!rows.length || !dates.length) {
    dom.inventoryCalendar.innerHTML = '<div class="calendar-empty">暂无可展示库存数据</div>';
    return;
  }

  const headerCells = dates
    .map(
      (day) => `
      <th class="calendar-header-day">
        <span class="calendar-weekday">${escapeHtml(day.weekday)}</span>
        <span class="calendar-date">${escapeHtml(day.label)}</span>
      </th>
    `
    )
    .join("");

  const bodyRows = rows
    .map((row) => {
      const dayCells = row.cells
        .map((cell) => {
          const bookingEntries = Object.entries(cell.bookings || {});
          const bookingNodes = [];
          let stayTotal = 0;

          bookingEntries.forEach(([platform, stats]) => {
            let newCount = 0;
            let stayCount = 0;

            if (typeof stats === "number") {
              newCount = Number(stats) || 0;
            } else {
              newCount = Number(stats.new || 0);
              stayCount = Number(stats.stay || 0);
            }

            if (newCount > 0) {
              const key = platformKey(platform);
              bookingNodes.push(
                `<button type="button" class="calendar-booking-item badge-new-${key}" data-action="open-cancel" data-room-type="${escapeHtml(row.roomType)}" data-platform="${escapeHtml(platform)}" data-date="${escapeHtml(cell.date)}">${escapeHtml(`${platform}新${newCount}`)}</button>`
              );
            }

            if (stayCount > 0) {
              stayTotal += stayCount;
            }
          });

          if (stayTotal > 0) {
            bookingNodes.push(
              `<button type="button" class="calendar-booking-item badge-stay" data-action="open-booking-detail" data-room-type="${escapeHtml(row.roomType)}" data-date="${escapeHtml(cell.date)}" data-stage="续">续${escapeHtml(stayTotal)}</button>`
            );
          }

          const bookingHtml = bookingNodes.join("");

          return `
            <td>
              <div class="calendar-cell">
                <div class="calendar-remain">
                  <span class="calendar-remain-label">剩</span>
                  <span class="calendar-remain-num">${escapeHtml(cell.remaining)}</span>
                </div>
                <div class="calendar-bookings">${bookingHtml}</div>
              </div>
            </td>
          `;
        })
        .join("");

      return `
        <tr>
          <td class="calendar-room-col">
            <button type="button" class="calendar-room" data-action="open-set-total" data-room-type="${escapeHtml(row.roomType)}" data-total="${escapeHtml(row.total)}">
              <div class="calendar-room-name">${escapeHtml(row.roomType)}</div>
              <div class="calendar-room-total">总房量 ${row.total}</div>
            </button>
          </td>
          ${dayCells}
        </tr>
      `;
    })
    .join("");

  dom.inventoryCalendar.innerHTML = `
    <table class="calendar-table">
      <thead>
        <tr>
          <th class="calendar-room-col">房型</th>
          ${headerCells}
        </tr>
      </thead>
      <tbody>
        ${bodyRows}
      </tbody>
    </table>
  `;
}


function renderBookingOptions(items, status, selectedValue = "") {
  const select = dom.adjustForm.elements.bookingId;
  select.innerHTML = "";

  if (!items.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = status === "修改" ? "暂无可修改订单" : "暂无可取消订单";
    select.appendChild(opt);
    return;
  }

  items.forEach((item) => {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = item.label;
    opt.dataset.checkInDate = item.checkInDate || "";
    opt.dataset.checkOutDate = item.checkOutDate || "";
    opt.dataset.available = String(item.available ?? 1);
    opt.dataset.quantity = String(item.quantity ?? item.available ?? 1);
    opt.dataset.roomIds = JSON.stringify(item.roomIds || []);
    select.appendChild(opt);
  });

  if (selectedValue && items.some((item) => item.id === selectedValue)) {
    select.value = selectedValue;
  } else {
    select.value = items[0].id;
  }
}


function renderRoomPickers(items, slotCount, selectedRoomIds = []) {
  dom.roomPickerList.innerHTML = "";
  if (slotCount <= 0) {
    return;
  }

  const validIds = new Set(items.map((item) => String(item.id || "")));
  const presetValues = Array.isArray(selectedRoomIds)
    ? selectedRoomIds.slice(0, slotCount)
    : [];

  for (let index = 0; index < slotCount; index += 1) {
    const wrapper = document.createElement("label");
    wrapper.className = "room-picker-item";

    const title = document.createElement("span");
    title.textContent = `房号${index + 1}`;

    const select = document.createElement("select");
    select.setAttribute("data-room-slot", String(index));

    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "自动分配";
    select.appendChild(emptyOption);

    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = String(item.id || "");
      option.textContent = `${item.floorName}-${item.number}`;
      select.appendChild(option);
    });

    const preset = String(presetValues[index] || "").trim();
    select.value = preset && validIds.has(preset) ? preset : "";

    wrapper.appendChild(title);
    wrapper.appendChild(select);
    dom.roomPickerList.appendChild(wrapper);
  }

  if (!items.length) {
    const note = document.createElement("div");
    note.className = "form-note";
    note.textContent = "当前日期范围暂无可选房号，可留空由系统自动分配。";
    dom.roomPickerList.appendChild(note);
  }
}


function applySelectedBookingToForm({ forceDates = false } = {}) {
  const status = getAdjustStatus();
  if (status !== "取消" && status !== "修改") {
    return;
  }

  const selectedOption = getSelectedBookingOption();
  if (!selectedOption) {
    state.pendingPreferredRoomIds = [];
    return;
  }

  const checkInDate = selectedOption.dataset.checkInDate || "";
  const checkOutDate = selectedOption.dataset.checkOutDate || "";

  if (
    status === "取消"
    || forceDates
    || !dom.adjustForm.elements.checkInDate.value
    || !dom.adjustForm.elements.checkOutDate.value
  ) {
    if (checkInDate) {
      dom.adjustForm.elements.checkInDate.value = checkInDate;
    }
    if (checkOutDate) {
      dom.adjustForm.elements.checkOutDate.value = checkOutDate;
    }
  }

  if (status === "取消") {
    dom.adjustForm.elements.quantity.value = "1";
    state.pendingPreferredRoomIds = [];
    return;
  }

  if (forceDates || collectSelectedRoomIds().length === 0) {
    state.pendingPreferredRoomIds = parseBookingOptionRoomIds(selectedOption);
  }
  dom.adjustForm.elements.quantity.value = String(
    parsePositiveInt(selectedOption.dataset.quantity || "1", 1)
  );
}


function getDesiredRoomSlotCount() {
  const status = getAdjustStatus();
  if (status === "取消") {
    return 0;
  }

  if (status === "修改") {
    const option = getSelectedBookingOption();
    if (!option) {
      return 0;
    }
    return parsePositiveInt(option.dataset.quantity || "1", 1);
  }

  return parsePositiveInt(dom.adjustForm.elements.quantity.value, 1);
}


function getRoomPickerSelectionsForRender(slotCount) {
  if (slotCount <= 0) {
    state.pendingPreferredRoomIds = [];
    return [];
  }

  if (state.pendingPreferredRoomIds.length) {
    const fromBooking = state.pendingPreferredRoomIds.slice(0, slotCount);
    state.pendingPreferredRoomIds = [];
    return fromBooking;
  }

  return collectSelectedRoomIds().slice(0, slotCount);
}


async function refreshBookingOptionsIfNeeded() {
  const status = getAdjustStatus();

  if (status === "预订") {
    renderBookingOptions([], status);
    return;
  }

  const roomType = dom.adjustForm.elements.roomType.value;
  const platform = dom.adjustForm.elements.platform.value;

  if (!roomType || !platform) {
    renderBookingOptions([], status);
    return;
  }

  const bookingSelect = dom.adjustForm.elements.bookingId;
  const previousValue = bookingSelect.value;

  try {
    let items = [];

    if (status === "取消") {
      const checkInDate = normalizeDateInputElementValue(dom.adjustForm.elements.checkInDate);
      const checkOutDate = normalizeDateInputElementValue(dom.adjustForm.elements.checkOutDate);

      if (!checkInDate || !checkOutDate) {
        renderBookingOptions([], status);
        return;
      }

      if (checkOutDate <= checkInDate) {
        renderBookingOptions([], status);
        return;
      }

      const query = new URLSearchParams({
        roomType,
        platform,
        checkInDate,
        checkOutDate,
      }).toString();
      const data = await requestJSON(`/api/cancel-options?${query}`);
      items = data.items || [];
    } else {
      const query = new URLSearchParams({ roomType, platform }).toString();
      const data = await requestJSON(`/api/modify-options?${query}`);
      items = data.items || [];
    }

    renderBookingOptions(items, status, previousValue);

    const selectedValue = bookingSelect.value;
    const shouldForceDates = status === "取消" || selectedValue !== previousValue;
    applySelectedBookingToForm({ forceDates: shouldForceDates });
  } catch (error) {
    renderBookingOptions([], status);
    showToast(error.message, true);
  }
}


async function refreshRoomOptionsIfNeeded() {
  const status = getAdjustStatus();
  const slotCount = getDesiredRoomSlotCount();

  if (status === "取消") {
    renderRoomPickers([], 0, []);
    return;
  }

  if (slotCount <= 0) {
    dom.roomPickerList.innerHTML = '<div class="form-note">请选择订单后再调整房号。</div>';
    return;
  }

  const roomType = dom.adjustForm.elements.roomType.value;
  const checkInDate = normalizeDateInputElementValue(dom.adjustForm.elements.checkInDate);
  const checkOutDate = normalizeDateInputElementValue(dom.adjustForm.elements.checkOutDate);
  const selectedRoomIds = getRoomPickerSelectionsForRender(slotCount);

  if (!roomType || !checkInDate || !checkOutDate) {
    renderRoomPickers([], slotCount, selectedRoomIds);
    return;
  }

  if (checkOutDate <= checkInDate) {
    renderRoomPickers([], slotCount, selectedRoomIds);
    return;
  }

  const query = new URLSearchParams({
    roomType,
    checkInDate,
    checkOutDate,
  });

  if (status === "修改") {
    const bookingId = dom.adjustForm.elements.bookingId.value;
    if (bookingId) {
      query.set("excludeBookingId", bookingId);
    }
  }

  try {
    const data = await requestJSON(`/api/available-rooms?${query.toString()}`);
    renderRoomPickers(data.items || [], slotCount, selectedRoomIds);
  } catch (error) {
    renderRoomPickers([], slotCount, selectedRoomIds);
    showToast(error.message, true);
  }
}


async function refreshAdjustDependencies() {
  syncAdjustModeUI();
  await refreshBookingOptionsIfNeeded();
  await refreshRoomOptionsIfNeeded();
}

async function loadMeta() {
  const previousPlatform = String(dom.adjustForm.elements.platform.value || "").trim();
  const previousRoomType = String(dom.adjustForm.elements.roomType.value || "").trim();

  const data = await requestJSON("/api/meta");
  state.platforms = data.platforms;
  state.statuses = data.statuses;
  state.roomTypes = data.roomTypes;
  if (Array.isArray(data.localOnlyRoomTypes)) {
    state.localOnlyRoomTypes = data.localOnlyRoomTypes;
  }

  showDataHealthAlertIfNeeded(data.dataHealthAlert);

  fillSelect(dom.adjustForm, "platform", state.platforms);
  fillSelect(dom.adjustForm, "status", state.statuses);

  if (previousPlatform && hasSelectOption(dom.adjustForm.elements.platform, previousPlatform)) {
    dom.adjustForm.elements.platform.value = previousPlatform;
  } else {
    setDefaultSourcePlatform();
  }

  refreshRoomTypeOptionsByPlatform(previousRoomType);
}

async function loadCalendar() {
  const targetDate = dom.viewDate.value;
  const query = `date=${encodeURIComponent(targetDate)}&days=${state.calendarWindowDays}`;
  const data = await requestJSON(`/api/calendar?${query}`);
  renderCalendar(data);

  const first = data.dates[0]?.date || targetDate;
  const last = data.dates[data.dates.length - 1]?.date || targetDate;
  dom.inventoryHint.textContent = `窗口：${first} 至 ${last}（${data.dates.length}天）`;
}

async function loadHistory() {
  const data = await requestJSON("/api/history?limit=10");
  renderHistory(data.items);
}

async function submitInitLocal(event) {
  event.preventDefault();

  const needSync = window.confirm(
    "是否需要同步平台？\n\n点击【确定】：生成平台同步任务（后续功能执行）\n点击【取消】：默认你已在平台手动修改完成"
  );

  const payload = {
    roomType: dom.initForm.elements.roomType.value,
    quantity: Number(dom.initForm.elements.quantity.value),
    syncPlatforms: needSync,
  };

  if (needSync) {
    openSyncProgress("本地系统");
  }

  let result = null;
  try {
    result = await requestJSON("/api/init-local", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    await loadMeta();
    await loadCalendar();
    await loadHistory();
    closeModal(dom.initModal);

    if (needSync) {
      const nextReport = result.syncReport || null;
      finishSyncProgress("本地系统", nextReport);
      const asyncJobId = String(result.asyncSyncJobId || "").trim();
      if (asyncJobId) {
        showToast("平台将按顺序逐个同步，请勿操作平台标签页。");
        startAsyncSyncPolling("本地系统", asyncJobId);
        return;
      }
      stopAsyncSyncPolling();
      showToast(adjustSuccessMessage(nextReport));
    } else {
      showToast("总房量设置完成，默认你已在平台手动改好");
    }
  } catch (error) {
    stopAsyncSyncPolling();
    hideSyncGuardOverlay();
    if (needSync) {
      closeModal(dom.syncProgressModal);
    }
    showToast(error.message, true);
  }
}

async function submitAdjustment(event) {
  event.preventDefault();

  const status = getAdjustStatus();
  if (status === "取消" || status === "修改") {
    applySelectedBookingToForm();
  }

  const dateValidation = validateAdjustDateRange({ showToastOnError: true });
  if (!dateValidation.ok) {
    const checkOutInput = dom.adjustForm.elements.checkOutDate;
    if (checkOutInput instanceof HTMLInputElement) {
      checkOutInput.reportValidity();
    }
    return;
  }

  const bookingId = dom.adjustForm.elements.bookingId.value;
  const quantity = parsePositiveInt(dom.adjustForm.elements.quantity.value, 1);
  const selectedRoomIds = collectSelectedRoomIds();
  const uniqueRoomIds = Array.from(new Set(selectedRoomIds));

  if (uniqueRoomIds.length !== selectedRoomIds.length) {
    showToast("同一订单中房号不能重复选择", true);
    return;
  }

  const payload = {
    checkInDate: dateValidation.checkInDate,
    checkOutDate: dateValidation.checkOutDate,
    roomType: dom.adjustForm.elements.roomType.value,
    platform: dom.adjustForm.elements.platform.value,
    status,
    quantity: status === "预订" ? quantity : (status === "取消" ? 1 : 0),
    bookingId: status === "预订" ? "" : bookingId,
    roomIds: status === "取消" ? [] : uniqueRoomIds,
  };

  if (payload.roomIds.length) {
    payload.roomId = payload.roomIds[0];
  }

  if ((status === "取消" || status === "修改") && !payload.bookingId) {
    showToast(`${status}时请先选择具体订单`, true);
    return;
  }

  if (status === "预订" && payload.quantity <= 0) {
    showToast("预订数量必须大于 0", true);
    return;
  }

  const skipSyncProgress = (payload.platform === "自接" || payload.platform === "抖音") && isLocalOnlyRoomType(payload.roomType);
  if (!skipSyncProgress) {
    openSyncProgress(payload.platform);
  }

  let result = null;
  try {
    result = await requestJSON("/api/adjust", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    stopAsyncSyncPolling();
    hideSyncGuardOverlay();
    if (!skipSyncProgress) {
      closeModal(dom.syncProgressModal);
    }
    showToast(error.message || "出错了", true);
    return;
  }

  try {
    await loadCalendar();
    await loadHistory();
  } catch (error) {
    showToast(`调整已提交，但页面刷新失败：${error.message}`, true);
  }

  closeModal(dom.modal);
  const nextReport = result.syncReport || null;
  if (!skipSyncProgress) {
    finishSyncProgress(payload.platform, nextReport);
  }

  const asyncJobId = String(result.asyncSyncJobId || "").trim();
  if (!skipSyncProgress && asyncJobId) {
    showToast("平台将按顺序逐个同步，请勿操作平台标签页。", false);
    startAsyncSyncPolling(payload.platform, asyncJobId);
    return;
  }

  stopAsyncSyncPolling();
  showToast(adjustSuccessMessage(nextReport));
}


async function openCancelFromChip(buttonEl) {
  const roomType = buttonEl.getAttribute("data-room-type") || "";
  const platform = buttonEl.getAttribute("data-platform") || "";
  const targetDate = buttonEl.getAttribute("data-date") || "";

  if (!roomType || !platform || !targetDate) {
    return;
  }

  dom.adjustForm.elements.roomType.value = roomType;
  dom.adjustForm.elements.platform.value = platform;
  dom.adjustForm.elements.status.value = "取消";
  dom.adjustForm.elements.checkInDate.value = targetDate;
  dom.adjustForm.elements.checkOutDate.value = addDays(targetDate, 1);
  clearCheckOutDateValidation();
  dom.adjustForm.elements.bookingId.value = "";
  dom.adjustForm.elements.quantity.value = "1";
  state.pendingPreferredRoomIds = [];

  openModal(dom.modal);
  await refreshAdjustDependencies();
}


async function openBookingDetailFromChip(buttonEl) {
  const roomType = buttonEl.getAttribute("data-room-type") || "";
  const targetDate = buttonEl.getAttribute("data-date") || "";
  const stage = buttonEl.getAttribute("data-stage") || "";

  if (!roomType || !targetDate) {
    return;
  }

  const query = new URLSearchParams({
    roomType,
    date: targetDate,
    stage,
  }).toString();

  try {
    const data = await requestJSON(`/api/day-bookings?${query}`);
    renderBookingDetailList(data.items || [], roomType, targetDate, stage);
    openModal(dom.bookingDetailModal);
  } catch (error) {
    showToast(error.message, true);
  }
}

function openInitFromRoomCard(buttonEl) {
  const roomType = buttonEl.getAttribute("data-room-type") || "";
  const totalFromCard = Number(buttonEl.getAttribute("data-total") || "");
  const fallbackTotal = findRoomTypeTotal(roomType);
  const total = Number.isFinite(totalFromCard) ? totalFromCard : fallbackTotal;

  if (!roomType) {
    return;
  }

  dom.initForm.elements.roomType.value = roomType;
  dom.initRoomTypeText.textContent = `房型：${roomType}`;
  dom.initForm.elements.quantity.value = String(total ?? 0);
  openModal(dom.initModal);
}

function bindAdjustDateInputs() {
  const dateInputNames = ["checkInDate", "checkOutDate"];

  dateInputNames.forEach((name) => {
    const inputEl = dom.adjustForm.elements[name];
    if (!(inputEl instanceof HTMLInputElement)) {
      return;
    }

    inputEl.addEventListener("focus", () => {
      maybeClearDateInputOnFocus(inputEl);
    });

    inputEl.addEventListener("blur", () => {
      const skipRestore = state.pendingDatePickerField === name;
      if (skipRestore) {
        state.pendingDatePickerField = "";
      }

      const restored = skipRestore ? false : restoreDateInputDefaultIfEmpty(inputEl);
      normalizeDateInputElementValue(inputEl);
      validateAdjustDateRange();
      if (restored) {
        inputEl.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  });

  const pickerInputs = dom.adjustForm.querySelectorAll("input[data-native-picker]");
  pickerInputs.forEach((pickerEl) => {
    if (!(pickerEl instanceof HTMLInputElement)) {
      return;
    }

    const applyPickedDate = () => {
      const fieldName = String(pickerEl.getAttribute("data-native-picker") || "").trim();
      const targetInput = dom.adjustForm.elements[fieldName];
      if (!(targetInput instanceof HTMLInputElement)) {
        return;
      }

      const picked = normalizeFlexibleDateInput(pickerEl.value);
      if (!picked) {
        return;
      }

      targetInput.value = picked;
      validateAdjustDateRange();
      targetInput.dispatchEvent(new Event("change", { bubbles: true }));
    };

    pickerEl.addEventListener("input", applyPickedDate);
    pickerEl.addEventListener("change", applyPickedDate);
  });

  const pickerButtons = dom.adjustForm.querySelectorAll("button[data-picker-for]");
  pickerButtons.forEach((buttonEl) => {
    if (!(buttonEl instanceof HTMLButtonElement)) {
      return;
    }

    buttonEl.addEventListener("mousedown", () => {
      const fieldName = String(buttonEl.getAttribute("data-picker-for") || "").trim();
      state.pendingDatePickerField = fieldName;
    });

    buttonEl.addEventListener("click", () => {
      const fieldName = String(buttonEl.getAttribute("data-picker-for") || "").trim();
      state.pendingDatePickerField = "";
      const targetInput = dom.adjustForm.elements[fieldName];
      const pickerEl = dom.adjustForm.querySelector(`input[data-native-picker='${fieldName}']`);

      if (!(targetInput instanceof HTMLInputElement) || !(pickerEl instanceof HTMLInputElement)) {
        return;
      }

      const normalized = normalizeDateInputElementValue(targetInput);
      pickerEl.value = normalized || "";

      if (typeof pickerEl.showPicker === "function") {
        pickerEl.showPicker();
        return;
      }

      pickerEl.focus();
      pickerEl.click();
    });
  });
}

function wireEvents() {
  bindAdjustDateInputs();

  dom.openAdjustBtn.addEventListener("click", async () => {
    const defaultStatus = state.statuses.includes("预订")
      ? "预订"
      : (state.statuses[0] || "预订");

    const defaults = getDefaultAdjustDateRange();

    dom.adjustForm.elements.checkInDate.value = defaults.checkInDate;
    dom.adjustForm.elements.checkOutDate.value = defaults.checkOutDate;
    dom.adjustForm.elements.status.value = defaultStatus;
    setDefaultSourcePlatform();
    dom.adjustForm.elements.bookingId.value = "";
    dom.adjustForm.elements.quantity.value = "1";
    clearCheckOutDateValidation();
    state.pendingPreferredRoomIds = [];
    openModal(dom.modal);
    try {
      await refreshAdjustDependencies();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  dom.closeInitModalBtn.addEventListener("click", () => closeModal(dom.initModal));
  dom.cancelInitBtn.addEventListener("click", () => closeModal(dom.initModal));
  dom.closeBookingDetailBtn.addEventListener("click", () => closeModal(dom.bookingDetailModal));
  dom.closeSyncProgressBtn.addEventListener("click", () => closeModal(dom.syncProgressModal));
  dom.closeModalBtn.addEventListener("click", () => closeModal(dom.modal));
  dom.cancelBtn.addEventListener("click", () => closeModal(dom.modal));

  dom.refreshBtn.addEventListener("click", async () => {
    try {
      await loadCalendar();
      await loadHistory();
      showToast("已刷新");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  dom.viewDate.addEventListener("change", async () => {
    try {
      await loadCalendar();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  dom.initForm.addEventListener("submit", submitInitLocal);
  dom.adjustForm.addEventListener("submit", submitAdjustment);

  dom.inventoryCalendar.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const roomCard = target.closest("[data-action='open-set-total']");
    if (roomCard instanceof HTMLElement) {
      openInitFromRoomCard(roomCard);
      return;
    }

    const detailChip = target.closest("[data-action='open-booking-detail']");
    if (detailChip instanceof HTMLElement) {
      await openBookingDetailFromChip(detailChip);
      return;
    }

    const chip = target.closest("[data-action='open-cancel']");
    if (!(chip instanceof HTMLElement)) {
      return;
    }

    await openCancelFromChip(chip);
  });

  dom.syncProgressList.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const loginBtn = target.closest("[data-action='open-platform-login']");
    if (!(loginBtn instanceof HTMLButtonElement)) {
      return;
    }

    const platform = String(loginBtn.getAttribute("data-platform") || "").trim();
    if (!platform) {
      return;
    }

    loginBtn.disabled = true;
    try {
      await ensurePlatformTabFocused(platform);
    } catch (error) {
      showToast(error.message, true);
    } finally {
      loginBtn.disabled = false;
    }
  });

  if (dom.platformGuidePanel) {
    dom.platformGuidePanel.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const focusBtn = target.closest("[data-action='focus-platform-tab']");
      if (focusBtn instanceof HTMLButtonElement) {
        const platform = String(focusBtn.getAttribute("data-platform") || "").trim();
        if (!platform) {
          return;
        }

        focusBtn.disabled = true;
        try {
          await ensurePlatformTabFocused(platform);
        } catch (error) {
          showToast(error.message, true);
        } finally {
          focusBtn.disabled = false;
        }
        return;
      }

      const openBtn = target.closest("[data-action='open-platform-tabs']");
      if (openBtn instanceof HTMLButtonElement) {
        openBtn.disabled = true;
        try {
          await openPlatformTabs({ forceRestart: false });
        } catch (error) {
          showToast(error.message, true);
        } finally {
          openBtn.disabled = false;
        }
      }
    });
  }

  [
    dom.adjustForm.elements.status,
    dom.adjustForm.elements.platform,
    dom.adjustForm.elements.roomType,
    dom.adjustForm.elements.checkInDate,
    dom.adjustForm.elements.checkOutDate,
  ].forEach((el) => {
    el.addEventListener("change", async () => {
      if (el === dom.adjustForm.elements.platform) {
        refreshRoomTypeOptionsByPlatform();
      }

      if (
        el === dom.adjustForm.elements.checkInDate
        || el === dom.adjustForm.elements.checkOutDate
      ) {
        normalizeDateInputElementValue(el);
        validateAdjustDateRange();
      }

      try {
        await refreshAdjustDependencies();
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });

  dom.adjustForm.elements.quantity.addEventListener("change", async () => {
    if (getAdjustStatus() !== "预订") {
      return;
    }
    try {
      await refreshRoomOptionsIfNeeded();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  dom.adjustForm.elements.bookingId.addEventListener("change", async () => {
    applySelectedBookingToForm({ forceDates: true });
    validateAdjustDateRange();
    try {
      await refreshRoomOptionsIfNeeded();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  dom.initModal.addEventListener("click", (event) => {
    if (event.target === dom.initModal) {
      closeModal(dom.initModal);
    }
  });

  dom.bookingDetailModal.addEventListener("click", (event) => {
    if (event.target === dom.bookingDetailModal) {
      closeModal(dom.bookingDetailModal);
    }
  });

  dom.modal.addEventListener("click", (event) => {
    if (event.target === dom.modal) {
      closeModal(dom.modal);
    }
  });

  dom.retrySyncBtn.addEventListener("click", async () => {
    await runSyncRetryAction("auto");
  });

  if (dom.giveUpSyncBtn) {
    dom.giveUpSyncBtn.addEventListener("click", async () => {
      await runSyncRetryAction("manual_fallback");
    });
  }
}

async function bootstrap() {
  dom.viewDate.value = todayString();
  state.calendarWindowDays = calcWindowDays();

  try {
    await loadMeta();
    await loadCalendar();
    await loadHistory();
    wireEvents();
  } catch (error) {
    showToast(error.message, true);
  }
}

bootstrap();

let resizeTimer = null;
window.addEventListener("resize", () => {
  if (resizeTimer) {
    clearTimeout(resizeTimer);
  }

  resizeTimer = setTimeout(async () => {
    const nextDays = calcWindowDays();
    if (nextDays !== state.calendarWindowDays) {
      state.calendarWindowDays = nextDays;
      try {
        await loadCalendar();
      } catch (error) {
        showToast(error.message, true);
      }
    }
  }, 160);
});
