from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from email.utils import parsedate_to_datetime
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "inventory_store.json"
BACKUP_DATA_FILE = DATA_DIR / "inventory_store.backup.json"

ROOM_TYPES_DEFAULT: dict[str, int] = {
    "豪华双床房": 1,
    "度假大床房": 3,
    "家庭房": 4,
    "度假双床房": 4,
    "普通大床房": 2,
    "普通双床房": 7,
}

LOCAL_ONLY_ROOM_TYPES = {"普通大床房", "普通双床房"}

PLATFORMS = ["携程", "飞猪", "美团", "抖音", "自接"]
SYNC_TARGET_PLATFORMS = ["携程", "飞猪", "美团"]
STATUSES = {
    "预订": -1,
    "取消": 1,
}
MODES = ["预订", "取消", "修改"]
STATUS_ALIASES = {
    "入住": "预订",
    "预订": "预订",
    "取消": "取消",
    "修改": "修改",
}
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
MAX_HISTORY_ITEMS = 1000
MAX_SYNC_ITEMS = 5000

try:
    DATA_RETENTION_DAYS = max(1, int(os.getenv("DATA_RETENTION_DAYS", "31")))
except ValueError:
    DATA_RETENTION_DAYS = 31

try:
    AUTO_BACKUP_INTERVAL_HOURS = max(0.0, float(os.getenv("AUTO_BACKUP_INTERVAL_HOURS", "12")))
except ValueError:
    AUTO_BACKUP_INTERVAL_HOURS = 12.0
AUTO_BACKUP_INTERVAL_SECONDS = AUTO_BACKUP_INTERVAL_HOURS * 3600.0

SHANGHAI_TZ = timezone(timedelta(hours=8))
NETWORK_TIME_HEADER_URLS = (
    "https://www.baidu.com",
    "https://www.qq.com",
    "https://www.bing.com",
)
NETWORK_TIME_JSON_URLS = (
    "https://worldtimeapi.org/api/timezone/Asia/Shanghai",
)
PREFER_NETWORK_RETENTION_DATE = str(os.getenv("PREFER_NETWORK_RETENTION_DATE", "1")).strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
try:
    NETWORK_TIME_TIMEOUT_SECONDS = max(0.2, float(os.getenv("NETWORK_TIME_TIMEOUT_SECONDS", "1.8")))
except ValueError:
    NETWORK_TIME_TIMEOUT_SECONDS = 1.8
try:
    NETWORK_TIME_CACHE_TTL_SECONDS = max(30.0, float(os.getenv("NETWORK_TIME_CACHE_TTL_SECONDS", "600")))
except ValueError:
    NETWORK_TIME_CACHE_TTL_SECONDS = 600.0
try:
    NETWORK_TIME_FAILURE_BACKOFF_SECONDS = max(15.0, float(os.getenv("NETWORK_TIME_FAILURE_BACKOFF_SECONDS", "120")))
except ValueError:
    NETWORK_TIME_FAILURE_BACKOFF_SECONDS = 120.0

CTRIP_BATCH_PAGE_URL = "https://ebooking.trip.com/rateplan/batchSetRoomStatusAndQuantity?microJump=true"
FLIGGY_ROOMS_MANAGE_URL = "https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk-rp/roomsVsManage"
MEITUAN_BATCH_PAGE_URL = "https://me.meituan.com/ebooking/merchant/product/batch-inventory"

app = Flask(__name__)
BOOTSTRAP_LOGIN_PROCESS: subprocess.Popen[str] | None = None
BOOTSTRAP_TAB_FOCUS_LOCK = threading.Lock()

ASYNC_SYNC_JOBS: dict[str, dict[str, Any]] = {}
ASYNC_SYNC_JOBS_LOCK = threading.Lock()
ASYNC_SYNC_EXECUTOR = ThreadPoolExecutor(max_workers=1)
MAX_ASYNC_SYNC_JOBS = 120

RETENTION_TIME_LOCK = threading.Lock()
RETENTION_NETWORK_DATE_CACHE: date | None = None
RETENTION_NETWORK_DATE_CACHE_AT_MONO = 0.0
RETENTION_NETWORK_DATE_LAST_FAIL_AT_MONO = 0.0

DATA_HEALTH_ALERT_LOCK = threading.Lock()
DATA_HEALTH_ALERT: dict[str, Any] | None = None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def set_data_health_alert(message: str, code: str) -> None:
    global DATA_HEALTH_ALERT
    alert = {
        "id": str(uuid4()),
        "code": code,
        "level": "error",
        "message": str(message or "数据库故障，请联系技术支持。"),
        "occurredAt": now_iso(),
    }
    with DATA_HEALTH_ALERT_LOCK:
        DATA_HEALTH_ALERT = alert


def get_data_health_alert() -> dict[str, Any] | None:
    with DATA_HEALTH_ALERT_LOCK:
        if DATA_HEALTH_ALERT is None:
            return None
        return dict(DATA_HEALTH_ALERT)


def is_local_only_room_type(room_type: str) -> bool:
    return str(room_type or "").strip() in LOCAL_ONLY_ROOM_TYPES


def should_apply_platform_delta(room_type: str, platform: str) -> bool:
    if not is_local_only_room_type(room_type):
        return True
    return str(platform or "").strip() in {"自接", "抖音"}


def default_room_snapshot(total: int) -> dict[str, int]:
    return {platform: total for platform in PLATFORMS}


def normalize_backup_info(raw_backup_info: Any) -> dict[str, Any]:
    source = raw_backup_info if isinstance(raw_backup_info, dict) else {}

    last_export_date = str(source.get("lastExportDate") or "").strip()
    if last_export_date and parse_iso_date_safe(last_export_date) is None:
        last_export_date = ""

    return {
        "lastExportDate": last_export_date,
        "lastExportAt": str(source.get("lastExportAt") or "").strip(),
        "lastAutoBackupAt": str(source.get("lastAutoBackupAt") or "").strip(),
        "autoBackupIntervalHours": AUTO_BACKUP_INTERVAL_HOURS,
    }


def default_backup_info() -> dict[str, Any]:
    return normalize_backup_info({})


def write_json_file_atomic(path: Path, payload: str) -> None:
    temp_file = path.with_suffix(path.suffix + ".tmp")
    with temp_file.open("w", encoding="utf-8") as handle:
        handle.write(payload)
    temp_file.replace(path)


def should_refresh_backup_file(*, force_refresh: bool = False) -> bool:
    if force_refresh or not BACKUP_DATA_FILE.exists():
        return True

    if AUTO_BACKUP_INTERVAL_SECONDS <= 0:
        return True

    try:
        age_seconds = time.time() - BACKUP_DATA_FILE.stat().st_mtime
    except OSError:
        return True

    return age_seconds >= AUTO_BACKUP_INTERVAL_SECONDS


def default_store() -> dict[str, Any]:
    floors, rooms = build_default_hotel_structure(ROOM_TYPES_DEFAULT)
    return {
        "version": 5,
        "roomConfig": ROOM_TYPES_DEFAULT.copy(),
        "inventory": {},
        "history": [],
        "syncQueue": [],
        "bookings": [],
        "floors": floors,
        "rooms": rooms,
        "backupInfo": default_backup_info(),
    }


def save_store(store: dict[str, Any], *, force_refresh_backup: bool = False) -> None:
    store["backupInfo"] = normalize_backup_info(store.get("backupInfo"))

    refresh_backup = should_refresh_backup_file(force_refresh=force_refresh_backup)
    if refresh_backup:
        prune_store_for_retention(store)
        store["backupInfo"]["lastAutoBackupAt"] = now_iso()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(store, ensure_ascii=False, indent=2)
    write_json_file_atomic(DATA_FILE, payload)

    if refresh_backup:
        write_json_file_atomic(BACKUP_DATA_FILE, payload)


def to_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def bounded_count(value: Any, total: int, fallback: int) -> int:
    count = to_int(value, fallback)
    if count < 0:
        return 0
    if count > total:
        return total
    return count


def normalize_platform_snapshot(raw_snapshot: Any, total: int) -> dict[str, int]:
    snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    return {
        platform: bounded_count(snapshot.get(platform, total), total, total)
        for platform in PLATFORMS
    }


def normalize_room_entry(raw_entry: Any, total: int) -> dict[str, Any]:
    if isinstance(raw_entry, dict) and "platforms" in raw_entry:
        platforms = normalize_platform_snapshot(raw_entry.get("platforms", {}), total)
        local_fallback = min(platforms.values()) if platforms else total
        local_available = bounded_count(raw_entry.get("localAvailable", local_fallback), total, local_fallback)
        return {
            "localAvailable": local_available,
            "platforms": platforms,
        }

    if isinstance(raw_entry, dict):
        # Legacy compatibility: old structure stored only platform counts.
        platforms = normalize_platform_snapshot(raw_entry, total)
        local_available = min(platforms.values()) if platforms else total
        return {
            "localAvailable": local_available,
            "platforms": platforms,
        }

    return {
        "localAvailable": total,
        "platforms": default_room_snapshot(total),
    }


def build_default_hotel_structure(room_config: dict[str, int]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    floor_1_id = str(uuid4())
    floor_2_id = str(uuid4())
    floor_3_id = str(uuid4())
    floors: list[dict[str, Any]] = [
        {"id": floor_1_id, "name": "1层", "isOpen": False},
        {"id": floor_2_id, "name": "2层", "isOpen": True},
        {"id": floor_3_id, "name": "3层", "isOpen": False},
    ]

    rooms: list[dict[str, str]] = []
    index = 1
    for room_type, total in room_config.items():
        count = max(0, to_int(total, 0))
        for _ in range(count):
            room_number = f"2{index:02d}"
            rooms.append(
                {
                    "id": str(uuid4()),
                    "floorId": floor_2_id,
                    "number": room_number,
                    "roomType": room_type,
                    "manualStatus": "空闲",
                }
            )
            index += 1

    return floors, rooms


def normalize_floors(raw_floors: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_floors, list):
        return []

    floors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(raw_floors):
        if not isinstance(item, dict):
            continue

        floor_id = str(item.get("id") or "").strip() or str(uuid4())
        if floor_id in seen_ids:
            continue

        floor_name = str(item.get("name") or "").strip() or f"{idx + 1}层"
        is_open = bool(item.get("isOpen", True))
        floors.append({"id": floor_id, "name": floor_name, "isOpen": is_open})
        seen_ids.add(floor_id)

    return floors


def normalize_rooms(
    raw_rooms: Any,
    floors: list[dict[str, Any]],
    room_config: dict[str, int],
) -> list[dict[str, str]]:
    if not isinstance(raw_rooms, list) or not floors:
        return []

    floor_ids = {item["id"] for item in floors}
    fallback_floor_id = floors[0]["id"]

    room_type_list = list(room_config.keys())
    fallback_room_type = room_type_list[0] if room_type_list else ""

    rooms: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_numbers: set[str] = set()

    for item in raw_rooms:
        if not isinstance(item, dict):
            continue

        room_id = str(item.get("id") or "").strip() or str(uuid4())
        if room_id in seen_ids:
            continue

        room_number = str(item.get("number") or "").strip()
        if not room_number or room_number in seen_numbers:
            continue

        floor_id = str(item.get("floorId") or "").strip()
        if floor_id not in floor_ids:
            floor_id = fallback_floor_id

        room_type = str(item.get("roomType") or "").strip()
        if room_type not in room_config:
            room_type = fallback_room_type

        manual_status = str(item.get("manualStatus") or "").strip()
        if manual_status not in {"空闲", "维修"}:
            manual_status = "空闲"

        if not room_type:
            continue

        rooms.append(
            {
                "id": room_id,
                "floorId": floor_id,
                "number": room_number,
                "roomType": room_type,
                "manualStatus": manual_status,
            }
        )
        seen_ids.add(room_id)
        seen_numbers.add(room_number)

    return rooms


def migrate_store(store: Any) -> dict[str, Any]:
    if not isinstance(store, dict):
        return default_store()

    source_version = to_int(store.get("version", 0), 0)

    store.setdefault("inventory", {})
    if not isinstance(store["inventory"], dict):
        store["inventory"] = {}

    store.setdefault("history", [])
    if not isinstance(store["history"], list):
        store["history"] = []

    store.setdefault("syncQueue", [])
    if not isinstance(store["syncQueue"], list):
        store["syncQueue"] = []

    store.setdefault("bookings", [])
    if not isinstance(store["bookings"], list):
        store["bookings"] = []

    store["backupInfo"] = normalize_backup_info(store.get("backupInfo"))

    room_config = store.get("roomConfig", {})
    if not isinstance(room_config, dict):
        room_config = {}

    normalized_room_config: dict[str, int] = {}
    for room_type, default_total in ROOM_TYPES_DEFAULT.items():
        normalized_room_config[room_type] = max(0, to_int(room_config.get(room_type, default_total), default_total))

    store["roomConfig"] = normalized_room_config

    floors = normalize_floors(store.get("floors", []))
    rooms = normalize_rooms(store.get("rooms", []), floors, normalized_room_config)

    floor_name_set = {str(item.get("name") or "").strip() for item in floors}

    # 旧版本若只存在 1 层，迁移为 1/2/3 层且将现有房间放到 2 层。
    if len(floors) == 1 and floor_name_set == {"1层"}:
        old_floor_id = str(floors[0].get("id") or "")
        floors, generated_rooms = build_default_hotel_structure(normalized_room_config)
        second_floor_id = ""
        for floor in floors:
            if str(floor.get("name")) == "2层":
                second_floor_id = str(floor.get("id"))
                break

        if rooms and second_floor_id:
            for room in rooms:
                if str(room.get("floorId") or "") == old_floor_id:
                    room["floorId"] = second_floor_id
        elif not rooms:
            rooms = generated_rooms

    # 若已有多楼层但缺少 1/2/3 中的任意楼层，则补齐并默认仅 2 层开放。
    if floors:
        existing_names = {str(item.get("name") or "").strip() for item in floors}
        for floor_name in ["1层", "2层", "3层"]:
            if floor_name in existing_names:
                continue
            floors.append(
                {
                    "id": str(uuid4()),
                    "name": floor_name,
                    "isOpen": floor_name == "2层",
                }
            )

    # 老版本升级到新版时，若基础楼层缺少 isOpen 字段，补默认值。
    if source_version < 5:
        for floor in floors:
            floor_name = str(floor.get("name") or "").strip()
            if "isOpen" not in floor:
                floor["isOpen"] = floor_name == "2层"

    if not floors:
        floors, default_rooms = build_default_hotel_structure(normalized_room_config)
        if not rooms:
            rooms = default_rooms

    if not rooms:
        _, generated_rooms = build_default_hotel_structure(normalized_room_config)
        first_floor_id = floors[0]["id"] if floors else ""
        for room in generated_rooms:
            room["floorId"] = first_floor_id
        rooms = generated_rooms

    store["floors"] = floors
    store["rooms"] = rooms

    for target_date, day_map in list(store["inventory"].items()):
        if not isinstance(day_map, dict):
            store["inventory"][target_date] = {}
            day_map = store["inventory"][target_date]

        for room_type, total in normalized_room_config.items():
            day_map[room_type] = normalize_room_entry(day_map.get(room_type), total)

    store["version"] = 5
    return store


def load_json_store_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    # utf-8-sig can decode both BOM and non-BOM UTF-8 files.
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            with path.open("r", encoding=encoding) as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None

    # Guard against accidental literal replacement artifacts like `r`n.
    repaired = raw.replace("`r`n", "\n")
    if repaired == raw:
        return None

    try:
        payload = json.loads(repaired)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def load_store() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    used_fallback = False
    main_file_exists = DATA_FILE.exists()
    backup_file_exists = BACKUP_DATA_FILE.exists()

    store = load_json_store_file(DATA_FILE)
    main_file_broken = main_file_exists and store is None
    if store is None:
        store = load_json_store_file(BACKUP_DATA_FILE)
        used_fallback = store is not None

    if store is None:
        store = default_store()
        save_store(store)
        if main_file_exists or backup_file_exists:
            set_data_health_alert(
                "数据库文件故障，主库和备份库均不可读取，系统已回退默认空数据库。请立即联系技术支持。",
                code="store-both-broken",
            )
        return store

    if used_fallback:
        if main_file_broken:
            set_data_health_alert(
                "检测到主数据库损坏，系统已自动使用备份数据库恢复并覆盖主库。请联系技术支持检查。",
                code="store-main-recovered",
            )
        elif not main_file_exists:
            set_data_health_alert(
                "检测到主数据库文件缺失，系统已自动使用备份数据库恢复主库。请联系技术支持检查。",
                code="store-main-missing",
            )

    normalized_store = migrate_store(store)
    refresh_backup_due = should_refresh_backup_file(force_refresh=used_fallback)

    if used_fallback or normalized_store != store or refresh_backup_due:
        save_store(
            normalized_store,
            force_refresh_backup=used_fallback or refresh_backup_due,
        )

    return normalized_store


def parse_stay_range(payload: dict[str, Any]) -> tuple[date, date, list[str]]:
    check_in_raw = str(
        payload.get("checkInDate")
        or payload.get("startDate")
        or payload.get("date")
        or ""
    ).strip()
    check_out_raw = str(payload.get("checkOutDate") or payload.get("endDate") or "").strip()

    if not check_in_raw:
        raise ValueError("请选择到店日期")

    try:
        check_in = date.fromisoformat(check_in_raw)
    except ValueError as exc:
        raise ValueError("到店日期格式不正确，请使用 YYYY-MM-DD") from exc

    if not check_out_raw:
        # Backward compatibility for old one-day payloads.
        check_out = check_in + timedelta(days=1)
    else:
        try:
            check_out = date.fromisoformat(check_out_raw)
        except ValueError as exc:
            raise ValueError("离店日期格式不正确，请使用 YYYY-MM-DD") from exc

    if check_out <= check_in:
        raise ValueError("离店日期必须晚于到店日期")

    days: list[str] = []
    cursor = check_in
    while cursor < check_out:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)

    return check_in, check_out, days


def ensure_day_inventory(store: dict[str, Any], target_date: str) -> dict[str, dict[str, Any]]:
    day_map = store["inventory"].setdefault(target_date, {})
    room_config = store["roomConfig"]
    for room_type, total in room_config.items():
        day_map[room_type] = normalize_room_entry(day_map.get(room_type), total)
    return day_map


def build_inventory_rows(store: dict[str, Any], target_date: str) -> list[dict[str, Any]]:
    day_map = ensure_day_inventory(store, target_date)
    rows: list[dict[str, Any]] = []

    for room_type, total in store["roomConfig"].items():
        room_entry = day_map[room_type]
        rows.append(
            {
                "roomType": room_type,
                "total": total,
                "localAvailable": int(room_entry["localAvailable"]),
                "platforms": {
                    platform: int(room_entry["platforms"][platform])
                    for platform in PLATFORMS
                },
            }
        )

    return rows


def validate_init_payload(payload: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    room_type = str(payload.get("roomType", "")).strip()
    quantity_raw = payload.get("quantity", 0)
    sync_platforms = bool(payload.get("syncPlatforms", False))

    if room_type not in store["roomConfig"]:
        raise ValueError("房型不在配置列表中")

    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("数量必须是整数") from exc

    if quantity < 0:
        raise ValueError("总房量不能小于 0")

    return {
        "roomType": room_type,
        "quantity": quantity,
        "syncPlatforms": sync_platforms,
    }


def validate_adjust_payload(payload: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    room_type = str(payload.get("roomType", "")).strip()
    platform = str(payload.get("platform", "")).strip()
    status_raw = str(payload.get("status", "")).strip()
    quantity_raw = payload.get("quantity", 0)
    booking_id = str(payload.get("bookingId", "")).strip()
    room_id = str(payload.get("roomId", "")).strip()
    room_ids_raw = payload.get("roomIds", [])

    room_ids: list[str] = []
    if isinstance(room_ids_raw, list):
        for item in room_ids_raw:
            room_value = str(item or "").strip()
            if room_value:
                room_ids.append(room_value)
    elif isinstance(room_ids_raw, str):
        room_value = room_ids_raw.strip()
        if room_value:
            room_ids.append(room_value)

    if room_id and room_id not in room_ids:
        room_ids.insert(0, room_id)

    check_in, check_out, days = parse_stay_range(payload)

    if room_type not in store["roomConfig"]:
        raise ValueError("房型不在配置列表中")

    if platform not in PLATFORMS:
        raise ValueError("平台不在配置列表中")

    if is_local_only_room_type(room_type) and platform not in {"自接", "抖音"}:
        raise ValueError("普通房型仅支持“自接”或“抖音”来源")

    status = STATUS_ALIASES.get(status_raw)
    if status not in MODES:
        raise ValueError("方式必须是 预订、取消 或 修改")

    if status in {"取消", "修改"} and not booking_id:
        raise ValueError("取消或修改时请先选择具体订单")

    if status == "取消":
        quantity = 1
    elif status == "修改":
        quantity = 0
    else:
        try:
            quantity = int(quantity_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("数量必须是整数") from exc

        if quantity <= 0:
            raise ValueError("数量必须大于 0")

    return {
        "checkInDate": check_in.isoformat(),
        "checkOutDate": check_out.isoformat(),
        "days": days,
        "nights": len(days),
        "roomType": room_type,
        "platform": platform,
        "status": status,
        "quantity": quantity,
        "bookingId": booking_id,
        "roomId": room_id,
        "roomIds": room_ids,
    }


def get_booking_by_id(store: dict[str, Any], booking_id: str) -> dict[str, Any] | None:
    for booking in store["bookings"]:
        if str(booking.get("id")) == booking_id:
            return booking
    return None


def get_floor_name_map(store: dict[str, Any]) -> dict[str, str]:
    floor_name_map: dict[str, str] = {}
    for floor in store["floors"]:
        floor_id = str(floor.get("id") or "").strip()
        if not floor_id:
            continue
        floor_name_map[floor_id] = str(floor.get("name") or floor_id)
    return floor_name_map


def get_open_floor_ids(store: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for floor in store["floors"]:
        floor_id = str(floor.get("id") or "").strip()
        if not floor_id:
            continue
        if bool(floor.get("isOpen", True)):
            result.add(floor_id)
    return result


def get_room_capacity_by_type(
    store: dict[str, Any],
    *,
    floors: list[dict[str, Any]] | None = None,
    rooms: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    floors_ref = floors if floors is not None else store["floors"]
    rooms_ref = rooms if rooms is not None else store["rooms"]

    room_config = store["roomConfig"]
    capacity: dict[str, int] = {room_type: 0 for room_type in room_config.keys()}

    open_floor_ids: set[str] = set()
    for floor in floors_ref:
        floor_id = str(floor.get("id") or "").strip()
        if not floor_id:
            continue
        if bool(floor.get("isOpen", True)):
            open_floor_ids.add(floor_id)

    for room in rooms_ref:
        floor_id = str(room.get("floorId") or "").strip()
        if floor_id not in open_floor_ids:
            continue

        manual_status = str(room.get("manualStatus") or "空闲").strip()
        if manual_status == "维修":
            continue

        room_type = str(room.get("roomType") or "").strip()
        if room_type in capacity:
            capacity[room_type] += 1

    return capacity


def ensure_room_config_within_capacity(
    store: dict[str, Any],
    *,
    floors: list[dict[str, Any]] | None = None,
    rooms: list[dict[str, Any]] | None = None,
) -> None:
    # 兼容旧调用：已取消“总房量 <= 可用房间数”的硬性校验。
    return


def get_room_by_id(store: dict[str, Any], room_id: str) -> dict[str, Any] | None:
    for room in store["rooms"]:
        if str(room.get("id") or "").strip() == room_id:
            return room
    return None


def has_positive_booking_qty(booking: dict[str, Any]) -> bool:
    booking_daily = booking.get("dailyQuantity", {})
    if not isinstance(booking_daily, dict):
        return False
    return any(to_int(qty, 0) > 0 for qty in booking_daily.values())


def booking_contains_room_id(booking: dict[str, Any], room_id: str) -> bool:
    target_room_id = str(room_id or "").strip()
    if not target_room_id:
        return False
    return target_room_id in get_booking_room_ids(booking)


def room_has_active_booking(store: dict[str, Any], room_id: str) -> bool:
    for booking in store["bookings"]:
        if not booking_contains_room_id(booking, room_id):
            continue
        if has_positive_booking_qty(booking):
            return True
    return False


def room_conflicts_in_days(store: dict[str, Any], room_id: str, days: list[str], exclude_booking_id: str = "") -> bool:
    if not room_id or not days:
        return False

    day_set = set(days)
    for booking in store["bookings"]:
        if not booking_contains_room_id(booking, room_id):
            continue
        if exclude_booking_id and str(booking.get("id") or "") == exclude_booking_id:
            continue

        booking_daily = booking.get("dailyQuantity", {})
        if not isinstance(booking_daily, dict):
            continue

        for day, qty in booking_daily.items():
            if str(day) in day_set and to_int(qty, 0) > 0:
                return True

    return False


def list_available_rooms(
    store: dict[str, Any],
    room_type: str,
    days: list[str],
    *,
    exclude_booking_id: str = "",
) -> list[dict[str, str]]:
    floor_name_map = get_floor_name_map(store)
    open_floor_ids = get_open_floor_ids(store)
    result: list[dict[str, str]] = []

    for room in store["rooms"]:
        current_type = str(room.get("roomType") or "").strip()
        if current_type != room_type:
            continue

        room_id = str(room.get("id") or "").strip()
        if not room_id:
            continue

        if room_conflicts_in_days(store, room_id, days, exclude_booking_id=exclude_booking_id):
            continue

        floor_id = str(room.get("floorId") or "").strip()
        if floor_id not in open_floor_ids:
            continue

        manual_status = str(room.get("manualStatus") or "空闲").strip()
        if manual_status == "维修":
            continue

        result.append(
            {
                "id": room_id,
                "number": str(room.get("number") or ""),
                "floorId": floor_id,
                "floorName": floor_name_map.get(floor_id, "未分层"),
            }
        )

    result.sort(key=lambda item: (item.get("floorName", ""), item.get("number", "")))
    return result


def parse_booking_days(booking: dict[str, Any]) -> list[str]:
    daily_quantity = booking.get("dailyQuantity", {})
    if isinstance(daily_quantity, dict):
        return sorted(
            [
                str(day)
                for day, qty in daily_quantity.items()
                if to_int(qty, 0) > 0 and str(day)
            ]
        )

    return []


def get_booking_room_ids(booking: dict[str, Any]) -> list[str]:
    room_ids_raw = booking.get("roomIds", [])
    result: list[str] = []

    if isinstance(room_ids_raw, list):
        for item in room_ids_raw:
            room_id = str(item or "").strip()
            if room_id and room_id not in result:
                result.append(room_id)

    single_room_id = str(booking.get("roomId") or "").strip()
    if single_room_id and single_room_id not in result:
        result.insert(0, single_room_id)

    return result


def get_booking_room_numbers(booking: dict[str, Any]) -> list[str]:
    room_numbers_raw = booking.get("roomNumbers", [])
    result: list[str] = []

    if isinstance(room_numbers_raw, list):
        for item in room_numbers_raw:
            number = str(item or "").strip()
            if number and number not in result:
                result.append(number)

    single_room_number = str(booking.get("roomNumber") or "").strip()
    if single_room_number and single_room_number not in result:
        result.insert(0, single_room_number)

    return result


def get_booking_quantity(booking: dict[str, Any]) -> int:
    booking_daily = booking.get("dailyQuantity", {})
    if isinstance(booking_daily, dict):
        max_qty = 0
        for qty in booking_daily.values():
            max_qty = max(max_qty, to_int(qty, 0))
        if max_qty > 0:
            return max_qty

    return max(1, to_int(booking.get("quantity"), 1))


def list_modify_options(
    store: dict[str, Any],
    room_type: str,
    platform: str,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []

    for booking in store["bookings"]:
        if str(booking.get("roomType") or "").strip() != room_type:
            continue
        if str(booking.get("sourcePlatform") or "").strip() != platform:
            continue
        if not has_positive_booking_qty(booking):
            continue

        check_in = str(booking.get("checkInDate") or "").strip()
        check_out = str(booking.get("checkOutDate") or "").strip()
        quantity = get_booking_quantity(booking)
        room_ids = get_booking_room_ids(booking)
        room_numbers = get_booking_room_numbers(booking)

        room_text = f" 房号{','.join(room_numbers)}" if room_numbers else ""
        label = f"{platform} {check_in}~{check_out}{room_text} 数量{quantity}"

        options.append(
            {
                "id": str(booking.get("id") or ""),
                "label": label,
                "quantity": quantity,
                "checkInDate": check_in,
                "checkOutDate": check_out,
                "roomIds": room_ids,
                "roomNumbers": room_numbers,
            }
        )

    options.sort(key=lambda item: item.get("checkInDate", ""), reverse=True)
    return options


def list_cancel_options(
    store: dict[str, Any],
    room_type: str,
    platform: str,
    selected_days: list[str],
) -> list[dict[str, Any]]:
    selected_set = set(selected_days)
    options: list[dict[str, Any]] = []

    for booking in store["bookings"]:
        if str(booking.get("roomType")) != room_type:
            continue
        if str(booking.get("sourcePlatform")) != platform:
            continue

        active_days = parse_booking_days(booking)
        overlap_days = [day for day in active_days if day in selected_set]
        if not overlap_days:
            continue

        daily_quantity = booking.get("dailyQuantity", {})
        available = min(to_int(daily_quantity.get(day, 0), 0) for day in active_days)
        if available <= 0:
            continue

        check_in = str(booking.get("checkInDate", "")).strip()
        check_out = str(booking.get("checkOutDate", "")).strip()
        room_number = str(booking.get("roomNumber") or "").strip()
        room_text = f" 房号{room_number}" if room_number else ""
        label = f"{platform} {check_in}~{check_out}{room_text} 整单取消{available}"

        options.append(
            {
                "id": str(booking.get("id")),
                "label": label,
                "available": available,
                "checkInDate": check_in,
                "checkOutDate": check_out,
                "nights": len(active_days),
                "roomNumber": room_number,
            }
        )

    options.sort(key=lambda item: item.get("checkInDate", ""), reverse=True)
    return options


def list_day_booking_details(
    store: dict[str, Any],
    room_type: str,
    target_date: str,
    stage: str = "",
    platform: str = "",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for booking in store["bookings"]:
        if str(booking.get("roomType") or "").strip() != room_type:
            continue

        source_platform = str(booking.get("sourcePlatform") or "").strip()
        if platform and source_platform != platform:
            continue

        booking_daily = booking.get("dailyQuantity", {})
        if not isinstance(booking_daily, dict):
            continue

        qty = to_int(booking_daily.get(target_date, 0), 0)
        if qty <= 0:
            continue

        check_in = str(booking.get("checkInDate") or "").strip()
        stage_value = "新" if check_in == target_date else "续"
        if stage and stage_value != stage:
            continue

        items.append(
            {
                "id": str(booking.get("id") or ""),
                "platform": source_platform,
                "stage": stage_value,
                "quantity": qty,
                "checkInDate": check_in,
                "checkOutDate": str(booking.get("checkOutDate") or "").strip(),
                "roomNumber": str(booking.get("roomNumber") or "").strip(),
                "roomType": room_type,
            }
        )

    items.sort(
        key=lambda item: (
            str(item.get("platform") or ""),
            str(item.get("checkInDate") or ""),
            str(item.get("roomNumber") or ""),
        )
    )
    return items


def parse_iso_date_safe(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    try:
        return date.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            return None


def in_date_range(target: date, start: date, end: date) -> bool:
    return start <= target <= end


def parse_http_date_to_shanghai_date(raw_value: Any) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(SHANGHAI_TZ).date()


def fetch_network_today_shanghai(timeout_seconds: float) -> date | None:
    headers = {"User-Agent": "Mozilla/5.0 (HotelInventorySync)"}

    for url in NETWORK_TIME_HEADER_URLS:
        try:
            req = urllib_request.Request(url, method="HEAD", headers=headers)
            with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:
                parsed = parse_http_date_to_shanghai_date(resp.headers.get("Date"))
                if parsed is not None:
                    return parsed
        except urllib_error.HTTPError as exc:
            parsed = parse_http_date_to_shanghai_date(exc.headers.get("Date") if exc.headers else None)
            if parsed is not None:
                return parsed
        except (urllib_error.URLError, TimeoutError, OSError, ValueError):
            continue

    for url in NETWORK_TIME_JSON_URLS:
        try:
            req = urllib_request.Request(url, method="GET", headers=headers)
            with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:
                payload_text = resp.read().decode("utf-8", errors="ignore")
            payload = json.loads(payload_text)
            raw_dt = str(payload.get("datetime") or "").strip()
            if not raw_dt:
                continue
            dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(SHANGHAI_TZ).date()
        except (json.JSONDecodeError, urllib_error.URLError, TimeoutError, OSError, ValueError):
            continue

    return None


def retention_reference_today(today: date | None = None) -> date:
    global RETENTION_NETWORK_DATE_CACHE
    global RETENTION_NETWORK_DATE_CACHE_AT_MONO
    global RETENTION_NETWORK_DATE_LAST_FAIL_AT_MONO

    if today is not None:
        return today

    local_today = date.today()
    if not PREFER_NETWORK_RETENTION_DATE:
        return local_today

    now_mono = time.monotonic()
    with RETENTION_TIME_LOCK:
        if (
            RETENTION_NETWORK_DATE_CACHE is not None
            and (now_mono - RETENTION_NETWORK_DATE_CACHE_AT_MONO) <= NETWORK_TIME_CACHE_TTL_SECONDS
        ):
            return RETENTION_NETWORK_DATE_CACHE

        if (
            RETENTION_NETWORK_DATE_LAST_FAIL_AT_MONO > 0
            and (now_mono - RETENTION_NETWORK_DATE_LAST_FAIL_AT_MONO) <= NETWORK_TIME_FAILURE_BACKOFF_SECONDS
        ):
            return local_today

    network_today = fetch_network_today_shanghai(NETWORK_TIME_TIMEOUT_SECONDS)

    with RETENTION_TIME_LOCK:
        if network_today is not None:
            RETENTION_NETWORK_DATE_CACHE = network_today
            RETENTION_NETWORK_DATE_CACHE_AT_MONO = now_mono
            RETENTION_NETWORK_DATE_LAST_FAIL_AT_MONO = 0.0
            return network_today

        RETENTION_NETWORK_DATE_LAST_FAIL_AT_MONO = now_mono

    return local_today


def retention_cutoff_date(today: date | None = None) -> date:
    reference_date = retention_reference_today(today)
    return reference_date - timedelta(days=DATA_RETENTION_DAYS)


def should_keep_history_record_for_retention(record: dict[str, Any], cutoff: date) -> bool:
    created_at_date = parse_iso_date_safe(record.get("createdAt"))
    if created_at_date is not None:
        return created_at_date >= cutoff

    has_parseable_day = False
    for day in parse_record_days(record):
        day_date = parse_iso_date_safe(day)
        if day_date is None:
            continue
        has_parseable_day = True
        if day_date >= cutoff:
            return True

    if has_parseable_day:
        return False

    return True


def should_keep_sync_item_for_retention(item: dict[str, Any], cutoff: date) -> bool:
    status = str(item.get("status") or "").strip().lower()
    if status == "pending":
        return True

    target_date = parse_iso_date_safe(item.get("date"))
    if target_date is not None:
        return target_date >= cutoff

    created_at_date = parse_iso_date_safe(item.get("createdAt"))
    if created_at_date is not None:
        return created_at_date >= cutoff

    return True


def should_keep_booking_for_retention(booking: dict[str, Any], cutoff: date) -> bool:
    check_out_date = parse_iso_date_safe(booking.get("checkOutDate"))
    if check_out_date is not None:
        return check_out_date >= cutoff

    if booking_overlaps_range(booking, cutoff, date.max):
        return True

    has_parseable_date = False
    for key in ("checkInDate", "createdAt", "updatedAt"):
        value_date = parse_iso_date_safe(booking.get(key))
        if value_date is None:
            continue
        has_parseable_date = True
        if value_date >= cutoff:
            return True

    if has_parseable_date:
        return False

    return True


def prune_store_for_retention(
    store: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, int]:
    removed = {
        "inventoryDates": 0,
        "history": 0,
        "syncQueue": 0,
        "bookings": 0,
    }

    cutoff = retention_cutoff_date(today)

    inventory_raw = store.get("inventory")
    if isinstance(inventory_raw, dict):
        retained_inventory: dict[str, Any] = {}
        for target_date, day_map in inventory_raw.items():
            day_text = str(target_date).strip()
            day_date = parse_iso_date_safe(day_text)
            if day_date is not None and day_date < cutoff:
                removed["inventoryDates"] += 1
                continue
            retained_inventory[day_text] = day_map
        store["inventory"] = retained_inventory

    history_raw = store.get("history")
    if isinstance(history_raw, list):
        retained_history: list[dict[str, Any]] = []
        for record in history_raw:
            if not isinstance(record, dict):
                removed["history"] += 1
                continue
            if should_keep_history_record_for_retention(record, cutoff):
                retained_history.append(record)
            else:
                removed["history"] += 1

        if len(retained_history) > MAX_HISTORY_ITEMS:
            removed["history"] += len(retained_history) - MAX_HISTORY_ITEMS
            del retained_history[MAX_HISTORY_ITEMS:]

        store["history"] = retained_history

    sync_queue_raw = store.get("syncQueue")
    if isinstance(sync_queue_raw, list):
        retained_sync_queue: list[dict[str, Any]] = []
        for item in sync_queue_raw:
            if not isinstance(item, dict):
                removed["syncQueue"] += 1
                continue
            if should_keep_sync_item_for_retention(item, cutoff):
                retained_sync_queue.append(item)
            else:
                removed["syncQueue"] += 1

        if len(retained_sync_queue) > MAX_SYNC_ITEMS:
            removed["syncQueue"] += len(retained_sync_queue) - MAX_SYNC_ITEMS
            del retained_sync_queue[MAX_SYNC_ITEMS:]

        store["syncQueue"] = retained_sync_queue

    bookings_raw = store.get("bookings")
    if isinstance(bookings_raw, list):
        retained_bookings: list[dict[str, Any]] = []
        for booking in bookings_raw:
            if not isinstance(booking, dict):
                removed["bookings"] += 1
                continue
            if should_keep_booking_for_retention(booking, cutoff):
                retained_bookings.append(booking)
            else:
                removed["bookings"] += 1
        store["bookings"] = retained_bookings

    return removed


def booking_overlaps_range(booking: dict[str, Any], start: date, end: date) -> bool:
    booking_daily = booking.get("dailyQuantity", {})
    if isinstance(booking_daily, dict):
        for day, qty in booking_daily.items():
            if to_int(qty, 0) <= 0:
                continue
            day_date = parse_iso_date_safe(day)
            if day_date and in_date_range(day_date, start, end):
                return True

    check_in = parse_iso_date_safe(booking.get("checkInDate"))
    check_out = parse_iso_date_safe(booking.get("checkOutDate"))
    if check_in and check_out:
        return not (check_out <= start or check_in > end)

    return False


def record_overlaps_range(record: dict[str, Any], start: date, end: date) -> bool:
    created_at_date = parse_iso_date_safe(record.get("createdAt"))
    if created_at_date and in_date_range(created_at_date, start, end):
        return True

    for day in parse_record_days(record):
        day_date = parse_iso_date_safe(day)
        if day_date and in_date_range(day_date, start, end):
            return True

    return False


def sync_item_overlaps_range(item: dict[str, Any], start: date, end: date) -> bool:
    target_date = parse_iso_date_safe(item.get("date"))
    if target_date and in_date_range(target_date, start, end):
        return True

    created_at_date = parse_iso_date_safe(item.get("createdAt"))
    if created_at_date and in_date_range(created_at_date, start, end):
        return True

    return False


def build_floor_room_type_distribution(store: dict[str, Any]) -> list[dict[str, Any]]:
    floor_name_map = get_floor_name_map(store)
    summary_map: dict[str, dict[str, Any]] = {}

    for floor in store["floors"]:
        floor_id = str(floor.get("id") or "").strip()
        if not floor_id:
            continue

        summary_map[floor_id] = {
            "floorId": floor_id,
            "floorName": str(floor.get("name") or floor_name_map.get(floor_id, floor_id)),
            "isOpen": bool(floor.get("isOpen", True)),
            "totalRooms": 0,
            "roomTypeCounts": {},
        }

    for room in store["rooms"]:
        floor_id = str(room.get("floorId") or "").strip()
        room_type = str(room.get("roomType") or "").strip()
        if not floor_id or not room_type:
            continue

        summary = summary_map.get(floor_id)
        if summary is None:
            summary = {
                "floorId": floor_id,
                "floorName": floor_name_map.get(floor_id, "未分层"),
                "isOpen": False,
                "totalRooms": 0,
                "roomTypeCounts": {},
            }
            summary_map[floor_id] = summary

        room_type_counts = summary["roomTypeCounts"]
        room_type_counts[room_type] = to_int(room_type_counts.get(room_type, 0), 0) + 1
        summary["totalRooms"] = to_int(summary.get("totalRooms", 0), 0) + 1

    result = list(summary_map.values())
    result.sort(key=lambda item: str(item.get("floorName") or ""))
    for item in result:
        counts = item.get("roomTypeCounts")
        if isinstance(counts, dict):
            item["roomTypeCounts"] = dict(sorted(counts.items(), key=lambda pair: pair[0]))

    return result


def build_backup_payload(store: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    inventory_slice: dict[str, Any] = {}
    for target_date, day_map in store["inventory"].items():
        day_date = parse_iso_date_safe(target_date)
        if not day_date:
            continue
        if not in_date_range(day_date, start, end):
            continue
        if isinstance(day_map, dict):
            inventory_slice[str(target_date)] = day_map

    bookings_slice = [
        booking
        for booking in store["bookings"]
        if isinstance(booking, dict) and booking_overlaps_range(booking, start, end)
    ]
    history_slice = [
        record
        for record in store["history"]
        if isinstance(record, dict) and record_overlaps_range(record, start, end)
    ]
    sync_slice = [
        item
        for item in store["syncQueue"]
        if isinstance(item, dict) and sync_item_overlaps_range(item, start, end)
    ]

    return {
        "backupVersion": 1,
        "generatedAt": now_iso(),
        "rangeStart": start.isoformat(),
        "rangeEnd": end.isoformat(),
        "storeVersion": to_int(store.get("version", 5), 5),
        "data": {
            "roomConfig": store["roomConfig"],
            "floors": store["floors"],
            "rooms": store["rooms"],
            "floorRoomTypeDistribution": build_floor_room_type_distribution(store),
            "inventory": inventory_slice,
            "bookings": bookings_slice,
            "history": history_slice,
            "syncQueue": sync_slice,
        },
    }


def merge_list_by_id(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    index_map: dict[str, int] = {}

    for item in existing:
        item_id = str(item.get("id") or "").strip()
        if item_id:
            if item_id in index_map:
                continue
            index_map[item_id] = len(result)
        result.append(item)

    for item in incoming:
        item_id = str(item.get("id") or "").strip()
        if item_id and item_id in index_map:
            result[index_map[item_id]] = item
            continue
        if item_id:
            index_map[item_id] = len(result)
        result.append(item)

    return result


def merge_backup_into_store(store: dict[str, Any], backup_payload: Any) -> tuple[dict[str, Any], dict[str, int]]:
    if not isinstance(backup_payload, dict):
        raise ValueError("备份文件格式不正确")

    backup_data = backup_payload.get("data")
    if backup_data is None:
        backup_data = backup_payload
    if not isinstance(backup_data, dict):
        raise ValueError("备份文件缺少 data 字段")

    stats = {
        "floors": 0,
        "rooms": 0,
        "inventoryDates": 0,
        "bookings": 0,
        "history": 0,
        "syncQueue": 0,
    }

    incoming_room_config = backup_data.get("roomConfig")
    if isinstance(incoming_room_config, dict):
        for room_type, raw_total in incoming_room_config.items():
            room_type_name = str(room_type).strip()
            if not room_type_name:
                continue
            store["roomConfig"][room_type_name] = max(0, to_int(raw_total, 0))

    incoming_floors = normalize_floors(backup_data.get("floors", []))
    if incoming_floors:
        store["floors"] = merge_list_by_id(store["floors"], incoming_floors)
        stats["floors"] = len(incoming_floors)

    incoming_rooms = normalize_rooms(backup_data.get("rooms", []), store["floors"], store["roomConfig"])
    if incoming_rooms:
        store["rooms"] = merge_list_by_id(store["rooms"], incoming_rooms)
        stats["rooms"] = len(incoming_rooms)

    incoming_inventory = backup_data.get("inventory")
    if isinstance(incoming_inventory, dict):
        for target_date, day_map in incoming_inventory.items():
            if isinstance(day_map, dict):
                store["inventory"][str(target_date)] = day_map
        stats["inventoryDates"] = len(incoming_inventory)

    incoming_bookings_raw = backup_data.get("bookings")
    if isinstance(incoming_bookings_raw, list):
        incoming_bookings = [item for item in incoming_bookings_raw if isinstance(item, dict)]
        store["bookings"] = merge_list_by_id(store["bookings"], incoming_bookings)
        stats["bookings"] = len(incoming_bookings)

    incoming_history_raw = backup_data.get("history")
    if isinstance(incoming_history_raw, list):
        incoming_history = [item for item in incoming_history_raw if isinstance(item, dict)]
        store["history"] = merge_list_by_id(store["history"], incoming_history)
        stats["history"] = len(incoming_history)

    incoming_sync_raw = backup_data.get("syncQueue")
    if isinstance(incoming_sync_raw, list):
        incoming_sync = [item for item in incoming_sync_raw if isinstance(item, dict)]
        store["syncQueue"] = merge_list_by_id(store["syncQueue"], incoming_sync)
        stats["syncQueue"] = len(incoming_sync)

    merged_store = migrate_store(store)
    merged_store["history"].sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    merged_store["syncQueue"].sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    if len(merged_store["history"]) > MAX_HISTORY_ITEMS:
        del merged_store["history"][MAX_HISTORY_ITEMS:]
    if len(merged_store["syncQueue"]) > MAX_SYNC_ITEMS:
        del merged_store["syncQueue"][MAX_SYNC_ITEMS:]

    return merged_store, stats


def append_history_record(store: dict[str, Any], record: dict[str, Any]) -> None:
    store["history"].insert(0, record)
    if len(store["history"]) > MAX_HISTORY_ITEMS:
        del store["history"][MAX_HISTORY_ITEMS:]


def append_adjust_sync_tasks(
    store: dict[str, Any],
    source_platform: str,
    room_type: str,
    status: str,
    daily_changes: dict[str, dict[str, Any]],
) -> None:
    if is_local_only_room_type(room_type):
        return

    created_at = now_iso()
    for target_date, change in daily_changes.items():
        platform_changes = change.get("platforms", {})
        if not isinstance(platform_changes, dict):
            continue

        for target_platform in SYNC_TARGET_PLATFORMS:
            if target_platform == source_platform:
                continue
            target_change = platform_changes.get(target_platform)
            if not isinstance(target_change, dict):
                continue
            day_delta = int(target_change["after"]) - int(target_change["before"])
            day_quantity = abs(day_delta)
            if day_quantity <= 0:
                continue
            store["syncQueue"].insert(
                0,
                {
                    "id": str(uuid4()),
                    "createdAt": created_at,
                    "status": "pending",
                    "actionType": "adjust",
                    "date": target_date,
                    "roomType": room_type,
                    "sourcePlatform": source_platform,
                    "targetPlatform": target_platform,
                    "mode": status,
                    "quantity": day_quantity,
                    "delta": day_delta,
                    "before": target_change["before"],
                    "after": target_change["after"],
                },
            )

    if len(store["syncQueue"]) > MAX_SYNC_ITEMS:
        del store["syncQueue"][MAX_SYNC_ITEMS:]


def append_init_sync_tasks(
    store: dict[str, Any],
    room_type: str,
    quantity: int,
    daily_changes: dict[str, dict[str, Any]],
) -> None:
    if is_local_only_room_type(room_type):
        return

    created_at = now_iso()
    for target_date, change in daily_changes.items():
        platform_changes = change.get("platforms", {})
        if not isinstance(platform_changes, dict):
            continue

        for target_platform in SYNC_TARGET_PLATFORMS:
            target_change = platform_changes.get(target_platform)
            if not isinstance(target_change, dict):
                continue
            store["syncQueue"].insert(
                0,
                {
                    "id": str(uuid4()),
                    "createdAt": created_at,
                    "status": "pending",
                    "actionType": "init",
                    "date": target_date,
                    "roomType": room_type,
                    "sourcePlatform": "本地系统",
                    "targetPlatform": target_platform,
                    "mode": "初始化",
                    "quantity": quantity,
                    "delta": target_change["after"] - target_change["before"],
                    "before": target_change["before"],
                    "after": target_change["after"],
                },
            )

    if len(store["syncQueue"]) > MAX_SYNC_ITEMS:
        del store["syncQueue"][MAX_SYNC_ITEMS:]


def group_sync_items_by_contiguous_dates(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped_map: dict[tuple[str, int], list[tuple[date, dict[str, Any]]]] = {}
    invalid_entries: list[dict[str, Any]] = []

    for item in items:
        room_type = str(item.get("roomType") or "").strip()
        target_date_raw = str(item.get("date") or "").strip()
        remaining_quantity = to_int(item.get("after"), -1)

        if not room_type:
            invalid_entries.append({"item": item, "message": "缺少 roomType"})
            continue
        if not target_date_raw:
            invalid_entries.append({"item": item, "message": "缺少 date"})
            continue
        if remaining_quantity < 0:
            invalid_entries.append({"item": item, "message": "缺少合法的 after（目标剩余房量）"})
            continue

        try:
            target_day = date.fromisoformat(target_date_raw)
        except ValueError:
            invalid_entries.append({"item": item, "message": "date 格式必须是 YYYY-MM-DD"})
            continue

        key = (room_type, remaining_quantity)
        grouped_map.setdefault(key, []).append((target_day, item))

    batches: list[dict[str, Any]] = []
    for (room_type, remaining_quantity), entries in grouped_map.items():
        entries.sort(key=lambda pair: pair[0])
        if not entries:
            continue

        start_day = entries[0][0]
        end_day = entries[0][0]
        batch_items: list[dict[str, Any]] = [entries[0][1]]

        for current_day, current_item in entries[1:]:
            if current_day == end_day + timedelta(days=1):
                end_day = current_day
                batch_items.append(current_item)
                continue

            batches.append(
                {
                    "roomType": room_type,
                    "remainingQuantity": remaining_quantity,
                    "startDay": start_day,
                    "endDay": end_day,
                    "items": list(batch_items),
                }
            )

            start_day = current_day
            end_day = current_day
            batch_items = [current_item]

        batches.append(
            {
                "roomType": room_type,
                "remainingQuantity": remaining_quantity,
                "startDay": start_day,
                "endDay": end_day,
                "items": list(batch_items),
            }
        )

    batches.sort(key=lambda batch: (batch["startDay"], batch["roomType"]))
    return batches, invalid_entries


def run_ctrip_sync_queue(
    store: dict[str, Any],
    *,
    limit: int = 20,
    headless: bool = False,
    task_ids: set[str] | None = None,
    force_manual_fallback: bool = False,
    restore_management_tab: bool = True,
) -> dict[str, Any]:
    def format_ctrip_error_message(exc: Exception | str) -> str:
        message = str(exc).strip() or "携程同步失败"

        requires_relogin = (
            "会话未登录" in message
            or "请先在登录引导页完成携程登录" in message
        )

        if requires_relogin:
            return "携程会话已失效，请先完成携程登录引导后重试"

        return "请关闭携程平台标签页后重新尝试"

    task_id_filter: set[str] | None = None
    if task_ids is not None:
        task_id_filter = {str(item).strip() for item in task_ids if str(item).strip()}

    pending_items = [
        item
        for item in store["syncQueue"]
        if isinstance(item, dict)
        and str(item.get("targetPlatform") or "").strip() == "携程"
        and str(item.get("status") or "").strip() == "pending"
        and (
            task_id_filter is None
            or str(item.get("id") or "").strip() in task_id_filter
        )
    ]

    if not pending_items:
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "items": [],
        }

    from platform_sync import CtripQuantityUpdate, CtripSyncSession

    picked = pending_items[:limit]
    grouped_batches, invalid_entries = group_sync_items_by_contiguous_dates(picked)
    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    manual_count = 0

    for invalid in invalid_entries:
        item = invalid["item"]
        message = str(invalid["message"])
        task_id = str(item.get("id") or "")
        item["status"] = "failed"
        item["syncedAt"] = now_iso()
        item["errorMessage"] = message
        failed_count += 1
        results.append(
            {
                "id": task_id,
                "ok": False,
                "message": message,
            }
        )

    if not grouped_batches:
        return {
            "processed": len(picked),
            "success": success_count,
            "failed": failed_count,
            "manual": manual_count,
            "items": results,
        }

    try:
        with CtripSyncSession(headless=headless) as session:
            session.open_rateplan_page()
            for batch in grouped_batches:
                room_type = str(batch["roomType"])
                remaining_quantity = int(batch["remainingQuantity"])
                start_day = batch["startDay"]
                end_day = batch["endDay"]
                batch_items = list(batch["items"])
                check_out_day = end_day + timedelta(days=1)

                batch_retry_count = max(
                    (
                        to_int(item.get("retryCount", 0), 0)
                        for item in batch_items
                        if isinstance(item, dict)
                    ),
                    default=0,
                )

                try:
                    update = CtripQuantityUpdate(
                        room_type=room_type,
                        check_in_date=start_day.isoformat(),
                        check_out_date=check_out_day.isoformat(),
                        remaining_quantity=remaining_quantity,
                    )
                except Exception as exc:
                    error_message = format_ctrip_error_message(exc)
                    for item in batch_items:
                        task_id = str(item.get("id") or "")
                        item["status"] = "failed"
                        item["syncedAt"] = now_iso()
                        item["errorMessage"] = error_message
                        failed_count += 1
                        results.append(
                            {
                                "id": task_id,
                                "ok": False,
                                "message": error_message,
                            }
                        )
                    continue

                if force_manual_fallback:
                    try:
                        fallback_details = session.update_room_quantity(
                            update,
                            open_page=True,
                            apply_date=False,
                            auto_submit=False,
                            restore_management_tab=restore_management_tab,
                        )
                        enriched_fallback_details = {
                            **fallback_details,
                            "checkInDate": start_day.isoformat(),
                            "checkOutDate": check_out_day.isoformat(),
                        }
                        manual_message = (
                            f"已放弃自动重试，切换备用方案：请手动设置日期 {start_day.isoformat()} 至 {check_out_day.isoformat()} 并提交"
                        )
                        for item in batch_items:
                            task_id = str(item.get("id") or "")
                            item["status"] = "manual"
                            item["syncedAt"] = now_iso()
                            item["errorMessage"] = manual_message
                            manual_count += 1
                            results.append(
                                {
                                    "id": task_id,
                                    "ok": True,
                                    "message": manual_message,
                                    "details": enriched_fallback_details,
                                }
                            )
                        continue
                    except Exception as fallback_exc:
                        fallback_message = format_ctrip_error_message(fallback_exc)
                        error_message = fallback_message
                        for item in batch_items:
                            task_id = str(item.get("id") or "")
                            item["status"] = "failed"
                            item["syncedAt"] = now_iso()
                            item["errorMessage"] = error_message
                            failed_count += 1
                            results.append(
                                {
                                    "id": task_id,
                                    "ok": False,
                                    "message": error_message,
                                }
                            )
                        continue

                try:
                    details = session.update_room_quantity(
                        update,
                        open_page=True,
                        apply_date=True,
                        auto_submit=True,
                        restore_management_tab=restore_management_tab,
                    )
                    enriched_details = {
                        **details,
                        "checkInDate": start_day.isoformat(),
                        "checkOutDate": check_out_day.isoformat(),
                    }
                    for item in batch_items:
                        task_id = str(item.get("id") or "")
                        item["status"] = "success"
                        item["syncedAt"] = now_iso()
                        item["errorMessage"] = ""
                        success_count += 1
                        results.append(
                            {
                                "id": task_id,
                                "ok": True,
                                "message": "已提交平台修改",
                                "details": enriched_details,
                            }
                        )
                except Exception as exc:
                    error_message = format_ctrip_error_message(exc)

                    if batch_retry_count > 0:
                        try:
                            fallback_details = session.update_room_quantity(
                                update,
                                open_page=True,
                                apply_date=False,
                                auto_submit=False,
                                restore_management_tab=restore_management_tab,
                            )
                            enriched_fallback_details = {
                                **fallback_details,
                                "checkInDate": start_day.isoformat(),
                                "checkOutDate": check_out_day.isoformat(),
                            }
                            manual_message = (
                                f"携程新流程重试后仍失败，已切换旧流程：请手动设置日期 {start_day.isoformat()} 至 {check_out_day.isoformat()} 并提交"
                            )
                            for item in batch_items:
                                task_id = str(item.get("id") or "")
                                item["status"] = "manual"
                                item["syncedAt"] = now_iso()
                                item["errorMessage"] = manual_message
                                manual_count += 1
                                results.append(
                                    {
                                        "id": task_id,
                                        "ok": True,
                                        "message": manual_message,
                                        "details": enriched_fallback_details,
                                    }
                                )
                            continue
                        except Exception as fallback_exc:
                            fallback_message = format_ctrip_error_message(fallback_exc)
                            error_message = fallback_message

                    for item in batch_items:
                        task_id = str(item.get("id") or "")
                        item["status"] = "failed"
                        item["syncedAt"] = now_iso()
                        item["errorMessage"] = error_message
                        failed_count += 1
                        results.append(
                            {
                                "id": task_id,
                                "ok": False,
                                "message": error_message,
                            }
                        )
    except Exception as exc:
        error_message = format_ctrip_error_message(exc)
        for batch in grouped_batches:
            for item in list(batch["items"]):
                task_id = str(item.get("id") or "")
                item["status"] = "failed"
                item["syncedAt"] = now_iso()
                item["errorMessage"] = error_message
                results.append(
                    {
                        "id": task_id,
                        "ok": False,
                        "message": error_message,
                    }
                )

        return {
            "status": "failed",
            "message": error_message,
            "processed": 0,
            "success": 0,
            "failed": len(picked),
            "manual": 0,
            "items": results,
        }

    response: dict[str, Any] = {
        "processed": len(picked),
        "success": success_count,
        "failed": failed_count,
        "manual": manual_count,
        "items": results,
    }

    if manual_count > 0 and failed_count == 0:
        response["status"] = "manual"
        response["message"] = "部分任务已切换旧流程，请在平台页面手动设置日期后提交"
    elif manual_count > 0 and failed_count > 0:
        response["status"] = "failed"
        response["message"] = "部分任务已切换旧流程，且存在失败任务"

    return response


def run_fliggy_sync_queue(
    store: dict[str, Any],
    *,
    limit: int = 20,
    headless: bool = False,
    task_ids: set[str] | None = None,
    force_manual_fallback: bool = False,
    restore_management_tab: bool = True,
) -> dict[str, Any]:
    def format_fliggy_error_message(exc: Exception | str) -> str:
        message = str(exc).strip() or "飞猪同步失败"

        requires_relogin = (
            "会话未登录" in message
            or "请先在登录引导页完成飞猪登录" in message
            or "未检测到可复用的登录浏览器" in message
        )

        if requires_relogin:
            return "飞猪会话已失效，请先完成飞猪登录引导后重试"
        return f"飞猪同步失败：{message}"

    task_id_filter: set[str] | None = None
    if task_ids is not None:
        task_id_filter = {str(item).strip() for item in task_ids if str(item).strip()}

    pending_items = [
        item
        for item in store["syncQueue"]
        if isinstance(item, dict)
        and str(item.get("targetPlatform") or "").strip() == "飞猪"
        and str(item.get("status") or "").strip() == "pending"
        and (
            task_id_filter is None
            or str(item.get("id") or "").strip() in task_id_filter
        )
    ]

    if not pending_items:
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "items": [],
        }

    from platform_sync import FliggyQuantityUpdate, FliggySyncSession

    picked = pending_items[:limit]
    grouped_batches, invalid_entries = group_sync_items_by_contiguous_dates(picked)
    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    manual_count = 0

    for invalid in invalid_entries:
        item = invalid["item"]
        message = str(invalid["message"])
        task_id = str(item.get("id") or "")
        item["status"] = "failed"
        item["syncedAt"] = now_iso()
        item["errorMessage"] = message
        failed_count += 1
        results.append(
            {
                "id": task_id,
                "ok": False,
                "message": message,
            }
        )

    if not grouped_batches:
        return {
            "processed": len(picked),
            "success": success_count,
            "failed": failed_count,
            "manual": manual_count,
            "items": results,
        }

    try:
        with FliggySyncSession(headless=headless) as session:
            session.open_batch_status_page()
            try:
                for batch in grouped_batches:
                    room_type = str(batch["roomType"])
                    remaining_quantity = int(batch["remainingQuantity"])
                    start_day = batch["startDay"]
                    end_day = batch["endDay"]
                    batch_items = list(batch["items"])
                    check_out_day = end_day + timedelta(days=1)

                    try:
                        update = FliggyQuantityUpdate(
                            room_type=room_type,
                            check_in_date=start_day.isoformat(),
                            check_out_date=check_out_day.isoformat(),
                            remaining_quantity=remaining_quantity,
                        )

                        if force_manual_fallback:
                            fallback_details = session.update_room_quantity(
                                update,
                                open_page=True,
                                apply_date=False,
                                auto_submit=False,
                            )
                            enriched_fallback_details = {
                                **fallback_details,
                                "checkInDate": start_day.isoformat(),
                                "checkOutDate": check_out_day.isoformat(),
                            }
                            manual_message = (
                                "已放弃自动重试，切换备用方案：请在飞猪AI助理页手动发送并确认本次指令"
                            )
                            for item in batch_items:
                                task_id = str(item.get("id") or "")
                                item["status"] = "manual"
                                item["syncedAt"] = now_iso()
                                item["errorMessage"] = manual_message
                                manual_count += 1
                                results.append(
                                    {
                                        "id": task_id,
                                        "ok": True,
                                        "message": manual_message,
                                        "details": enriched_fallback_details,
                                    }
                                )
                            continue

                        details = session.update_room_quantity(
                            update,
                            open_page=True,
                            apply_date=True,
                            auto_submit=True,
                        )
                        enriched_details = {
                            **details,
                            "checkInDate": start_day.isoformat(),
                            "checkOutDate": check_out_day.isoformat(),
                        }
                        for item in batch_items:
                            task_id = str(item.get("id") or "")
                            item["status"] = "success"
                            item["syncedAt"] = now_iso()
                            item["errorMessage"] = ""
                            success_count += 1
                            results.append(
                                {
                                    "id": task_id,
                                    "ok": True,
                                    "message": "已提交平台修改",
                                    "details": enriched_details,
                                }
                            )
                    except Exception as exc:
                        error_message = format_fliggy_error_message(exc)

                        batch_retry_count = max(
                            (
                                to_int(item.get("retryCount", 0), 0)
                                for item in batch_items
                                if isinstance(item, dict)
                            ),
                            default=0,
                        )

                        if batch_retry_count > 0:
                            try:
                                fallback_details = session.update_room_quantity(
                                    update,
                                    open_page=True,
                                    apply_date=False,
                                    auto_submit=False,
                                )
                                enriched_fallback_details = {
                                    **fallback_details,
                                    "checkInDate": start_day.isoformat(),
                                    "checkOutDate": check_out_day.isoformat(),
                                }
                                manual_message = (
                                    "飞猪新流程重试后仍失败，已切换备用方案：请在飞猪AI助理页手动发送并确认本次指令"
                                )
                                for item in batch_items:
                                    task_id = str(item.get("id") or "")
                                    item["status"] = "manual"
                                    item["syncedAt"] = now_iso()
                                    item["errorMessage"] = manual_message
                                    manual_count += 1
                                    results.append(
                                        {
                                            "id": task_id,
                                            "ok": True,
                                            "message": manual_message,
                                            "details": enriched_fallback_details,
                                        }
                                    )
                                continue
                            except Exception as fallback_exc:
                                fallback_message = format_fliggy_error_message(fallback_exc)
                                error_message = fallback_message

                        for item in batch_items:
                            task_id = str(item.get("id") or "")
                            item["status"] = "failed"
                            item["syncedAt"] = now_iso()
                            item["errorMessage"] = error_message
                            failed_count += 1
                            results.append(
                                {
                                    "id": task_id,
                                    "ok": False,
                                    "message": error_message,
                                }
                            )
            finally:
                if restore_management_tab:
                    # Restore local management page only once after all Fliggy batches complete,
                    # to avoid management<->Fliggy foreground flicker between batches.
                    try:
                        management_page = session._find_local_management_page()
                        if management_page is not None:
                            session._bring_page_to_front(management_page)
                    except Exception:
                        pass
    except Exception as exc:
        error_message = format_fliggy_error_message(exc)
        for batch in grouped_batches:
            for item in list(batch["items"]):
                task_id = str(item.get("id") or "")
                item["status"] = "failed"
                item["syncedAt"] = now_iso()
                item["errorMessage"] = error_message
                results.append(
                    {
                        "id": task_id,
                        "ok": False,
                        "message": error_message,
                    }
                )

        return {
            "status": "failed",
            "message": error_message,
            "processed": 0,
            "success": 0,
            "failed": len(picked),
            "manual": 0,
            "items": results,
        }

    response: dict[str, Any] = {
        "processed": len(picked),
        "success": success_count,
        "failed": failed_count,
        "manual": manual_count,
        "items": results,
    }

    if manual_count > 0 and failed_count == 0:
        response["status"] = "manual"
        response["message"] = "已切换为飞猪AI助理手动确认，请在平台页面发送指令并确认"
    elif manual_count > 0 and failed_count > 0:
        response["status"] = "failed"
        response["message"] = "部分任务需在飞猪AI助理页手动发送并确认，且存在失败任务"

    return response


def run_meituan_sync_queue(
    store: dict[str, Any],
    *,
    limit: int = 20,
    headless: bool = False,
    task_ids: set[str] | None = None,
    restore_management_tab: bool = True,
) -> dict[str, Any]:
    def format_meituan_error_message(exc: Exception | str) -> str:
        message = str(exc).strip() or "美团同步失败"

        requires_relogin = (
            "会话未登录" in message
            or "请先在登录引导页完成美团登录" in message
            or "未检测到可复用的登录浏览器" in message
        )

        if requires_relogin:
            return "美团会话已失效，请先完成美团登录引导后重试"
        return f"美团同步失败：{message}"

    task_id_filter: set[str] | None = None
    if task_ids is not None:
        task_id_filter = {str(item).strip() for item in task_ids if str(item).strip()}

    pending_items = [
        item
        for item in store["syncQueue"]
        if isinstance(item, dict)
        and str(item.get("targetPlatform") or "").strip() == "美团"
        and str(item.get("status") or "").strip() == "pending"
        and (
            task_id_filter is None
            or str(item.get("id") or "").strip() in task_id_filter
        )
    ]

    if not pending_items:
        return {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "items": [],
        }

    from platform_sync import MeituanQuantityUpdate, MeituanSyncSession

    picked = pending_items[:limit]
    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0

    try:
        with MeituanSyncSession(headless=headless) as session:
            session.open_batch_inventory_page()
            for item in picked:
                task_id = str(item.get("id") or "")
                room_type = str(item.get("roomType") or "").strip()
                target_date_raw = str(item.get("date") or "").strip()
                remaining_quantity = to_int(item.get("after"), -1)

                try:
                    if not room_type:
                        raise ValueError("缺少 roomType")
                    if not target_date_raw:
                        raise ValueError("缺少 date")
                    if remaining_quantity < 0:
                        raise ValueError("缺少合法的 after（目标剩余房量）")

                    target_day = date.fromisoformat(target_date_raw)
                    update = MeituanQuantityUpdate(
                        room_type=room_type,
                        check_in_date=target_day.isoformat(),
                        check_out_date=(target_day + timedelta(days=1)).isoformat(),
                        remaining_quantity=remaining_quantity,
                    )
                    details = session.update_room_quantity(
                        update,
                        open_page=True,
                        restore_management_tab=restore_management_tab,
                    )

                    item["status"] = "success"
                    item["syncedAt"] = now_iso()
                    item["errorMessage"] = ""
                    success_count += 1
                    results.append(
                        {
                            "id": task_id,
                            "ok": True,
                            "message": "已提交平台修改",
                            "details": details,
                        }
                    )
                except Exception as exc:
                    error_message = format_meituan_error_message(exc)
                    item["status"] = "failed"
                    item["syncedAt"] = now_iso()
                    item["errorMessage"] = error_message
                    failed_count += 1
                    results.append(
                        {
                            "id": task_id,
                            "ok": False,
                            "message": error_message,
                        }
                    )
    except Exception as exc:
        error_message = format_meituan_error_message(exc)
        for item in picked:
            task_id = str(item.get("id") or "")
            item["status"] = "failed"
            item["syncedAt"] = now_iso()
            item["errorMessage"] = error_message
            results.append(
                {
                    "id": task_id,
                    "ok": False,
                    "message": error_message,
                }
            )

        return {
            "status": "failed",
            "message": error_message,
            "processed": 0,
            "success": 0,
            "failed": len(picked),
            "items": results,
        }

    return {
        "processed": len(picked),
        "success": success_count,
        "failed": failed_count,
        "items": results,
    }


def env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    value = str(raw_value).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def list_pending_sync_task_ids(store: dict[str, Any], *, target_platform: str) -> set[str]:
    result: set[str] = set()
    for item in store["syncQueue"]:
        if not isinstance(item, dict):
            continue
        if str(item.get("targetPlatform") or "").strip() != target_platform:
            continue
        if str(item.get("status") or "").strip() != "pending":
            continue
        task_id = str(item.get("id") or "").strip()
        if task_id:
            result.add(task_id)
    return result


def normalize_task_id_set(task_ids: Any) -> set[str]:
    if not isinstance(task_ids, (set, list, tuple)):
        return set()
    return {
        str(item).strip()
        for item in task_ids
        if str(item).strip()
    }


def mark_sync_tasks_failed(
    store: dict[str, Any],
    *,
    platform: str,
    task_ids: set[str],
    message: str,
) -> list[dict[str, Any]]:
    selected_ids = normalize_task_id_set(task_ids)
    if not selected_ids:
        return []

    results: list[dict[str, Any]] = []
    for item in store["syncQueue"]:
        if not isinstance(item, dict):
            continue
        if str(item.get("targetPlatform") or "").strip() != platform:
            continue

        task_id = str(item.get("id") or "").strip()
        if not task_id or task_id not in selected_ids:
            continue

        current_status = str(item.get("status") or "").strip().lower()
        if current_status == "success":
            continue

        item["status"] = "failed"
        item["syncedAt"] = now_iso()
        item["errorMessage"] = message
        results.append(
            {
                "id": task_id,
                "ok": False,
                "message": message,
            }
        )

    return results


def run_timeout_sync_queue(
    store: dict[str, Any],
    *,
    platform: str,
    task_ids: set[str],
) -> dict[str, Any]:
    selected_ids = normalize_task_id_set(task_ids)
    if not selected_ids:
        return {"processed": 0, "success": 0, "failed": 0, "items": []}

    results = mark_sync_tasks_failed(
        store,
        platform=platform,
        task_ids=selected_ids,
        message="同步超时",
    )

    return {
        "processed": len(results),
        "success": 0,
        "failed": len(results),
        "items": results,
    }


def run_queued_sync_queue(platform: str, task_ids: set[str]) -> dict[str, Any]:
    selected_ids = normalize_task_id_set(task_ids)
    return {
        "status": "queued",
        "message": "待接入（已入队）",
        "processed": 0,
        "success": 0,
        "failed": 0,
        "targetTaskCount": len(selected_ids),
        "items": [
            {
                "id": task_id,
                "ok": False,
                "message": "待接入（已入队）",
            }
            for task_id in sorted(selected_ids)
        ],
    }


def restore_local_management_tab_after_sync() -> None:
    try:
        if not is_bootstrap_browser_reachable():
            return

        targets = list_bootstrap_browser_targets()
        target_id = ""
        for item in targets:
            url = str(item.get("url") or "").lower()
            if "/dashboard" not in url:
                continue
            if "127.0.0.1:" not in url and "localhost:" not in url:
                continue
            target_id = str(item.get("id") or item.get("targetId") or "").strip()
            if target_id:
                break

        if target_id:
            focus_bootstrap_target_by_id(target_id)
    except Exception:
        pass


def focus_platform_tab_for_sync(platform: str) -> None:
    platform_key = normalize_focus_platform(platform)
    if not platform_key:
        return

    try:
        if not is_bootstrap_browser_reachable():
            return

        request_host = "127.0.0.1:5000"
        with BOOTSTRAP_TAB_FOCUS_LOCK:
            targets = list_bootstrap_browser_targets()
            target_id = match_target_id_for_platform(targets, platform_key, request_host)
            if target_id:
                focus_bootstrap_target_by_id(target_id)
                return

            ensure_bootstrap_platform_tabs([platform_key], request_host)
            refreshed_id, _ = wait_for_bootstrap_platform_target(
                platform_key,
                request_host,
                timeout_seconds=2.8,
                poll_interval_seconds=0.14,
            )
            if refreshed_id:
                focus_bootstrap_target_by_id(refreshed_id)
    except Exception:
        pass


def run_platform_sync_queue(
    store: dict[str, Any],
    *,
    platform: str,
    task_ids: set[str],
    limit: int,
    headless: bool,
    force_manual_fallback: bool = False,
    restore_management_tab: bool = True,
) -> dict[str, Any]:
    if platform == "携程":
        platform_limit = max(limit, len(task_ids))
        return run_ctrip_sync_queue(
            store,
            limit=platform_limit,
            headless=headless,
            task_ids=task_ids,
            force_manual_fallback=force_manual_fallback,
            restore_management_tab=restore_management_tab,
        )

    if platform == "飞猪":
        platform_limit = max(limit, len(task_ids))
        return run_fliggy_sync_queue(
            store,
            limit=platform_limit,
            headless=headless,
            task_ids=task_ids,
            force_manual_fallback=force_manual_fallback,
            restore_management_tab=restore_management_tab,
        )

    if platform == "美团":
        platform_limit = max(limit, len(task_ids))
        return run_meituan_sync_queue(
            store,
            limit=platform_limit,
            headless=headless,
            task_ids=task_ids,
            restore_management_tab=restore_management_tab,
        )

    return {"processed": 0, "success": 0, "failed": 0, "items": []}


def normalize_sync_task_ids_map(task_ids_by_platform: dict[str, set[str]] | None) -> dict[str, set[str]]:
    normalized: dict[str, set[str]] = {platform: set() for platform in SYNC_TARGET_PLATFORMS}
    if not isinstance(task_ids_by_platform, dict):
        return normalized

    for platform in SYNC_TARGET_PLATFORMS:
        raw_ids = task_ids_by_platform.get(platform, set())
        if not isinstance(raw_ids, set):
            continue
        normalized[platform] = {str(item).strip() for item in raw_ids if str(item).strip()}

    return normalized


def auto_sync_platforms_after_change(
    store: dict[str, Any],
    *,
    source_platform: str,
    task_ids_by_platform: dict[str, set[str]] | None = None,
    force_manual_fallback: bool = False,
) -> dict[str, Any]:
    auto_enabled = env_flag("AUTO_SYNC_ENABLED", env_flag("AUTO_SYNC_CTRIP_ENABLED", True))

    normalized_ids_map = normalize_sync_task_ids_map(task_ids_by_platform)
    target_count_total = sum(len(task_ids) for task_ids in normalized_ids_map.values())

    if not auto_enabled:
        platform_reports = [
            {
                "platform": platform,
                "status": "disabled",
                "message": "自动同步未启用",
                "taskIds": sorted(normalized_ids_map.get(platform, set())),
                "targetTaskCount": len(normalized_ids_map.get(platform, set())),
                "processed": 0,
                "success": 0,
                "failed": 0,
                "items": [],
            }
            for platform in SYNC_TARGET_PLATFORMS
        ]
        return {
            "enabled": False,
            "sourcePlatform": source_platform,
            "targetTaskCount": target_count_total,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "platformReports": platform_reports,
        }

    limit_raw = os.getenv("AUTO_SYNC_LIMIT", os.getenv("AUTO_SYNC_CTRIP_LIMIT", "20"))
    try:
        limit = max(1, min(200, int(limit_raw)))
    except ValueError:
        limit = 20

    headless = env_flag("AUTO_SYNC_HEADLESS", env_flag("AUTO_SYNC_CTRIP_HEADLESS", False))

    report_map: dict[str, dict[str, Any]] = {}
    for platform in SYNC_TARGET_PLATFORMS:
        target_id_set = normalized_ids_map.get(platform, set())
        target_ids = sorted(target_id_set)
        target_count = len(target_id_set)

        if platform == source_platform:
            report_map[platform] = {
                "platform": platform,
                "status": "skipped",
                "message": "无需更新（当前下单平台）",
                "taskIds": target_ids,
                "targetTaskCount": target_count,
                "processed": 0,
                "success": 0,
                "failed": 0,
                "items": [],
            }
            continue

        if target_count == 0:
            report_map[platform] = {
                "platform": platform,
                "status": "noop",
                "message": "无需更新",
                "taskIds": [],
                "targetTaskCount": 0,
                "processed": 0,
                "success": 0,
                "failed": 0,
                "items": [],
            }
            continue

        focus_platform_tab_for_sync(platform)

        try:
            raw = run_platform_sync_queue(
                store,
                platform=platform,
                task_ids=target_id_set,
                limit=limit,
                headless=headless,
                force_manual_fallback=force_manual_fallback,
                restore_management_tab=False,
            )
            success = int(raw.get("success", 0))
            failed = int(raw.get("failed", 0))
            processed = int(raw.get("processed", 0))

            status = str(raw.get("status") or "").strip().lower()
            message = str(raw.get("message") or "").strip()

            items = raw.get("items", [])
            if not isinstance(items, list):
                items = []

            first_failed_message = ""
            for item in items:
                if not isinstance(item, dict):
                    continue
                if bool(item.get("ok", True)):
                    continue
                first_failed_message = str(item.get("message") or "").strip()
                if first_failed_message:
                    break

            if not status:
                if failed > 0:
                    if not message:
                        message = first_failed_message
                    if not message:
                        message = "同步失败"
                    status = "timeout" if "超时" in message else "failed"
                elif success > 0:
                    status = "success"
                    message = message or "已提交平台修改"
                else:
                    status = "noop"
                    message = message or "无需更新"

            if status in {"timeout", "failed"} and target_count > 0 and not items:
                items = [
                    {
                        "id": task_id,
                        "ok": False,
                        "message": message or "同步超时",
                    }
                    for task_id in target_ids
                ]

            report_map[platform] = {
                "platform": platform,
                "status": status,
                "message": message,
                "taskIds": target_ids,
                "targetTaskCount": target_count,
                "processed": processed,
                "success": success,
                "failed": failed,
                "items": items,
            }
        except Exception as exc:
            already_success_ids: list[str] = []
            for queue_item in store["syncQueue"]:
                if not isinstance(queue_item, dict):
                    continue
                if str(queue_item.get("targetPlatform") or "").strip() != platform:
                    continue

                queue_task_id = str(queue_item.get("id") or "").strip()
                if queue_task_id not in target_id_set:
                    continue

                queue_status = str(queue_item.get("status") or "").strip().lower()
                if queue_status == "success":
                    already_success_ids.append(queue_task_id)

            if target_ids and len(already_success_ids) == len(target_ids):
                success_ids = sorted(set(already_success_ids))
                report_map[platform] = {
                    "platform": platform,
                    "status": "success",
                    "message": f"已提交平台修改 {len(success_ids)} 条",
                    "taskIds": success_ids,
                    "targetTaskCount": len(success_ids),
                    "processed": len(success_ids),
                    "success": len(success_ids),
                    "failed": 0,
                    "items": [
                        {
                            "id": task_id,
                            "ok": True,
                            "message": "已提交平台修改",
                        }
                        for task_id in success_ids
                    ],
                    "warning": f"已忽略清理阶段异常: {exc}",
                }
                continue

            failed_items = mark_sync_tasks_failed(
                store,
                platform=platform,
                task_ids=set(target_ids),
                message="同步超时",
            )
            failed_item_ids = {
                str(item.get("id") or "").strip()
                for item in failed_items
                if isinstance(item, dict)
            }
            all_failed_items = list(failed_items)
            for task_id in target_ids:
                if task_id in failed_item_ids:
                    continue
                all_failed_items.append(
                    {
                        "id": task_id,
                        "ok": False,
                        "message": "同步超时",
                    }
                )

            report_map[platform] = {
                "platform": platform,
                "status": "timeout",
                "message": "同步超时",
                "taskIds": target_ids,
                "targetTaskCount": target_count,
                "processed": len(failed_items),
                "success": 0,
                "failed": len(all_failed_items),
                "items": all_failed_items,
                "error": str(exc),
            }

    restore_local_management_tab_after_sync()

    platform_reports = [report_map[platform] for platform in SYNC_TARGET_PLATFORMS]
    total_processed = sum(int(item.get("processed", 0)) for item in platform_reports)
    total_success = sum(int(item.get("success", 0)) for item in platform_reports)
    total_failed = sum(int(item.get("failed", 0)) for item in platform_reports)

    return {
        "enabled": True,
        "sourcePlatform": source_platform,
        "targetTaskCount": target_count_total,
        "processed": total_processed,
        "success": total_success,
        "failed": total_failed,
        "platformReports": platform_reports,
    }


def auto_sync_ctrip_after_change(
    store: dict[str, Any],
    *,
    task_ids: set[str] | None = None,
) -> dict[str, Any]:
    ids = task_ids if task_ids is not None else set()
    return auto_sync_platforms_after_change(
        store,
        source_platform="本地系统",
        task_ids_by_platform={"携程": set(ids)},
    )


def build_running_platform_report(
    platform: str,
    task_ids: set[str],
    *,
    message: str = "同步中，请稍候...",
) -> dict[str, Any]:
    sorted_ids = sorted({str(item).strip() for item in task_ids if str(item).strip()})
    return {
        "platform": platform,
        "status": "running",
        "message": message,
        "taskIds": sorted_ids,
        "targetTaskCount": len(sorted_ids),
        "processed": 0,
        "success": 0,
        "failed": 0,
        "items": [
            {
                "id": task_id,
                "ok": False,
                "message": message,
            }
            for task_id in sorted_ids
        ],
    }


def recompute_sync_report_totals(sync_report: dict[str, Any]) -> dict[str, Any]:
    platform_reports = sync_report.get("platformReports", [])
    if not isinstance(platform_reports, list):
        platform_reports = []

    sync_report["targetTaskCount"] = sum(int(item.get("targetTaskCount", 0)) for item in platform_reports)
    sync_report["processed"] = sum(int(item.get("processed", 0)) for item in platform_reports)
    sync_report["success"] = sum(int(item.get("success", 0)) for item in platform_reports)
    sync_report["failed"] = sum(int(item.get("failed", 0)) for item in platform_reports)
    return sync_report


def upsert_platform_report(sync_report: dict[str, Any], platform_report: dict[str, Any]) -> dict[str, Any]:
    platform = str(platform_report.get("platform") or "").strip()
    if not platform:
        return sync_report

    reports = sync_report.get("platformReports", [])
    if not isinstance(reports, list):
        reports = []

    replaced = False
    merged: list[dict[str, Any]] = []
    for item in reports:
        if not isinstance(item, dict):
            continue
        if str(item.get("platform") or "").strip() == platform:
            merged.append(platform_report)
            replaced = True
            continue
        merged.append(item)

    if not replaced:
        merged.append(platform_report)

    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    report_map = {
        str(item.get("platform") or "").strip(): item
        for item in merged
        if isinstance(item, dict)
    }
    for platform_name in SYNC_TARGET_PLATFORMS:
        report_item = report_map.get(platform_name)
        if report_item is None:
            continue
        ordered.append(report_item)
        seen.add(platform_name)

    for key, value in report_map.items():
        if not key or key in seen:
            continue
        ordered.append(value)

    sync_report["platformReports"] = ordered
    return recompute_sync_report_totals(sync_report)


def trim_async_sync_jobs_inplace() -> None:
    if len(ASYNC_SYNC_JOBS) <= MAX_ASYNC_SYNC_JOBS:
        return

    sorted_items = sorted(
        ASYNC_SYNC_JOBS.items(),
        key=lambda pair: str(pair[1].get("updatedAt") or pair[1].get("createdAt") or ""),
    )
    overflow = len(ASYNC_SYNC_JOBS) - MAX_ASYNC_SYNC_JOBS
    for idx in range(max(0, overflow)):
        stale_id = str(sorted_items[idx][0])
        ASYNC_SYNC_JOBS.pop(stale_id, None)


def create_async_sync_job(source_platform: str, initial_report: dict[str, Any]) -> str:
    job_id = str(uuid4())
    snapshot = json.loads(json.dumps(initial_report, ensure_ascii=False))
    with ASYNC_SYNC_JOBS_LOCK:
        ASYNC_SYNC_JOBS[job_id] = {
            "id": job_id,
            "sourcePlatform": source_platform,
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
            "completed": False,
            "syncReport": snapshot,
            "message": "",
        }
        trim_async_sync_jobs_inplace()
    return job_id


def get_async_sync_job_snapshot(job_id: str) -> dict[str, Any] | None:
    target_id = str(job_id or "").strip()
    if not target_id:
        return None

    with ASYNC_SYNC_JOBS_LOCK:
        job = ASYNC_SYNC_JOBS.get(target_id)
        if not isinstance(job, dict):
            return None
        return json.loads(json.dumps(job, ensure_ascii=False))


def run_meituan_async_sync_job(
    job_id: str,
    *,
    source_platform: str,
    task_ids: set[str],
) -> None:
    meituan_ids = {str(item).strip() for item in task_ids if str(item).strip()}
    if not meituan_ids:
        return

    try:
        store = load_store()
        meituan_only_ids = {"携程": set(), "飞猪": set(), "美团": set(meituan_ids)}
        meituan_report = auto_sync_platforms_after_change(
            store,
            source_platform=source_platform,
            task_ids_by_platform=meituan_only_ids,
        )
        save_store(store)

        platform_reports = meituan_report.get("platformReports", [])
        if not isinstance(platform_reports, list):
            platform_reports = []

        meituan_platform_report = next(
            (
                item for item in platform_reports
                if isinstance(item, dict) and str(item.get("platform") or "").strip() == "美团"
            ),
            build_running_platform_report("美团", meituan_ids, message="同步状态未知，请稍后刷新"),
        )

        with ASYNC_SYNC_JOBS_LOCK:
            job = ASYNC_SYNC_JOBS.get(job_id)
            if not isinstance(job, dict):
                return

            sync_report = job.get("syncReport", {})
            if not isinstance(sync_report, dict):
                sync_report = {"enabled": True, "sourcePlatform": source_platform, "platformReports": []}

            upsert_platform_report(sync_report, meituan_platform_report)
            job["syncReport"] = sync_report
            job["completed"] = True
            job["updatedAt"] = now_iso()
            job["message"] = str(meituan_platform_report.get("message") or "")
    except Exception as exc:
        failed_report = {
            "platform": "美团",
            "status": "failed",
            "message": str(exc).strip() or "美团同步失败",
            "taskIds": sorted(meituan_ids),
            "targetTaskCount": len(meituan_ids),
            "processed": 0,
            "success": 0,
            "failed": len(meituan_ids),
            "items": [
                {
                    "id": task_id,
                    "ok": False,
                    "message": str(exc).strip() or "美团同步失败",
                }
                for task_id in sorted(meituan_ids)
            ],
        }

        with ASYNC_SYNC_JOBS_LOCK:
            job = ASYNC_SYNC_JOBS.get(job_id)
            if not isinstance(job, dict):
                return

            sync_report = job.get("syncReport", {})
            if not isinstance(sync_report, dict):
                sync_report = {"enabled": True, "sourcePlatform": source_platform, "platformReports": []}

            upsert_platform_report(sync_report, failed_report)
            job["syncReport"] = sync_report
            job["completed"] = True
            job["updatedAt"] = now_iso()
            job["message"] = str(failed_report.get("message") or "")


def allocate_rooms_for_booking(
    store: dict[str, Any],
    *,
    room_type: str,
    days: list[str],
    quantity: int,
    preferred_room_ids: list[str],
    exclude_booking_id: str = "",
) -> list[dict[str, str]]:
    if quantity <= 0:
        raise ValueError("数量必须大于 0")

    open_floor_ids = get_open_floor_ids(store)
    available_rooms = list_available_rooms(
        store,
        room_type=room_type,
        days=days,
        exclude_booking_id=exclude_booking_id,
    )
    available_map = {str(item.get("id") or ""): item for item in available_rooms}

    selected: list[dict[str, str]] = []
    selected_ids: set[str] = set()

    for room_id in preferred_room_ids:
        if room_id in selected_ids:
            continue

        room = get_room_by_id(store, room_id)
        if room is None:
            raise ValueError("选择的房号不存在")
        if str(room.get("roomType") or "").strip() != room_type:
            raise ValueError("所选房号与房型不匹配")

        floor_id = str(room.get("floorId") or "").strip()
        if floor_id not in open_floor_ids:
            raise ValueError("所选房号所在楼层未开放")

        manual_status = str(room.get("manualStatus") or "空闲").strip()
        if manual_status == "维修":
            raise ValueError("所选房号当前为维修状态")

        if room_conflicts_in_days(store, room_id, days, exclude_booking_id=exclude_booking_id):
            raise ValueError("所选房号在该时段已被占用")

        room_number = str(room.get("number") or "").strip()
        selected.append(
            {
                "id": room_id,
                "number": room_number,
            }
        )
        selected_ids.add(room_id)

    if len(selected) > quantity:
        raise ValueError("选择房号数量超过预订数量")

    for item in available_rooms:
        if len(selected) >= quantity:
            break
        room_id = str(item.get("id") or "")
        if room_id in selected_ids:
            continue
        selected.append(
            {
                "id": room_id,
                "number": str(item.get("number") or ""),
            }
        )
        selected_ids.add(room_id)

    if len(selected) < quantity:
        raise ValueError("可用房号不足，请减少数量或调整日期")

    return selected


def build_room_booked_map(store: dict[str, Any], room_type: str) -> dict[str, int]:
    booked_map: dict[str, int] = {}

    for booking in store["bookings"]:
        if str(booking.get("roomType") or "").strip() != room_type:
            continue

        booking_daily = booking.get("dailyQuantity", {})
        if not isinstance(booking_daily, dict):
            continue

        for target_date, qty_raw in booking_daily.items():
            day = str(target_date).strip()
            qty = to_int(qty_raw, 0)
            if not day or qty <= 0:
                continue
            booked_map[day] = booked_map.get(day, 0) + qty

    return booked_map


def apply_local_initialization(store: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    room_type = payload["roomType"]
    new_total = payload["quantity"]
    sync_platforms = payload["syncPlatforms"]

    previous_total = int(store["roomConfig"][room_type])
    store["roomConfig"][room_type] = new_total

    booked_map = build_room_booked_map(store, room_type)
    affected_days = sorted(set(store["inventory"].keys()) | set(booked_map.keys()))

    daily_changes: dict[str, dict[str, Any]] = {}
    apply_platforms = [
        platform
        for platform in PLATFORMS
        if should_apply_platform_delta(room_type, platform)
    ]

    for target_date in affected_days:
        day_map = ensure_day_inventory(store, target_date)
        room_entry = day_map[room_type]
        booked_qty = max(0, to_int(booked_map.get(target_date, 0), 0))
        recalculated_available = max(0, new_total - booked_qty)

        local_before = int(room_entry["localAvailable"])
        platform_changes: dict[str, dict[str, int]] = {}
        for platform in PLATFORMS:
            before = int(room_entry["platforms"][platform])
            after = before
            if platform in apply_platforms:
                after = recalculated_available
            platform_changes[platform] = {
                "before": before,
                "after": after,
            }

        daily_changes[target_date] = {
            "local": {
                "before": local_before,
                "after": recalculated_available,
            },
            "platforms": platform_changes,
            "booked": booked_qty,
        }

    for target_date, change in daily_changes.items():
        day_map = ensure_day_inventory(store, target_date)
        room_entry = day_map[room_type]
        room_entry["localAvailable"] = change["local"]["after"]
        for platform, platform_change in change["platforms"].items():
            room_entry["platforms"][platform] = platform_change["after"]

    if sync_platforms:
        append_init_sync_tasks(
            store,
            room_type=room_type,
            quantity=new_total,
            daily_changes=daily_changes,
        )

    record = {
        "id": str(uuid4()),
        "createdAt": now_iso(),
        "type": "初始化房量",
        "roomType": room_type,
        "quantity": new_total,
        "previousTotal": previous_total,
        "newTotal": new_total,
        "affectedNights": len(affected_days),
        "syncRequested": sync_platforms,
        "dailyChanges": daily_changes,
    }
    append_history_record(store, record)
    return record


def apply_adjustment(store: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    room_type = payload["roomType"]
    source_platform = payload["platform"]
    status = payload["status"]
    quantity = payload["quantity"]
    days = list(payload["days"])
    booking_id = payload.get("bookingId", "")
    preferred_room_ids = [
        str(item).strip()
        for item in payload.get("roomIds", [])
        if str(item).strip()
    ]

    delta = STATUSES.get(status, 0) * quantity
    total = int(store["roomConfig"][room_type])

    all_platforms = list(PLATFORMS)
    apply_platforms = [
        platform
        for platform in all_platforms
        if should_apply_platform_delta(room_type, platform)
    ]

    daily_changes: dict[str, dict[str, Any]] = {}
    record_check_in = payload["checkInDate"]
    record_check_out = payload["checkOutDate"]
    record_nights = payload["nights"]
    record_quantity = quantity
    delta_for_record: int | None = delta
    record_room_ids: list[str] = []
    record_room_numbers: list[str] = []

    if status == "取消":
        booking = get_booking_by_id(store, booking_id)
        if booking is None:
            raise ValueError("未找到要取消的订单")
        if str(booking.get("roomType")) != room_type:
            raise ValueError("取消订单与当前房型不匹配")
        if str(booking.get("sourcePlatform")) != source_platform:
            raise ValueError("取消订单与当前平台不匹配")

        booking_daily = booking.get("dailyQuantity", {})
        if not isinstance(booking_daily, dict):
            raise ValueError("订单数据异常，无法取消")

        cancel_day_qty = {
            day: to_int(qty, 0)
            for day, qty in booking_daily.items()
            if to_int(qty, 0) > 0
        }
        days = sorted(cancel_day_qty.keys())
        if not days:
            raise ValueError("该订单已无可取消晚数")

        record_check_in = str(booking.get("checkInDate") or payload["checkInDate"])
        record_check_out = str(booking.get("checkOutDate") or payload["checkOutDate"])
        record_nights = len(days)
        record_quantity = max(cancel_day_qty.values())
        delta_for_record = None
        record_room_ids = get_booking_room_ids(booking)
        record_room_numbers = get_booking_room_numbers(booking)

    if status == "修改":
        booking = get_booking_by_id(store, booking_id)
        if booking is None:
            raise ValueError("未找到要修改的订单")
        if str(booking.get("roomType") or "").strip() != room_type:
            raise ValueError("修改订单与当前房型不匹配")
        if str(booking.get("sourcePlatform") or "").strip() != source_platform:
            raise ValueError("修改订单与当前平台不匹配")

        old_daily_raw = booking.get("dailyQuantity", {})
        if not isinstance(old_daily_raw, dict):
            raise ValueError("订单数据异常，无法修改")

        old_daily = {
            str(day): to_int(qty, 0)
            for day, qty in old_daily_raw.items()
            if to_int(qty, 0) > 0
        }
        old_days = sorted(old_daily.keys())
        if not old_days:
            raise ValueError("该订单已无可修改晚数")

        modify_quantity = get_booking_quantity(booking)
        allocated_rooms = allocate_rooms_for_booking(
            store,
            room_type=room_type,
            days=days,
            quantity=modify_quantity,
            preferred_room_ids=preferred_room_ids,
            exclude_booking_id=booking_id,
        )
        record_room_ids = [item["id"] for item in allocated_rooms]
        record_room_numbers = [item["number"] for item in allocated_rooms]

        affected_days = sorted(set(old_days) | set(days))
        daily_changes = {}

        for target_date in affected_days:
            day_map = ensure_day_inventory(store, target_date)
            room_entry = day_map[room_type]

            old_qty = to_int(old_daily.get(target_date, 0), 0)
            new_qty = modify_quantity if target_date in days else 0
            day_delta = old_qty - new_qty

            local_before = int(room_entry["localAvailable"])
            local_after = local_before + day_delta
            if local_after < 0:
                raise ValueError(
                    f"{target_date} {room_type} 本地库存会变成负数：当前 {local_before}，本次变化 {day_delta}"
                )
            if local_after > total:
                raise ValueError(
                    f"{target_date} {room_type} 本地库存会超过总房量：当前 {local_before}，本次变化 {day_delta}"
                )

            platform_changes: dict[str, dict[str, int]] = {}
            for platform in all_platforms:
                before = int(room_entry["platforms"][platform])
                after = before
                if platform in apply_platforms:
                    after = before + day_delta
                    if after < 0:
                        raise ValueError(
                            f"{target_date} {room_type} 在 {platform} 会变成负数：当前 {before}，本次变化 {day_delta}"
                        )
                    if after > total:
                        raise ValueError(
                            f"{target_date} {room_type} 在 {platform} 会超过总房量：当前 {before}，本次变化 {day_delta}"
                        )
                platform_changes[platform] = {"before": before, "after": after}

            daily_changes[target_date] = {
                "local": {"before": local_before, "after": local_after},
                "platforms": platform_changes,
            }

        for target_date, changes in daily_changes.items():
            day_map = ensure_day_inventory(store, target_date)
            room_entry = day_map[room_type]
            room_entry["localAvailable"] = changes["local"]["after"]
            for platform, change in changes["platforms"].items():
                room_entry["platforms"][platform] = change["after"]

        booking["checkInDate"] = payload["checkInDate"]
        booking["checkOutDate"] = payload["checkOutDate"]
        booking["quantity"] = modify_quantity
        booking["dailyQuantity"] = {day: modify_quantity for day in days}
        booking["roomIds"] = record_room_ids
        booking["roomNumbers"] = record_room_numbers
        booking["roomId"] = record_room_ids[0] if record_room_ids else None
        booking["roomNumber"] = record_room_numbers[0] if record_room_numbers else None
        booking["updatedAt"] = now_iso()

        append_adjust_sync_tasks(
            store,
            source_platform=source_platform,
            room_type=room_type,
            status="修改",
            daily_changes=daily_changes,
        )

        record = {
            "id": str(uuid4()),
            "createdAt": now_iso(),
            "type": "调整房量",
            "checkInDate": payload["checkInDate"],
            "checkOutDate": payload["checkOutDate"],
            "nights": payload["nights"],
            "roomType": room_type,
            "sourcePlatform": source_platform,
            "status": "修改",
            "quantity": modify_quantity,
            "delta": None,
            "bookingId": booking_id,
            "roomIds": record_room_ids,
            "roomNumbers": record_room_numbers,
            "roomId": record_room_ids[0] if record_room_ids else None,
            "roomNumber": record_room_numbers[0] if record_room_numbers else None,
            "dailyChanges": daily_changes,
        }
        append_history_record(store, record)
        return record

    if status == "预订":
        allocated_rooms = allocate_rooms_for_booking(
            store,
            room_type=room_type,
            days=days,
            quantity=quantity,
            preferred_room_ids=preferred_room_ids,
        )
        record_room_ids = [item["id"] for item in allocated_rooms]
        record_room_numbers = [item["number"] for item in allocated_rooms]

    for target_date in days:
        day_map = ensure_day_inventory(store, target_date)
        room_entry = day_map[room_type]

        day_quantity = quantity
        day_delta = delta
        if status == "取消":
            day_quantity = to_int(cancel_day_qty.get(target_date, 0), 0)
            if day_quantity <= 0:
                continue
            day_delta = day_quantity

        local_before = int(room_entry["localAvailable"])
        local_after = local_before + day_delta
        if local_after < 0:
            raise ValueError(
                f"{target_date} {room_type} 本地库存会变成负数：当前 {local_before}，本次变化 {day_delta}"
            )
        if local_after > total:
            raise ValueError(
                f"{target_date} {room_type} 本地库存会超过总房量：当前 {local_before}，本次变化 {day_delta}"
            )

        platform_changes: dict[str, dict[str, int]] = {}
        for platform in all_platforms:
            before = int(room_entry["platforms"][platform])
            after = before
            if platform in apply_platforms:
                after = before + day_delta
                if after < 0:
                    raise ValueError(
                        f"{target_date} {room_type} 在 {platform} 会变成负数：当前 {before}，本次变化 {day_delta}"
                    )
                if after > total:
                    raise ValueError(
                        f"{target_date} {room_type} 在 {platform} 会超过总房量：当前 {before}，本次变化 {day_delta}"
                    )
            platform_changes[platform] = {
                "before": before,
                "after": after,
            }

        daily_changes[target_date] = {
            "local": {
                "before": local_before,
                "after": local_after,
            },
            "platforms": platform_changes,
        }

    for target_date, changes in daily_changes.items():
        day_map = ensure_day_inventory(store, target_date)
        room_entry = day_map[room_type]
        room_entry["localAvailable"] = changes["local"]["after"]
        for platform, change in changes["platforms"].items():
            room_entry["platforms"][platform] = change["after"]

    if status == "预订":
        new_booking = {
            "id": str(uuid4()),
            "createdAt": now_iso(),
            "roomType": room_type,
            "sourcePlatform": source_platform,
            "checkInDate": payload["checkInDate"],
            "checkOutDate": payload["checkOutDate"],
            "quantity": quantity,
            "dailyQuantity": {day: quantity for day in days},
            "roomIds": record_room_ids,
            "roomNumbers": record_room_numbers,
            "roomId": record_room_ids[0] if record_room_ids else None,
            "roomNumber": record_room_numbers[0] if record_room_numbers else None,
        }
        store["bookings"].insert(0, new_booking)
    elif status == "取消":
        booking = get_booking_by_id(store, booking_id)
        if booking is not None:
            booking_daily = booking.get("dailyQuantity", {})
            if isinstance(booking_daily, dict):
                for target_date in days:
                    if target_date in booking_daily:
                        booking_daily[target_date] = 0
                booking["updatedAt"] = now_iso()

    append_adjust_sync_tasks(
        store,
        source_platform=source_platform,
        room_type=room_type,
        status=status,
        daily_changes=daily_changes,
    )

    record = {
        "id": str(uuid4()),
        "createdAt": now_iso(),
        "type": "调整房量",
        "checkInDate": record_check_in,
        "checkOutDate": record_check_out,
        "nights": record_nights,
        "roomType": room_type,
        "sourcePlatform": source_platform,
        "status": status,
        "quantity": record_quantity,
        "delta": delta_for_record,
        "bookingId": booking_id if status == "取消" else None,
        "roomIds": record_room_ids if record_room_ids else None,
        "roomNumbers": record_room_numbers if record_room_numbers else None,
        "roomId": record_room_ids[0] if record_room_ids else None,
        "roomNumber": record_room_numbers[0] if record_room_numbers else None,
        "dailyChanges": daily_changes,
    }
    append_history_record(store, record)

    return record


def parse_record_days(record: dict[str, Any]) -> list[str]:
    if isinstance(record.get("days"), list):
        return [str(item) for item in record["days"] if str(item)]

    if isinstance(record.get("dailyChanges"), dict):
        return list(record["dailyChanges"].keys())

    if isinstance(record.get("localChanges"), dict):
        return list(record["localChanges"].keys())

    check_in_raw = str(record.get("checkInDate") or record.get("startDate") or "").strip()
    check_out_raw = str(record.get("checkOutDate") or record.get("endDate") or "").strip()

    if check_in_raw and check_out_raw:
        try:
            check_in = date.fromisoformat(check_in_raw)
            check_out = date.fromisoformat(check_out_raw)
        except ValueError:
            return []

        if check_out <= check_in:
            return [check_in.isoformat()]

        result: list[str] = []
        cursor = check_in
        while cursor < check_out:
            result.append(cursor.isoformat())
            cursor += timedelta(days=1)
        return result

    single_date = str(record.get("date") or "").strip()
    if single_date:
        return [single_date]

    return []


def build_source_booking_map(
    store: dict[str, Any],
    day_list: list[str],
) -> dict[str, dict[str, dict[str, dict[str, int]]]]:
    day_set = set(day_list)

    order_count_map: dict[str, dict[str, dict[str, dict[str, int]]]] = {
        room_type: {} for room_type in store["roomConfig"].keys()
    }

    for booking in store["bookings"]:
        room_type = str(booking.get("roomType") or "").strip()
        if room_type not in order_count_map:
            continue

        source_platform = str(booking.get("sourcePlatform") or "").strip()
        if source_platform not in PLATFORMS:
            continue

        booking_check_in = str(booking.get("checkInDate") or "").strip()

        booking_daily = booking.get("dailyQuantity", {})
        if not isinstance(booking_daily, dict):
            continue

        active_days = sorted(
            [
                str(day)
                for day, qty in booking_daily.items()
                if str(day) in day_set and to_int(qty, 0) > 0
            ]
        )
        if not active_days:
            continue

        room_map = order_count_map[room_type]

        for target_date in active_days:
            qty = to_int(booking_daily.get(target_date, 0), 0)
            if qty <= 0:
                continue
            day_map = room_map.setdefault(target_date, {})
            stats = day_map.setdefault(source_platform, {"new": 0, "stay": 0})
            if target_date == booking_check_in:
                stats["new"] += qty
            else:
                stats["stay"] += qty

    result: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    for room_type in store["roomConfig"].keys():
        result[room_type] = {}
        for target_date in day_list:
            raw_day_map = order_count_map.get(room_type, {}).get(target_date, {})
            day_map: dict[str, dict[str, int]] = {}
            for platform in PLATFORMS:
                stats = raw_day_map.get(platform)
                if not isinstance(stats, dict):
                    continue
                new_count = to_int(stats.get("new", 0), 0)
                stay_count = to_int(stats.get("stay", 0), 0)
                normalized: dict[str, int] = {}
                if new_count > 0:
                    normalized["new"] = new_count
                if stay_count > 0:
                    normalized["stay"] = stay_count
                if normalized:
                    day_map[platform] = normalized
            result[room_type][target_date] = day_map

    return result


def build_calendar_payload(store: dict[str, Any], base_date: date, window_days: int) -> dict[str, Any]:
    day_list: list[str] = []
    dates_meta: list[dict[str, str]] = []

    for offset in range(window_days):
        target = base_date + timedelta(days=offset)
        day_str = target.isoformat()
        day_list.append(day_str)
        dates_meta.append(
            {
                "date": day_str,
                "weekday": WEEKDAY_NAMES[target.weekday()],
                "label": f"{target.month}-{target.day}",
            }
        )

    source_booking_map = build_source_booking_map(store, day_list)

    rows: list[dict[str, Any]] = []
    for room_type, total in store["roomConfig"].items():
        cells: list[dict[str, Any]] = []
        for target_date in day_list:
            day_map = ensure_day_inventory(store, target_date)
            room_entry = day_map[room_type]

            cells.append(
                {
                    "date": target_date,
                    "remaining": int(room_entry["localAvailable"]),
                    "bookings": source_booking_map.get(room_type, {}).get(target_date, {}),
                }
            )

        rows.append(
            {
                "roomType": room_type,
                "total": total,
                "cells": cells,
            }
        )

    return {
        "dates": dates_meta,
        "rows": rows,
    }


def parse_target_date(raw_value: str) -> date:
    raw = str(raw_value or "").strip()
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("date 格式必须是 YYYY-MM-DD") from exc


def get_floor_by_id(store: dict[str, Any], floor_id: str) -> dict[str, Any] | None:
    for floor in store["floors"]:
        if str(floor.get("id") or "").strip() == floor_id:
            return floor
    return None


def is_room_number_taken(store: dict[str, Any], room_number: str, exclude_room_id: str = "") -> bool:
    target = room_number.strip().lower()
    if not target:
        return False

    for room in store["rooms"]:
        current_id = str(room.get("id") or "").strip()
        if exclude_room_id and current_id == exclude_room_id:
            continue
        current_number = str(room.get("number") or "").strip().lower()
        if current_number == target:
            return True
    return False


def build_room_status_lookup(store: dict[str, Any], target_date: str) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    for booking in store["bookings"]:
        room_ids = get_booking_room_ids(booking)
        if not room_ids:
            continue

        booking_daily = booking.get("dailyQuantity", {})
        if not isinstance(booking_daily, dict):
            continue

        active_days = sorted(
            [
                str(day)
                for day, qty in booking_daily.items()
                if to_int(qty, 0) > 0 and str(day)
            ]
        )
        if not active_days:
            continue

        for room_id in room_ids:
            info = lookup.setdefault(room_id, {"current": None, "next": None, "nextDay": ""})

            if target_date in active_days:
                info["current"] = booking
                continue

            future_days = [day for day in active_days if day > target_date]
            if not future_days:
                continue

            first_future_day = future_days[0]
            current_next_day = str(info.get("nextDay") or "")
            if not current_next_day or first_future_day < current_next_day:
                info["next"] = booking
                info["nextDay"] = first_future_day

    return lookup


def list_unfinished_orders(store: dict[str, Any], target_date: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for booking in store["bookings"]:
        if not has_positive_booking_qty(booking):
            continue

        active_days = parse_booking_days(booking)
        if not active_days:
            continue

        pending_days = [day for day in active_days if day >= target_date]
        if not pending_days:
            continue

        room_numbers = get_booking_room_numbers(booking)
        quantity = get_booking_quantity(booking)
        stage = "进行中" if target_date in active_days else "待入住"

        items.append(
            {
                "id": str(booking.get("id") or ""),
                "platform": str(booking.get("sourcePlatform") or "-"),
                "roomType": str(booking.get("roomType") or "-"),
                "checkInDate": str(booking.get("checkInDate") or ""),
                "checkOutDate": str(booking.get("checkOutDate") or ""),
                "quantity": quantity,
                "roomNumbers": room_numbers,
                "stage": stage,
                "remainingNights": len(pending_days),
            }
        )

    items.sort(
        key=lambda item: (
            str(item.get("checkInDate") or ""),
            str(item.get("platform") or ""),
            str(item.get("roomType") or ""),
        )
    )
    return items


def build_room_management_payload(store: dict[str, Any], target_date: date) -> dict[str, Any]:
    target_day = target_date.isoformat()
    status_lookup = build_room_status_lookup(store, target_day)
    floor_name_map = get_floor_name_map(store)
    unfinished_orders = list_unfinished_orders(store, target_day)

    rooms_by_floor: dict[str, list[dict[str, Any]]] = {}
    for room in store["rooms"]:
        floor_id = str(room.get("floorId") or "").strip()
        rooms_by_floor.setdefault(floor_id, []).append(room)

    floors_payload: list[dict[str, Any]] = []
    occupied_count = 0
    upcoming_count = 0
    maintenance_count = 0
    idle_count = 0
    total_rooms = 0
    open_floor_count = 0
    closed_floor_count = 0

    for floor in store["floors"]:
        floor_id = str(floor.get("id") or "").strip()
        floor_open = bool(floor.get("isOpen", True))
        if floor_open:
            open_floor_count += 1
        else:
            closed_floor_count += 1

        floor_rooms = sorted(
            rooms_by_floor.get(floor_id, []),
            key=lambda item: str(item.get("number") or ""),
        )

        room_items: list[dict[str, Any]] = []
        floor_occupied = 0
        for room in floor_rooms:
            room_id = str(room.get("id") or "").strip()
            number = str(room.get("number") or "")
            room_type = str(room.get("roomType") or "")
            manual_status = str(room.get("manualStatus") or "空闲").strip()
            if manual_status not in {"空闲", "维修"}:
                manual_status = "空闲"
            status_info = status_lookup.get(room_id, {})

            current_booking = status_info.get("current")
            next_booking = status_info.get("next")

            status = "空闲"
            reservation_text = "-"
            if not floor_open:
                status = "未开放"
                reservation_text = "楼层暂未开放"
            elif isinstance(current_booking, dict):
                status = "在住"
                occupied_count += 1
                floor_occupied += 1
                source_platform = str(current_booking.get("sourcePlatform") or "-")
                check_in = str(current_booking.get("checkInDate") or "")
                check_out = str(current_booking.get("checkOutDate") or "")
                reservation_text = f"{source_platform} {check_in}~{check_out}"
            elif manual_status == "维修":
                status = "维修"
                reservation_text = "维修中"
                maintenance_count += 1
            elif isinstance(next_booking, dict):
                status = "待入住"
                source_platform = str(next_booking.get("sourcePlatform") or "-")
                check_in = str(next_booking.get("checkInDate") or "")
                check_out = str(next_booking.get("checkOutDate") or "")
                reservation_text = f"{source_platform} {check_in}~{check_out}"
                upcoming_count += 1
            else:
                idle_count += 1

            room_items.append(
                {
                    "id": room_id,
                    "number": number,
                    "roomType": room_type,
                    "floorId": floor_id,
                    "floorName": floor_name_map.get(floor_id, "未分层"),
                    "floorOpen": floor_open,
                    "status": status,
                    "manualStatus": manual_status,
                    "reservationText": reservation_text,
                }
            )
            total_rooms += 1

        floors_payload.append(
            {
                "id": floor_id,
                "name": str(floor.get("name") or ""),
                "isOpen": floor_open,
                "roomCount": len(room_items),
                "occupiedCount": floor_occupied,
                "rooms": room_items,
            }
        )

    backup_info = normalize_backup_info(store.get("backupInfo"))

    return {
        "date": target_day,
        "roomTypes": [
            {"name": name, "total": total}
            for name, total in store["roomConfig"].items()
        ],
        "floors": floors_payload,
        "unfinishedOrders": unfinished_orders,
        "summary": {
            "totalRooms": total_rooms,
            "occupiedRooms": occupied_count,
            "upcomingRooms": upcoming_count,
            "maintenanceRooms": maintenance_count,
            "idleRooms": idle_count,
            "unfinishedOrdersCount": len(unfinished_orders),
            "openFloorCount": open_floor_count,
            "closedFloorCount": closed_floor_count,
        },
        "backupInfo": {
            "lastExportDate": str(backup_info.get("lastExportDate") or ""),
            "lastExportAt": str(backup_info.get("lastExportAt") or ""),
            "lastAutoBackupAt": str(backup_info.get("lastAutoBackupAt") or ""),
            "autoBackupIntervalHours": float(backup_info.get("autoBackupIntervalHours") or 0),
        },
    }


@app.get("/")
def bootstrap_page() -> Any:
    return render_template("bootstrap.html")


@app.get("/dashboard")
def index() -> Any:
    return render_template("index.html")


@app.get("/rooms")
def rooms_page() -> Any:
    return render_template("rooms.html")


def normalize_bootstrap_platforms(raw_platforms: Any) -> list[str]:
    default_platforms = ["ctrip", "fliggy", "meituan"]
    if not isinstance(raw_platforms, list):
        return default_platforms

    alias_map = {
        "ctrip": "ctrip",
        "携程": "ctrip",
        "fliggy": "fliggy",
        "飞猪": "fliggy",
        "meituan": "meituan",
        "美团": "meituan",
        "all": "all",
        "全部": "all",
    }

    selected: list[str] = []
    for item in raw_platforms:
        key = alias_map.get(str(item or "").strip().lower(), "")
        if key == "all":
            return default_platforms
        if key and key not in selected:
            selected.append(key)

    return selected or default_platforms


def get_bootstrap_cdp_version_url() -> str:
    return f"{get_bootstrap_cdp_base_url()}/json/version"


def get_bootstrap_cdp_base_url() -> str:
    cdp_endpoint = os.getenv("SYNC_BROWSER_CDP_ENDPOINT", os.getenv("SYNC_BROWSER_CDP_PORT", "9333")).strip()
    if not cdp_endpoint:
        cdp_endpoint = "9333"

    if cdp_endpoint.isdigit():
        cdp_endpoint = f"http://127.0.0.1:{cdp_endpoint}"

    if not cdp_endpoint.startswith("http://") and not cdp_endpoint.startswith("https://"):
        cdp_endpoint = f"http://{cdp_endpoint}"

    return cdp_endpoint.rstrip("/")


def normalize_focus_platform(raw_platform: Any) -> str:
    alias_map = {
        "ctrip": "ctrip",
        "携程": "ctrip",
        "fliggy": "fliggy",
        "飞猪": "fliggy",
        "meituan": "meituan",
        "美团": "meituan",
        "dashboard": "dashboard",
        "管理系统": "dashboard",
        "本地": "dashboard",
        "local": "dashboard",
    }
    key = str(raw_platform or "").strip().lower()
    return alias_map.get(key, "")


def normalize_focus_platforms(raw_platforms: Any) -> list[str]:
    if not isinstance(raw_platforms, (list, tuple, set)):
        raw_platforms = [raw_platforms]

    selected: list[str] = []
    for item in raw_platforms:
        key = normalize_focus_platform(item)
        if key and key not in selected:
            selected.append(key)
    return selected


def resolve_focus_target_url(platform_key: str, request_host: str) -> str:
    if platform_key == "ctrip":
        return CTRIP_BATCH_PAGE_URL
    if platform_key == "fliggy":
        return FLIGGY_ROOMS_MANAGE_URL
    if platform_key == "meituan":
        return MEITUAN_BATCH_PAGE_URL

    host = str(request_host or "").strip() or "127.0.0.1:5000"
    return f"http://{host}/dashboard"


def list_bootstrap_browser_targets() -> list[dict[str, Any]]:
    list_url = f"{get_bootstrap_cdp_base_url()}/json/list"
    with urllib_request.urlopen(list_url, timeout=1.8) as response:
        payload = response.read().decode("utf-8", errors="ignore")
    loaded = json.loads(payload)
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    return []


def focus_bootstrap_target_by_id(target_id: str) -> bool:
    target = str(target_id or "").strip()
    if not target:
        return False

    encoded = urllib_parse.quote(target, safe="")
    activate_url = f"{get_bootstrap_cdp_base_url()}/json/activate/{encoded}"
    try:
        with urllib_request.urlopen(activate_url, timeout=1.8):
            return True
    except Exception:
        return False


def close_bootstrap_target_by_id(target_id: str) -> bool:
    target = str(target_id or "").strip()
    if not target:
        return False

    encoded = urllib_parse.quote(target, safe="")
    close_url = f"{get_bootstrap_cdp_base_url()}/json/close/{encoded}"
    try:
        with urllib_request.urlopen(close_url, timeout=1.8):
            return True
    except Exception:
        return False


def open_bootstrap_new_tab(target_url: str) -> str:
    open_url = str(target_url or "").strip()
    if not open_url:
        return ""

    encoded_url = urllib_parse.quote(open_url, safe=":/?&=#%")
    new_url = f"{get_bootstrap_cdp_base_url()}/json/new?{encoded_url}"

    for method in ("PUT", "GET"):
        try:
            req = urllib_request.Request(new_url, method=method)
            with urllib_request.urlopen(req, timeout=2.2) as response:
                payload = response.read().decode("utf-8", errors="ignore")
            loaded = json.loads(payload)
            if isinstance(loaded, dict):
                return str(loaded.get("id") or loaded.get("targetId") or "").strip()
        except Exception:
            continue

    return ""


def platform_target_keywords(platform_key: str, request_host: str) -> tuple[str, ...]:
    host_key = str(request_host or "").strip().lower()
    if not host_key:
        host_key = "127.0.0.1:5000"

    if platform_key == "ctrip":
        return ("ebooking.trip.com",)
    if platform_key == "fliggy":
        return ("hotel.fliggy.com",)
    if platform_key == "meituan":
        return ("me.meituan.com",)
    return (f"{host_key}/dashboard", "localhost:5000/dashboard", "127.0.0.1:5000/dashboard")


def open_bootstrap_new_tab_near_opener(
    target_url: str,
    *,
    opener_platform_key: str,
    request_host: str,
) -> bool:
    open_url = str(target_url or "").strip()
    opener_key = normalize_focus_platform(opener_platform_key)
    opener_keywords = platform_target_keywords(opener_key, request_host)
    if not open_url or not opener_keywords:
        return False

    try:
        targets = list_bootstrap_browser_targets()
        opener_id = match_target_id_for_platform(targets, opener_key, request_host)
        if opener_id:
            focus_bootstrap_target_by_id(opener_id)
            time.sleep(0.12)

        opened_id = open_bootstrap_new_tab(open_url)
        if not opened_id:
            return False

        focus_bootstrap_target_by_id(opened_id)
        time.sleep(0.12)
        return True
    except Exception:
        return False


def match_target_id_for_platform(
    targets: list[dict[str, Any]],
    platform_key: str,
    request_host: str,
) -> str:
    keywords = platform_target_keywords(platform_key, request_host)

    for item in targets:
        url = str(item.get("url") or "").lower()
        if not url:
            continue
        if any(keyword in url for keyword in keywords):
            return str(item.get("id") or item.get("targetId") or "").strip()

    return ""


def wait_for_bootstrap_platform_target(
    platform_key: str,
    request_host: str,
    *,
    timeout_seconds: float = 1.8,
    poll_interval_seconds: float = 0.16,
) -> tuple[str, list[dict[str, Any]]]:
    deadline = time.time() + max(0.1, float(timeout_seconds))
    interval = max(0.05, float(poll_interval_seconds))
    last_targets: list[dict[str, Any]] = []

    while time.time() < deadline:
        try:
            targets = list_bootstrap_browser_targets()
        except Exception:
            targets = []

        if targets:
            last_targets = list(targets)
            matched = match_target_id_for_platform(targets, platform_key, request_host)
            if matched:
                return matched, last_targets

        time.sleep(interval)

    return "", last_targets


def ensure_bootstrap_platform_tabs(
    platform_keys: list[str],
    request_host: str,
) -> dict[str, list[str]]:
    order = ["dashboard", "ctrip", "fliggy", "meituan"]
    order_index = {key: idx for idx, key in enumerate(order)}

    normalized_keys = [
        key for key in normalize_focus_platforms(platform_keys)
        if key in order_index
    ]
    if not normalized_keys:
        return {"opened": [], "existing": [], "failed": []}

    normalized_keys.sort(key=lambda key: order_index.get(key, 99))

    targets = list_bootstrap_browser_targets()

    opened: list[str] = []
    existing: list[str] = []
    failed: list[str] = []

    def current_target_id(platform_key: str) -> str:
        return match_target_id_for_platform(targets, platform_key, request_host)

    for platform_key in normalized_keys:
        target_id = current_target_id(platform_key)
        if target_id:
            existing.append(platform_key)
            continue

        current_idx = order_index.get(platform_key, -1)
        opener_key = ""

        # Prefer dashboard as opener to keep recoveries in the same browser window
        # and avoid visibly jumping to other platform tabs during retries.
        dashboard_id = current_target_id("dashboard")
        if dashboard_id:
            opener_key = "dashboard"
        elif current_idx > 0:
            for idx in range(current_idx - 1, -1, -1):
                prev_key = order[idx]
                prev_id = current_target_id(prev_key)
                if not prev_id:
                    continue
                opener_key = prev_key
                break

        target_url = resolve_focus_target_url(platform_key, request_host)
        opened_id = ""
        if opener_key:
            opened_near = open_bootstrap_new_tab_near_opener(
                target_url,
                opener_platform_key=opener_key,
                request_host=request_host,
            )
            if opened_near:
                awaited_id, awaited_targets = wait_for_bootstrap_platform_target(
                    platform_key,
                    request_host,
                    timeout_seconds=2.6,
                    poll_interval_seconds=0.14,
                )
                if awaited_targets:
                    targets = list(awaited_targets)
                opened_id = awaited_id

        if not opened_id:
            awaited_id, awaited_targets = wait_for_bootstrap_platform_target(
                platform_key,
                request_host,
                timeout_seconds=0.9,
                poll_interval_seconds=0.12,
            )
            if awaited_targets:
                targets = list(awaited_targets)
            opened_id = awaited_id

        if not opened_id:
            opened_id = open_bootstrap_new_tab(target_url)

        if not opened_id:
            awaited_id, awaited_targets = wait_for_bootstrap_platform_target(
                platform_key,
                request_host,
                timeout_seconds=2.2,
                poll_interval_seconds=0.14,
            )
            if awaited_targets:
                targets = list(awaited_targets)
            opened_id = awaited_id

        if opened_id:
            opened.append(platform_key)
            targets.append({"id": opened_id, "url": target_url})
        else:
            failed.append(platform_key)

    return {
        "opened": opened,
        "existing": existing,
        "failed": failed,
    }


def is_bootstrap_browser_reachable() -> bool:
    version_url = get_bootstrap_cdp_version_url()
    try:
        with urllib_request.urlopen(version_url, timeout=1.5) as response:
            return int(getattr(response, "status", 200)) < 500
    except (urllib_error.URLError, TimeoutError, ValueError):
        return False


@app.post("/api/bootstrap/focus-platform-tab")
def api_bootstrap_focus_platform_tab() -> Any:
    payload = request.get_json(silent=True) or {}
    platform_key = normalize_focus_platform(payload.get("platform"))
    if not platform_key:
        return jsonify({"ok": False, "message": "平台参数无效"}), 400

    open_if_missing = bool(payload.get("openIfMissing", True))
    if not is_bootstrap_browser_reachable():
        return jsonify({"ok": False, "message": "未检测到可复用浏览器，请先点击跳转打开平台标签"}), 400

    request_host = str(request.host or "").strip()

    with BOOTSTRAP_TAB_FOCUS_LOCK:
        try:
            targets = list_bootstrap_browser_targets()
        except Exception as exc:
            return jsonify({"ok": False, "message": f"读取浏览器标签失败: {exc}"}), 500

        target_id = match_target_id_for_platform(targets, platform_key, request_host)
        if target_id and focus_bootstrap_target_by_id(target_id):
            return jsonify({"ok": True, "message": "已切换到对应平台标签"})

        if not open_if_missing:
            return jsonify({"ok": False, "message": "未找到对应平台标签，请先打开平台标签页"}), 404

        try:
            ensured = ensure_bootstrap_platform_tabs([platform_key], request_host)
        except Exception as exc:
            return jsonify({"ok": False, "message": f"补齐平台标签失败: {exc}"}), 500

        if ensured.get("failed"):
            return jsonify({"ok": False, "message": "切换失败，请点击跳转重新打开平台标签"}), 500

        refreshed_id, _ = wait_for_bootstrap_platform_target(
            platform_key,
            request_host,
            timeout_seconds=2.8,
            poll_interval_seconds=0.14,
        )
        if refreshed_id and focus_bootstrap_target_by_id(refreshed_id):
            if ensured.get("opened"):
                return jsonify({"ok": True, "message": "未找到旧标签，已补回并切换到平台标签"})
            return jsonify({"ok": True, "message": "已切换到对应平台标签"})

    return jsonify({"ok": False, "message": "切换失败，请点击跳转重新打开平台标签"}), 500


def stop_bootstrap_login_process() -> None:
    global BOOTSTRAP_LOGIN_PROCESS

    process = BOOTSTRAP_LOGIN_PROCESS
    if process is None:
        return

    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=2)
            except Exception:
                pass
        except Exception:
            pass

    BOOTSTRAP_LOGIN_PROCESS = None


@app.get("/api/bootstrap/login-tabs-status")
def api_bootstrap_login_tabs_status() -> Any:
    global BOOTSTRAP_LOGIN_PROCESS

    process_running = bool(BOOTSTRAP_LOGIN_PROCESS is not None and BOOTSTRAP_LOGIN_PROCESS.poll() is None)
    browser_reachable = is_bootstrap_browser_reachable()
    running = bool(process_running or browser_reachable)
    return jsonify(
        {
            "ok": True,
            "running": running,
            "browserReachable": browser_reachable,
        }
    )


@app.post("/api/bootstrap/open-login-tabs")
def api_bootstrap_open_login_tabs() -> Any:
    global BOOTSTRAP_LOGIN_PROCESS

    payload = request.get_json(silent=True) or {}
    force_restart = bool(payload.get("forceRestart", False))
    selected_platforms = normalize_bootstrap_platforms(payload.get("platforms", []))
    includes_ctrip = "ctrip" in selected_platforms
    browser_reachable = bool(includes_ctrip and is_bootstrap_browser_reachable())

    if not force_restart and browser_reachable:
        request_host = str(request.host or "").strip()
        try:
            ensured = ensure_bootstrap_platform_tabs(selected_platforms, request_host)
        except Exception as exc:
            return jsonify({"ok": False, "message": f"补齐平台标签失败: {exc}"}), 500

        opened = ensured.get("opened", [])
        failed = ensured.get("failed", [])
        if failed:
            return jsonify(
                {
                    "ok": False,
                    "message": "部分平台标签补齐失败，请点击重新打开平台标签。",
                }
            ), 500

        if opened:
            opened_text = "、".join(opened)
            return jsonify(
                {
                    "ok": True,
                    "alreadyRunning": True,
                    "message": f"检测到缺失标签，已自动补回：{opened_text}",
                }
            )

        return jsonify(
            {
                "ok": True,
                "alreadyRunning": True,
                "message": "检测到已打开的平台浏览器，已复用现有标签页。",
            }
        )

    if BOOTSTRAP_LOGIN_PROCESS is not None and BOOTSTRAP_LOGIN_PROCESS.poll() is None:
        if force_restart or (includes_ctrip and not is_bootstrap_browser_reachable()):
            stop_bootstrap_login_process()
        elif not includes_ctrip:
            platform_arg = "all"
            if len(selected_platforms) == 1:
                platform_arg = selected_platforms[0]

            command = [
                sys.executable,
                str(BASE_DIR / "login_manager.py"),
                "--platform",
                platform_arg,
                "--bootstrap-open-only",
            ]
            try:
                subprocess.Popen(command, cwd=str(BASE_DIR))
            except Exception as exc:
                return jsonify({"ok": False, "message": f"启动登录浏览器失败: {exc}"}), 500

            return jsonify(
                {
                    "ok": True,
                    "message": "已按携程、飞猪、美团顺序重新打开平台标签页（单浏览器多标签），请在浏览器完成登录并保持窗口开启。",
                }
            )
        else:
            return jsonify(
                {
                    "ok": True,
                    "alreadyRunning": True,
                    "message": "登录浏览器已在运行，请直接在浏览器完成登录并保持窗口开启。",
                }
            )

    if BOOTSTRAP_LOGIN_PROCESS is not None and BOOTSTRAP_LOGIN_PROCESS.poll() is not None:
        BOOTSTRAP_LOGIN_PROCESS = None

    platform_arg = "all"
    if len(selected_platforms) == 1:
        platform_arg = selected_platforms[0]

    command = [
        sys.executable,
        str(BASE_DIR / "login_manager.py"),
        "--platform",
        platform_arg,
        "--bootstrap-open-only",
    ]

    try:
        process = subprocess.Popen(command, cwd=str(BASE_DIR))
        if includes_ctrip:
            BOOTSTRAP_LOGIN_PROCESS = process
    except Exception as exc:
        return jsonify({"ok": False, "message": f"启动登录浏览器失败: {exc}"}), 500

    return jsonify(
        {
            "ok": True,
            "message": "已按携程、飞猪、美团顺序一次打开平台标签页（单浏览器多标签），请在浏览器完成登录并保持窗口开启。",
        }
    )


@app.get("/api/meta")
def api_meta() -> Any:
    store = load_store()
    data_health_alert = get_data_health_alert()
    backup_info = normalize_backup_info(store.get("backupInfo"))
    return jsonify(
        {
            "ok": True,
            "platforms": PLATFORMS,
            "statuses": MODES,
            "localOnlyRoomTypes": sorted(LOCAL_ONLY_ROOM_TYPES),
            "roomTypes": [
                {"name": name, "total": total}
                for name, total in store["roomConfig"].items()
            ],
            "backupInfo": {
                "lastExportDate": str(backup_info.get("lastExportDate") or ""),
                "lastExportAt": str(backup_info.get("lastExportAt") or ""),
                "lastAutoBackupAt": str(backup_info.get("lastAutoBackupAt") or ""),
                "autoBackupIntervalHours": float(backup_info.get("autoBackupIntervalHours") or 0),
            },
            "dataHealthAlert": data_health_alert,
        }
    )


@app.get("/api/calendar")
def api_calendar() -> Any:
    base_date_raw = request.args.get("date", "").strip()
    if not base_date_raw:
        return jsonify({"ok": False, "message": "缺少 date 参数"}), 400

    try:
        base_date = date.fromisoformat(base_date_raw)
    except ValueError:
        return jsonify({"ok": False, "message": "date 格式必须是 YYYY-MM-DD"}), 400

    window_days_raw = request.args.get("days", "14").strip()
    try:
        window_days = max(1, min(31, int(window_days_raw)))
    except ValueError:
        window_days = 14

    store = load_store()
    payload = build_calendar_payload(store, base_date=base_date, window_days=window_days)

    return jsonify(
        {
            "ok": True,
            "baseDate": base_date.isoformat(),
            **payload,
        }
    )


@app.get("/api/inventory")
def api_inventory() -> Any:
    target_date = request.args.get("date", "").strip()
    if not target_date:
        return jsonify({"ok": False, "message": "缺少 date 参数"}), 400

    try:
        date.fromisoformat(target_date)
    except ValueError:
        return jsonify({"ok": False, "message": "date 格式必须是 YYYY-MM-DD"}), 400

    store = load_store()
    rows = build_inventory_rows(store, target_date)
    return jsonify({"ok": True, "date": target_date, "rows": rows})


@app.get("/api/history")
def api_history() -> Any:
    limit_raw = request.args.get("limit", "50")
    try:
        limit = max(1, min(200, int(limit_raw)))
    except ValueError:
        limit = 50

    store = load_store()
    return jsonify({"ok": True, "items": store["history"][:limit]})


@app.get("/api/sync-queue")
def api_sync_queue() -> Any:
    limit_raw = request.args.get("limit", "50")
    try:
        limit = max(1, min(500, int(limit_raw)))
    except ValueError:
        limit = 50

    store = load_store()
    return jsonify({"ok": True, "items": store["syncQueue"][:limit]})


@app.post("/api/sync/run-ctrip")
def api_sync_run_ctrip() -> Any:
    payload = request.get_json(silent=True) or {}

    limit_raw = payload.get("limit", request.args.get("limit", 20))
    try:
        limit = max(1, min(200, int(limit_raw)))
    except (TypeError, ValueError):
        limit = 20

    headless = bool(payload.get("headless", False))

    try:
        store = load_store()
        report = run_ctrip_sync_queue(store, limit=limit, headless=headless)
        save_store(store)
        return jsonify({"ok": True, **report})
    except ImportError as exc:
        return jsonify({"ok": False, "message": f"缺少依赖，请先安装 Playwright: {exc}"}), 500
    except Exception as exc:
        return jsonify({"ok": False, "message": f"执行携程同步失败：{exc}"}), 500


@app.get("/api/sync/progress/<job_id>")
def api_sync_progress(job_id: str) -> Any:
    snapshot = get_async_sync_job_snapshot(job_id)
    if snapshot is None:
        return jsonify({"ok": False, "message": "同步进度任务不存在或已过期"}), 404

    return jsonify(
        {
            "ok": True,
            "jobId": str(snapshot.get("id") or ""),
            "completed": bool(snapshot.get("completed", False)),
            "message": str(snapshot.get("message") or ""),
            "syncReport": snapshot.get("syncReport", {}),
        }
    )


@app.post("/api/sync/retry")
def api_sync_retry() -> Any:
    payload = request.get_json(silent=True) or {}
    source_platform = str(payload.get("sourcePlatform") or "").strip()
    retry_mode = str(payload.get("retryMode") or "auto").strip().lower()
    if retry_mode not in {"auto", "manual_fallback"}:
        retry_mode = "auto"
    force_manual_fallback = retry_mode == "manual_fallback"

    raw_map = payload.get("platformTaskIds", {})
    if not isinstance(raw_map, dict):
        raw_map = {}

    requested_ids_by_platform: dict[str, set[str]] = {platform: set() for platform in SYNC_TARGET_PLATFORMS}
    for platform in SYNC_TARGET_PLATFORMS:
        raw_ids = raw_map.get(platform, [])
        if not isinstance(raw_ids, list):
            continue
        requested_ids_by_platform[platform] = {
            str(item).strip()
            for item in raw_ids
            if str(item).strip()
        }

    requested_total = sum(len(item) for item in requested_ids_by_platform.values())
    if requested_total <= 0:
        return jsonify({"ok": False, "message": "没有可重试的任务，请先刷新后重试"}), 400

    store = load_store()

    retry_ids_by_platform: dict[str, set[str]] = {platform: set() for platform in SYNC_TARGET_PLATFORMS}
    requested_existing_ids_by_platform: dict[str, set[str]] = {platform: set() for platform in SYNC_TARGET_PLATFORMS}
    requested_success_ids_by_platform: dict[str, set[str]] = {platform: set() for platform in SYNC_TARGET_PLATFORMS}
    for item in store["syncQueue"]:
        if not isinstance(item, dict):
            continue

        platform = str(item.get("targetPlatform") or "").strip()
        if platform not in SYNC_TARGET_PLATFORMS:
            continue

        task_id = str(item.get("id") or "").strip()
        if not task_id:
            continue

        requested_ids = requested_ids_by_platform.get(platform, set())
        if requested_ids and task_id not in requested_ids:
            continue
        if not requested_ids:
            continue

        requested_existing_ids_by_platform[platform].add(task_id)

        status = str(item.get("status") or "").strip().lower()
        error_message = str(item.get("errorMessage") or "").strip()
        if status == "success":
            requested_success_ids_by_platform[platform].add(task_id)
            continue

        is_retryable = (
            status == "failed"
            or status == "manual"
            or (status == "pending" and "超时" in error_message)
        )
        if not is_retryable:
            continue

        item["retryCount"] = to_int(item.get("retryCount", 0), 0) + 1
        item["retryAt"] = now_iso()
        item["status"] = "pending"
        item["errorMessage"] = ""
        retry_ids_by_platform[platform].add(task_id)

    matched_total = sum(len(item) for item in retry_ids_by_platform.values())
    if matched_total <= 0:
        existing_total = sum(len(item) for item in requested_existing_ids_by_platform.values())
        success_total = sum(len(item) for item in requested_success_ids_by_platform.values())
        if existing_total > 0 and existing_total == success_total:
            platform_reports: list[dict[str, Any]] = []
            total_success = 0
            for platform in SYNC_TARGET_PLATFORMS:
                success_ids = sorted(requested_success_ids_by_platform.get(platform, set()))
                success_count = len(success_ids)
                total_success += success_count

                if success_count > 0:
                    platform_reports.append(
                        {
                            "platform": platform,
                            "status": "success",
                            "message": f"已提交平台修改 {success_count} 条（无需重试）",
                            "taskIds": success_ids,
                            "targetTaskCount": success_count,
                            "processed": success_count,
                            "success": success_count,
                            "failed": 0,
                            "items": [
                                {
                                    "id": task_id,
                                    "ok": True,
                                    "message": "已同步，无需重试",
                                }
                                for task_id in success_ids
                            ],
                        }
                    )
                elif platform == source_platform:
                    platform_reports.append(
                        {
                            "platform": platform,
                            "status": "skipped",
                            "message": "无需更新（当前下单平台）",
                            "taskIds": [],
                            "targetTaskCount": 0,
                            "processed": 0,
                            "success": 0,
                            "failed": 0,
                            "items": [],
                        }
                    )
                else:
                    platform_reports.append(
                        {
                            "platform": platform,
                            "status": "noop",
                            "message": "无需更新",
                            "taskIds": [],
                            "targetTaskCount": 0,
                            "processed": 0,
                            "success": 0,
                            "failed": 0,
                            "items": [],
                        }
                    )

            report = {
                "enabled": True,
                "sourcePlatform": source_platform,
                "targetTaskCount": total_success,
                "processed": total_success,
                "success": total_success,
                "failed": 0,
                "platformReports": platform_reports,
            }
            save_store(store)
            return jsonify({"ok": True, "syncReport": report})

        return jsonify({"ok": False, "message": "未找到可重试任务，可能已成功或状态已变化，请刷新后重试"}), 400

    report = auto_sync_platforms_after_change(
        store,
        source_platform=source_platform,
        task_ids_by_platform=retry_ids_by_platform,
        force_manual_fallback=force_manual_fallback,
    )
    save_store(store)
    return jsonify({"ok": True, "syncReport": report})


@app.get("/api/cancel-options")
def api_cancel_options() -> Any:
    room_type = request.args.get("roomType", "").strip()
    platform = request.args.get("platform", "").strip()

    payload = {
        "checkInDate": request.args.get("checkInDate", "").strip(),
        "checkOutDate": request.args.get("checkOutDate", "").strip(),
    }

    try:
        _, _, days = parse_stay_range(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    store = load_store()
    if room_type not in store["roomConfig"]:
        return jsonify({"ok": False, "message": "房型不在配置列表中"}), 400
    if platform not in PLATFORMS:
        return jsonify({"ok": False, "message": "平台不在配置列表中"}), 400

    options = list_cancel_options(store, room_type=room_type, platform=platform, selected_days=days)
    return jsonify({"ok": True, "items": options})


@app.get("/api/available-rooms")
def api_available_rooms() -> Any:
    room_type = request.args.get("roomType", "").strip()
    exclude_booking_id = request.args.get("excludeBookingId", "").strip()
    payload = {
        "checkInDate": request.args.get("checkInDate", "").strip(),
        "checkOutDate": request.args.get("checkOutDate", "").strip(),
    }

    try:
        _, _, days = parse_stay_range(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    store = load_store()
    if room_type not in store["roomConfig"]:
        return jsonify({"ok": False, "message": "房型不在配置列表中"}), 400

    rooms = list_available_rooms(
        store,
        room_type=room_type,
        days=days,
        exclude_booking_id=exclude_booking_id,
    )
    return jsonify({"ok": True, "items": rooms})


@app.get("/api/modify-options")
def api_modify_options() -> Any:
    room_type = request.args.get("roomType", "").strip()
    platform = request.args.get("platform", "").strip()

    store = load_store()
    if room_type not in store["roomConfig"]:
        return jsonify({"ok": False, "message": "房型不在配置列表中"}), 400
    if platform not in PLATFORMS:
        return jsonify({"ok": False, "message": "平台不在配置列表中"}), 400

    options = list_modify_options(store, room_type=room_type, platform=platform)
    return jsonify({"ok": True, "items": options})


@app.get("/api/day-bookings")
def api_day_bookings() -> Any:
    room_type = request.args.get("roomType", "").strip()
    target_date_raw = request.args.get("date", "").strip()
    stage = request.args.get("stage", "").strip()
    platform = request.args.get("platform", "").strip()

    if not room_type:
        return jsonify({"ok": False, "message": "缺少 roomType 参数"}), 400
    if not target_date_raw:
        return jsonify({"ok": False, "message": "缺少 date 参数"}), 400

    try:
        target_date = date.fromisoformat(target_date_raw).isoformat()
    except ValueError:
        return jsonify({"ok": False, "message": "date 格式必须是 YYYY-MM-DD"}), 400

    if stage and stage not in {"新", "续"}:
        return jsonify({"ok": False, "message": "stage 仅支持 新 或 续"}), 400

    store = load_store()
    if room_type not in store["roomConfig"]:
        return jsonify({"ok": False, "message": "房型不在配置列表中"}), 400

    if platform and platform not in PLATFORMS:
        return jsonify({"ok": False, "message": "平台不在配置列表中"}), 400

    items = list_day_booking_details(
        store,
        room_type=room_type,
        target_date=target_date,
        stage=stage,
        platform=platform,
    )
    return jsonify({"ok": True, "items": items})


@app.get("/api/backup/export")
def api_backup_export() -> Any:
    days_raw = request.args.get("days", "30").strip()
    try:
        days = max(1, min(90, int(days_raw)))
    except ValueError:
        days = 30

    end = date.today()
    start = end - timedelta(days=days - 1)

    store = load_store()
    backup = build_backup_payload(store, start=start, end=end)
    backup_info = normalize_backup_info(store.get("backupInfo"))
    backup_info["lastExportDate"] = retention_reference_today().isoformat()
    backup_info["lastExportAt"] = now_iso()
    store["backupInfo"] = backup_info
    save_store(store)

    return jsonify(
        {
            "ok": True,
            "backup": backup,
            "lastExportDate": backup_info["lastExportDate"],
        }
    )


@app.post("/api/backup/import")
def api_backup_import() -> Any:
    payload = request.get_json(silent=True) or {}
    backup_payload = payload.get("backup", payload)

    try:
        store = load_store()
        merged_store, stats = merge_backup_into_store(store, backup_payload)
        ensure_room_config_within_capacity(merged_store)
        save_store(merged_store)
        return jsonify({"ok": True, "stats": stats})
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400


@app.get("/api/room-management")
def api_room_management() -> Any:
    try:
        target_date = parse_target_date(request.args.get("date", ""))
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    store = load_store()
    payload = build_room_management_payload(store, target_date)
    return jsonify({"ok": True, **payload})


@app.post("/api/floors")
def api_create_floor() -> Any:
    payload = request.get_json(silent=True) or {}
    floor_name = str(payload.get("name") or "").strip()
    is_open = bool(payload.get("isOpen", False))
    if not floor_name:
        return jsonify({"ok": False, "message": "楼层名称不能为空"}), 400

    store = load_store()
    floor = {
        "id": str(uuid4()),
        "name": floor_name,
        "isOpen": is_open,
    }
    store["floors"].append(floor)
    save_store(store)
    return jsonify({"ok": True, "floor": floor})


@app.patch("/api/floors/<floor_id>")
def api_update_floor(floor_id: str) -> Any:
    payload = request.get_json(silent=True) or {}
    target_id = str(floor_id).strip()
    if not target_id:
        return jsonify({"ok": False, "message": "缺少楼层ID"}), 400

    store = load_store()
    floor = get_floor_by_id(store, target_id)
    if floor is None:
        return jsonify({"ok": False, "message": "楼层不存在"}), 404

    if "name" in payload:
        next_name = str(payload.get("name") or "").strip()
        if not next_name:
            return jsonify({"ok": False, "message": "楼层名称不能为空"}), 400
        floor["name"] = next_name

    if "isOpen" in payload:
        next_open = bool(payload.get("isOpen"))
        temp_floors = [dict(item) for item in store["floors"]]
        for temp_floor in temp_floors:
            if str(temp_floor.get("id") or "").strip() == target_id:
                temp_floor["isOpen"] = next_open
                break

        try:
            ensure_room_config_within_capacity(store, floors=temp_floors, rooms=store["rooms"])
        except ValueError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

        floor["isOpen"] = next_open

    save_store(store)
    return jsonify({"ok": True, "floor": floor})


@app.delete("/api/floors/<floor_id>")
def api_delete_floor(floor_id: str) -> Any:
    target_id = str(floor_id).strip()
    if not target_id:
        return jsonify({"ok": False, "message": "缺少楼层ID"}), 400

    store = load_store()
    floor = get_floor_by_id(store, target_id)
    if floor is None:
        return jsonify({"ok": False, "message": "楼层不存在"}), 404

    target_room_ids = {
        str(room.get("id") or "").strip()
        for room in store["rooms"]
        if str(room.get("floorId") or "").strip() == target_id
    }

    for room_id in target_room_ids:
        if room_id and room_has_active_booking(store, room_id):
            return jsonify({"ok": False, "message": "该楼层存在在住/未离店房间，无法删除"}), 400

    store["floors"] = [
        item for item in store["floors"] if str(item.get("id") or "").strip() != target_id
    ]
    store["rooms"] = [
        room for room in store["rooms"]
        if str(room.get("floorId") or "").strip() != target_id
    ]

    if not store["floors"]:
        default_floors, _ = build_default_hotel_structure(store["roomConfig"])
        store["floors"] = default_floors

    try:
        ensure_room_config_within_capacity(store)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    save_store(store)
    return jsonify({"ok": True, "deletedRoomCount": len(target_room_ids)})


@app.post("/api/rooms")
def api_create_room() -> Any:
    payload = request.get_json(silent=True) or {}
    floor_id = str(payload.get("floorId") or "").strip()
    room_number = str(payload.get("number") or "").strip()
    room_type = str(payload.get("roomType") or "").strip()

    store = load_store()
    if get_floor_by_id(store, floor_id) is None:
        return jsonify({"ok": False, "message": "楼层不存在"}), 400
    if not room_number:
        return jsonify({"ok": False, "message": "房号不能为空"}), 400
    if is_room_number_taken(store, room_number):
        return jsonify({"ok": False, "message": "房号已存在"}), 400
    if room_type not in store["roomConfig"]:
        return jsonify({"ok": False, "message": "房型不在配置列表中"}), 400

    room = {
        "id": str(uuid4()),
        "floorId": floor_id,
        "number": room_number,
        "roomType": room_type,
        "manualStatus": "空闲",
    }
    store["rooms"].append(room)
    save_store(store)

    floor_name_map = get_floor_name_map(store)
    return jsonify(
        {
            "ok": True,
            "room": {
                **room,
                "floorName": floor_name_map.get(floor_id, "未分层"),
            },
        }
    )


@app.patch("/api/rooms/<room_id>")
def api_update_room(room_id: str) -> Any:
    payload = request.get_json(silent=True) or {}
    target_id = str(room_id).strip()
    if not target_id:
        return jsonify({"ok": False, "message": "缺少房间ID"}), 400

    store = load_store()
    room = get_room_by_id(store, target_id)
    if room is None:
        return jsonify({"ok": False, "message": "房间不存在"}), 404

    next_floor_id = str(payload.get("floorId") or room.get("floorId") or "").strip()
    next_room_number = str(payload.get("number") or room.get("number") or "").strip()
    next_room_type = str(payload.get("roomType") or room.get("roomType") or "").strip()
    next_manual_status = str(payload.get("manualStatus") or room.get("manualStatus") or "空闲").strip()

    if get_floor_by_id(store, next_floor_id) is None:
        return jsonify({"ok": False, "message": "楼层不存在"}), 400
    if not next_room_number:
        return jsonify({"ok": False, "message": "房号不能为空"}), 400
    if is_room_number_taken(store, next_room_number, exclude_room_id=target_id):
        return jsonify({"ok": False, "message": "房号已存在"}), 400
    if next_room_type not in store["roomConfig"]:
        return jsonify({"ok": False, "message": "房型不在配置列表中"}), 400
    if next_manual_status not in {"空闲", "维修"}:
        return jsonify({"ok": False, "message": "房间状态仅支持 空闲 或 维修"}), 400

    current_room_type = str(room.get("roomType") or "").strip()
    if next_room_type != current_room_type and room_has_active_booking(store, target_id):
        return jsonify({"ok": False, "message": "该房间存在在住/未离店订单，暂不能修改房型"}), 400

    if next_manual_status == "维修" and room_has_active_booking(store, target_id):
        return jsonify({"ok": False, "message": "该房间存在在住/未离店订单，暂不能设为维修"}), 400

    temp_rooms = [dict(item) for item in store["rooms"]]
    for temp_room in temp_rooms:
        if str(temp_room.get("id") or "").strip() != target_id:
            continue
        temp_room["floorId"] = next_floor_id
        temp_room["number"] = next_room_number
        temp_room["roomType"] = next_room_type
        temp_room["manualStatus"] = next_manual_status
        break

    try:
        ensure_room_config_within_capacity(store, floors=store["floors"], rooms=temp_rooms)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    room["floorId"] = next_floor_id
    room["number"] = next_room_number
    room["roomType"] = next_room_type
    room["manualStatus"] = next_manual_status
    save_store(store)

    floor_name_map = get_floor_name_map(store)
    return jsonify(
        {
            "ok": True,
            "room": {
                **room,
                "floorName": floor_name_map.get(next_floor_id, "未分层"),
            },
        }
    )


@app.delete("/api/rooms/<room_id>")
def api_delete_room(room_id: str) -> Any:
    target_id = str(room_id).strip()
    if not target_id:
        return jsonify({"ok": False, "message": "缺少房间ID"}), 400

    store = load_store()
    room = get_room_by_id(store, target_id)
    if room is None:
        return jsonify({"ok": False, "message": "房间不存在"}), 404

    if room_has_active_booking(store, target_id):
        return jsonify({"ok": False, "message": "该房间存在在住/未离店订单，无法删除"}), 400

    store["rooms"] = [
        item for item in store["rooms"]
        if str(item.get("id") or "").strip() != target_id
    ]

    try:
        ensure_room_config_within_capacity(store)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    save_store(store)
    return jsonify({"ok": True})


@app.post("/api/init-local")
def api_init_local() -> Any:
    payload = request.get_json(silent=True) or {}

    try:
        store = load_store()
        before_pending_ids = {
            platform: list_pending_sync_task_ids(store, target_platform=platform)
            for platform in SYNC_TARGET_PLATFORMS
        }
        validated = validate_init_payload(payload, store)
        record = apply_local_initialization(store, validated)
        after_pending_ids = {
            platform: list_pending_sync_task_ids(store, target_platform=platform)
            for platform in SYNC_TARGET_PLATFORMS
        }
        new_ids_by_platform = {
            platform: after_pending_ids[platform] - before_pending_ids[platform]
            for platform in SYNC_TARGET_PLATFORMS
        }
        sync_report = auto_sync_platforms_after_change(
            store,
            source_platform="本地系统",
            task_ids_by_platform=new_ids_by_platform,
        )
        save_store(store)
        return jsonify({"ok": True, "record": record, "syncReport": sync_report})
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400


@app.post("/api/adjust")
def api_adjust() -> Any:
    payload = request.get_json(silent=True) or {}

    try:
        store = load_store()
        before_pending_ids = {
            platform: list_pending_sync_task_ids(store, target_platform=platform)
            for platform in SYNC_TARGET_PLATFORMS
        }
        validated = validate_adjust_payload(payload, store)
        record = apply_adjustment(store, validated)
        after_pending_ids = {
            platform: list_pending_sync_task_ids(store, target_platform=platform)
            for platform in SYNC_TARGET_PLATFORMS
        }
        new_ids_by_platform = {
            platform: after_pending_ids[platform] - before_pending_ids[platform]
            for platform in SYNC_TARGET_PLATFORMS
        }

        if is_bootstrap_browser_reachable():
            focus_candidates: list[str] = []
            if new_ids_by_platform.get("携程"):
                focus_candidates.append("ctrip")
            if new_ids_by_platform.get("飞猪"):
                focus_candidates.append("fliggy")
            if new_ids_by_platform.get("美团"):
                focus_candidates.append("meituan")

            if focus_candidates:
                try:
                    ensure_bootstrap_platform_tabs(focus_candidates, str(request.host or "").strip())
                except Exception:
                    pass

        source_platform = str(validated.get("platform", "")).strip()
        sync_report = auto_sync_platforms_after_change(
            store,
            source_platform=source_platform,
            task_ids_by_platform=new_ids_by_platform,
        )
        save_store(store)
        return jsonify({"ok": True, "record": record, "syncReport": sync_report})
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
