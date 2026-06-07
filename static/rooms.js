const state = {
  date: "",
  roomTypes: [],
  floors: [],
  unfinishedOrders: [],
  selectedRoomId: "",
  backupInfo: {},
};

const dom = {
  statusDate: document.getElementById("statusDate"),
  refreshBtn: document.getElementById("refreshBtn"),
  addFloorForm: document.getElementById("addFloorForm"),
  addRoomForm: document.getElementById("addRoomForm"),
  exportBackupBtn: document.getElementById("exportBackupBtn"),
  backupFile: document.getElementById("backupFile"),
  importBackupBtn: document.getElementById("importBackupBtn"),
  lastBackupExportDate: document.getElementById("lastBackupExportDate"),
  floorBoard: document.getElementById("floorBoard"),
  totalRooms: document.getElementById("totalRooms"),
  occupiedRooms: document.getElementById("occupiedRooms"),
  upcomingRooms: document.getElementById("upcomingRooms"),
  idleRooms: document.getElementById("idleRooms"),
  maintenanceRooms: document.getElementById("maintenanceRooms"),
  unfinishedOrdersCard: document.getElementById("unfinishedOrdersCard"),
  unfinishedOrdersCount: document.getElementById("unfinishedOrdersCount"),
  unfinishedOrdersModal: document.getElementById("unfinishedOrdersModal"),
  closeUnfinishedOrdersBtn: document.getElementById("closeUnfinishedOrdersBtn"),
  unfinishedPlatformFilter: document.getElementById("unfinishedPlatformFilter"),
  unfinishedRoomTypeFilter: document.getElementById("unfinishedRoomTypeFilter"),
  unfinishedOrdersContent: document.getElementById("unfinishedOrdersContent"),
  roomDetailEmpty: document.getElementById("roomDetailEmpty"),
  roomDetailContent: document.getElementById("roomDetailContent"),
  detailNumber: document.getElementById("detailNumber"),
  detailFloor: document.getElementById("detailFloor"),
  detailStatusText: document.getElementById("detailStatusText"),
  detailStatusSelect: document.getElementById("detailStatusSelect"),
  detailReservation: document.getElementById("detailReservation"),
  detailRoomType: document.getElementById("detailRoomType"),
  saveRoomTypeBtn: document.getElementById("saveRoomTypeBtn"),
  deleteRoomBtn: document.getElementById("deleteRoomBtn"),
  toast: document.getElementById("toast"),
};

function todayString() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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

function normalizeIsoDateText(value) {
  const text = String(value || "").trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : "";
}

function renderBackupInfo() {
  if (!dom.lastBackupExportDate) {
    return;
  }
  const dateText = normalizeIsoDateText(state.backupInfo?.lastExportDate);
  dom.lastBackupExportDate.textContent = dateText || "未记录";
}

function openModal(modalEl) {
  modalEl.classList.remove("hidden");
  modalEl.setAttribute("aria-hidden", "false");
}

function closeModal(modalEl) {
  modalEl.classList.add("hidden");
  modalEl.setAttribute("aria-hidden", "true");
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.message || "请求失败");
  }
  return data;
}

function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function getRoomById(roomId) {
  for (const floor of state.floors) {
    for (const room of floor.rooms || []) {
      if (room.id === roomId) {
        return room;
      }
    }
  }
  return null;
}

function renderRoomTypeOptions(selectedType = "") {
  return state.roomTypes
    .map((item) => {
      const selected = item.name === selectedType ? "selected" : "";
      return `<option value="${escapeHtml(item.name)}" ${selected}>${escapeHtml(item.name)}</option>`;
    })
    .join("");
}

function tileClassByStatus(status) {
  if (status === "在住") {
    return "tile-occupied";
  }
  if (status === "待入住") {
    return "tile-upcoming";
  }
  if (status === "维修") {
    return "tile-maintenance";
  }
  if (status === "未开放") {
    return "tile-closed";
  }
  return "tile-idle";
}

function renderFormOptions() {
  const floorSelect = dom.addRoomForm.elements.floorId;
  const prevFloorId = floorSelect.value;
  floorSelect.innerHTML = "";
  state.floors.forEach((floor) => {
    const option = document.createElement("option");
    option.value = floor.id;
    option.textContent = `${floor.name}${floor.isOpen ? "（营业）" : "（未开放）"}`;
    floorSelect.appendChild(option);
  });

  const floorIds = state.floors.map((item) => String(item.id || "").trim()).filter((item) => Boolean(item));
  if (prevFloorId && floorIds.includes(prevFloorId)) {
    floorSelect.value = prevFloorId;
  } else {
    const openFloor = state.floors.find((item) => Boolean(item.isOpen));
    floorSelect.value = String(openFloor?.id || floorIds[0] || "");
  }

  const roomTypeSelect = dom.addRoomForm.elements.roomType;
  roomTypeSelect.innerHTML = "";
  state.roomTypes.forEach((roomType) => {
    const option = document.createElement("option");
    option.value = roomType.name;
    option.textContent = roomType.name;
    roomTypeSelect.appendChild(option);
  });
}

function renderSummary(summary) {
  dom.totalRooms.textContent = String(summary.totalRooms || 0);
  dom.occupiedRooms.textContent = String(summary.occupiedRooms || 0);
  dom.upcomingRooms.textContent = String(summary.upcomingRooms || 0);
  dom.idleRooms.textContent = String(summary.idleRooms || 0);
  dom.maintenanceRooms.textContent = String(summary.maintenanceRooms || 0);
  dom.unfinishedOrdersCount.textContent = String(summary.unfinishedOrdersCount || 0);
}

function fillFilterSelect(selectEl, values, defaultText) {
  const selectedValue = selectEl.value;
  selectEl.innerHTML = "";

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = defaultText;
  selectEl.appendChild(defaultOption);

  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    selectEl.appendChild(option);
  });

  const hasSelected = values.includes(selectedValue);
  selectEl.value = hasSelected ? selectedValue : "";
}

function syncUnfinishedOrderFilters() {
  const items = state.unfinishedOrders || [];
  const platforms = Array.from(
    new Set(
      items
        .map((item) => String(item.platform || "").trim())
        .filter((value) => Boolean(value))
    )
  ).sort((a, b) => a.localeCompare(b, "zh-CN"));

  const roomTypes = Array.from(
    new Set(
      items
        .map((item) => String(item.roomType || "").trim())
        .filter((value) => Boolean(value))
    )
  ).sort((a, b) => a.localeCompare(b, "zh-CN"));

  fillFilterSelect(dom.unfinishedPlatformFilter, platforms, "全部平台");
  fillFilterSelect(dom.unfinishedRoomTypeFilter, roomTypes, "全部房型");
}

function getFilteredUnfinishedOrders() {
  const items = state.unfinishedOrders || [];
  const platform = String(dom.unfinishedPlatformFilter.value || "").trim();
  const roomType = String(dom.unfinishedRoomTypeFilter.value || "").trim();

  return items.filter((item) => {
    const matchPlatform = !platform || String(item.platform || "") === platform;
    const matchRoomType = !roomType || String(item.roomType || "") === roomType;
    return matchPlatform && matchRoomType;
  });
}

function renderUnfinishedOrders() {
  const items = getFilteredUnfinishedOrders();
  if (!items.length) {
    dom.unfinishedOrdersContent.innerHTML = '<div class="board-empty">该筛选条件下暂无未完成订单</div>';
    return;
  }

  const html = items
    .map((item) => {
      const roomNumbers = Array.isArray(item.roomNumbers)
        ? item.roomNumbers.filter((value) => String(value || "").trim())
        : [];
      const roomText = roomNumbers.length ? `房号 ${roomNumbers.join(",")}` : "未分配房号";
      return `
        <article class="unfinished-order-item">
          <div class="unfinished-order-main">${escapeHtml(item.platform || "-")} · ${escapeHtml(item.roomType || "-")} · ${escapeHtml(item.stage || "-")} · 数量${escapeHtml(item.quantity ?? "-")}</div>
          <div class="unfinished-order-sub">${escapeHtml(item.checkInDate || "-")} ~ ${escapeHtml(item.checkOutDate || "-")} · 剩余${escapeHtml(item.remainingNights ?? "-")}晚 · ${escapeHtml(roomText)}</div>
        </article>
      `;
    })
    .join("");

  dom.unfinishedOrdersContent.innerHTML = html;
}

function renderRoomDetail() {
  const room = getRoomById(state.selectedRoomId);
  if (!room) {
    dom.roomDetailEmpty.classList.remove("hidden");
    dom.roomDetailContent.classList.add("hidden");
    dom.detailStatusText.classList.remove("hidden");
    dom.detailStatusSelect.classList.add("hidden");
    dom.saveRoomTypeBtn.dataset.roomId = "";
    dom.deleteRoomBtn.dataset.roomId = "";
    return;
  }

  dom.roomDetailEmpty.classList.add("hidden");
  dom.roomDetailContent.classList.remove("hidden");

  const statusText = room.status || "-";
  const canEditManualStatus = statusText === "空闲" || statusText === "维修";

  dom.detailNumber.textContent = room.number || "-";
  dom.detailFloor.textContent = room.floorName || "-";
  dom.detailStatusText.textContent = statusText;
  dom.detailStatusText.classList.toggle("hidden", canEditManualStatus);
  dom.detailStatusSelect.classList.toggle("hidden", !canEditManualStatus);
  if (canEditManualStatus) {
    dom.detailStatusSelect.value = statusText === "维修" ? "维修" : "空闲";
  }
  dom.detailReservation.textContent = room.reservationText || "-";
  dom.detailRoomType.innerHTML = renderRoomTypeOptions(room.roomType || "");

  dom.saveRoomTypeBtn.dataset.roomId = room.id;
  dom.deleteRoomBtn.dataset.roomId = room.id;
}

function renderFloorBoard() {
  if (!state.floors.length) {
    dom.floorBoard.innerHTML = '<div class="board-empty">暂无楼层，请先添加楼层。</div>';
    renderRoomDetail();
    return;
  }

  const html = state.floors
    .map((floor) => {
      const floorStateClass = floor.isOpen ? "floor-open" : "floor-closed";
      const floorStateText = floor.isOpen ? "营业中" : "未开放";
      const toggleText = floor.isOpen ? "设为未开放" : "开放楼层";

      const roomTiles = (floor.rooms || [])
        .map((room) => {
          const selectedClass = room.id === state.selectedRoomId ? "selected" : "";
          const statusClass = tileClassByStatus(room.status);
          return `
            <button
              type="button"
              class="room-tile ${statusClass} ${selectedClass}"
              data-action="select-room"
              data-room-id="${escapeHtml(room.id)}"
            >
              <div class="room-number">${escapeHtml(room.number)}</div>
              <div class="room-type">${escapeHtml(room.roomType)}</div>
              <div class="room-brief">${escapeHtml(room.status)}</div>
            </button>
          `;
        })
        .join("");

      return `
        <article class="floor-card">
          <div class="floor-head">
            <div class="floor-head-left">
              <div class="floor-title">${escapeHtml(floor.name)}</div>
              <div class="floor-meta">房间数 ${floor.roomCount || 0} / 在住 ${floor.occupiedCount || 0}</div>
              <span class="floor-state ${floorStateClass}">${floorStateText}</span>
            </div>
            <div class="floor-actions">
              <button type="button" class="btn btn-ghost" data-action="toggle-floor-open" data-floor-id="${escapeHtml(floor.id)}" data-next-open="${floor.isOpen ? "false" : "true"}">${toggleText}</button>
              <button type="button" class="btn btn-ghost" data-action="delete-floor" data-floor-id="${escapeHtml(floor.id)}">删除楼层</button>
            </div>
          </div>
          <div class="room-grid">
            ${roomTiles || '<div class="board-empty">当前楼层暂无房间</div>'}
          </div>
        </article>
      `;
    })
    .join("");

  dom.floorBoard.innerHTML = html;
  renderRoomDetail();
}

async function loadSnapshot() {
  const query = new URLSearchParams({ date: state.date }).toString();
  const data = await requestJSON(`/api/room-management?${query}`);
  state.roomTypes = data.roomTypes || [];
  state.floors = data.floors || [];
  state.unfinishedOrders = data.unfinishedOrders || [];
  state.backupInfo = data.backupInfo || {};

  if (state.selectedRoomId && !getRoomById(state.selectedRoomId)) {
    state.selectedRoomId = "";
  }

  renderSummary(data.summary || {});
  renderBackupInfo();
  renderFormOptions();
  renderFloorBoard();
}

async function addFloor(event) {
  event.preventDefault();
  const name = dom.addFloorForm.elements.name.value.trim();
  if (!name) {
    showToast("楼层名称不能为空", true);
    return;
  }

  try {
    await requestJSON("/api/floors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, isOpen: false }),
    });
    dom.addFloorForm.reset();
    await loadSnapshot();
    showToast("楼层已添加（默认未开放）");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function addRoom(event) {
  event.preventDefault();
  const payload = {
    floorId: dom.addRoomForm.elements.floorId.value,
    number: dom.addRoomForm.elements.number.value.trim(),
    roomType: dom.addRoomForm.elements.roomType.value,
  };

  try {
    await requestJSON("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    dom.addRoomForm.elements.number.value = "";
    await loadSnapshot();
    showToast("房间已添加");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deleteFloor(floorId) {
  const ok = window.confirm("确定删除该楼层吗？若该楼层下有房间会一并删除。存在在住/未离店订单时不可删除。");
  if (!ok) {
    return;
  }

  try {
    await requestJSON(`/api/floors/${encodeURIComponent(floorId)}`, {
      method: "DELETE",
    });
    await loadSnapshot();
    showToast("楼层已删除");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function toggleFloorOpen(floorId, nextOpen) {
  try {
    await requestJSON(`/api/floors/${encodeURIComponent(floorId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isOpen: nextOpen }),
    });
    await loadSnapshot();
    showToast(nextOpen ? "楼层已开放" : "楼层已设为未开放");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deleteRoom(roomId) {
  const ok = window.confirm("确定删除该房间吗？存在在住/未离店订单时不可删除。");
  if (!ok) {
    return;
  }

  try {
    await requestJSON(`/api/rooms/${encodeURIComponent(roomId)}`, {
      method: "DELETE",
    });
    if (state.selectedRoomId === roomId) {
      state.selectedRoomId = "";
    }
    await loadSnapshot();
    showToast("房间已删除");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function updateRoomInfo(roomId, roomType, manualStatus) {
  try {
    await requestJSON(`/api/rooms/${encodeURIComponent(roomId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ roomType, manualStatus }),
    });
    await loadSnapshot();
    showToast("房间信息已更新");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function exportBackup() {
  try {
    const data = await requestJSON("/api/backup/export?days=30");
    const backup = data.backup || {};
    const lastExportDate = normalizeIsoDateText(data.lastExportDate);
    if (lastExportDate) {
      state.backupInfo = {
        ...(state.backupInfo || {}),
        lastExportDate,
      };
      renderBackupInfo();
    }
    const now = new Date();
    const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}_${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}`;
    const fileName = `hotel-backup-30days-${stamp}.json`;
    downloadTextFile(fileName, JSON.stringify(backup, null, 2));
    showToast("近30天备份已导出");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function importBackup() {
  const file = dom.backupFile.files?.[0];
  if (!file) {
    showToast("请先选择备份文件", true);
    return;
  }

  let parsed;
  try {
    const text = await file.text();
    parsed = JSON.parse(text);
  } catch {
    showToast("备份文件不是有效的 JSON", true);
    return;
  }

  const ok = window.confirm("导入后会合并到当前数据，是否继续？");
  if (!ok) {
    return;
  }

  try {
    const data = await requestJSON("/api/backup/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backup: parsed }),
    });
    await loadSnapshot();
    dom.backupFile.value = "";

    const stats = data.stats || {};
    const summary = `楼层${stats.floors || 0} 房间${stats.rooms || 0} 日期${stats.inventoryDates || 0} 订单${stats.bookings || 0}`;
    showToast(`备份导入完成：${summary}`);
  } catch (error) {
    showToast(error.message, true);
  }
}

function wireEvents() {
  dom.refreshBtn.addEventListener("click", async () => {
    try {
      await loadSnapshot();
      showToast("已刷新");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  dom.statusDate.addEventListener("change", async () => {
    state.date = dom.statusDate.value;
    try {
      await loadSnapshot();
    } catch (error) {
      showToast(error.message, true);
    }
  });

  dom.addFloorForm.addEventListener("submit", addFloor);
  dom.addRoomForm.addEventListener("submit", addRoom);
  dom.exportBackupBtn.addEventListener("click", exportBackup);
  dom.importBackupBtn.addEventListener("click", importBackup);

  dom.floorBoard.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const roomTile = target.closest("[data-action='select-room']");
    if (roomTile instanceof HTMLElement) {
      state.selectedRoomId = roomTile.getAttribute("data-room-id") || "";
      renderFloorBoard();
      return;
    }

    const floorToggle = target.closest("[data-action='toggle-floor-open']");
    if (floorToggle instanceof HTMLElement) {
      const floorId = floorToggle.getAttribute("data-floor-id") || "";
      const nextOpen = floorToggle.getAttribute("data-next-open") === "true";
      if (floorId) {
        await toggleFloorOpen(floorId, nextOpen);
      }
      return;
    }

    const floorBtn = target.closest("[data-action='delete-floor']");
    if (floorBtn instanceof HTMLElement) {
      const floorId = floorBtn.getAttribute("data-floor-id") || "";
      if (floorId) {
        await deleteFloor(floorId);
      }
    }
  });

  dom.saveRoomTypeBtn.addEventListener("click", async () => {
    const roomId = dom.saveRoomTypeBtn.dataset.roomId || "";
    const room = getRoomById(roomId);
    const roomType = dom.detailRoomType.value;
    if (!roomId || !room || !roomType) {
      return;
    }

    const manualStatus = (room.status === "空闲" || room.status === "维修")
      ? (dom.detailStatusSelect.value || "空闲")
      : (room.manualStatus || "空闲");

    await updateRoomInfo(roomId, roomType, manualStatus);
  });

  dom.unfinishedOrdersCard.addEventListener("click", () => {
    syncUnfinishedOrderFilters();
    renderUnfinishedOrders();
    openModal(dom.unfinishedOrdersModal);
  });

  [dom.unfinishedPlatformFilter, dom.unfinishedRoomTypeFilter].forEach((el) => {
    el.addEventListener("change", () => {
      renderUnfinishedOrders();
    });
  });

  dom.closeUnfinishedOrdersBtn.addEventListener("click", () => {
    closeModal(dom.unfinishedOrdersModal);
  });

  dom.unfinishedOrdersModal.addEventListener("click", (event) => {
    if (event.target === dom.unfinishedOrdersModal) {
      closeModal(dom.unfinishedOrdersModal);
    }
  });

  dom.deleteRoomBtn.addEventListener("click", async () => {
    const roomId = dom.deleteRoomBtn.dataset.roomId || "";
    if (!roomId) {
      return;
    }
    await deleteRoom(roomId);
  });
}

async function bootstrap() {
  state.date = todayString();
  dom.statusDate.value = state.date;

  try {
    await loadSnapshot();
    wireEvents();
  } catch (error) {
    showToast(error.message, true);
  }
}

bootstrap();
