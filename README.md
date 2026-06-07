# Hotel Platform Login Helper

This project automates login for:

- Ctrip
- Fliggy
- Meituan

It uses Playwright persistent browser profiles, so your login state is saved in `sessions/` and reused next time.

## Why this stack

Python + Playwright is a good fit because it supports:

- Stable browser automation on Windows
- Persistent login sessions
- Manual captcha completion when required

## Quick start

### Downloadable Windows installer

For non-developers, publish the bundled Windows installer from GitHub Releases:

```text
山海宾馆房量同步台-带浏览器安装包.exe
```

This installer includes Chromium, installs the app under the current user's `LocalAppData`, creates desktop/start-menu shortcuts, and does not require Python or Playwright on the target PC. On first run, copy or edit `.env` in the installed app folder and fill your own platform credentials.

The installer is intended to be uploaded as a Release asset, not committed into the source repository.

### Developer setup

1. Create and activate a virtual env:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

3. Prepare credentials:

```powershell
copy .env.example .env
```

Fill values in `.env`.

If `.env` is not configured, the script will ask for username/password in terminal only when a platform really needs login.

4. Run login flow:

```powershell
python login_manager.py --platform all
```

Options:

- `--platform all|ctrip|fliggy|meituan`
- `--close-after-login` (default keeps browser windows open)

## Captcha and manual verification

If captcha/slider appears, complete it in the browser manually. Then return to terminal and press Enter to continue.

Fliggy currently uses a manual submit flow by design (to reduce anti-bot slider failures):

- Script fills account/password when possible.
- You manually click Next/Login and complete slider verification.

## Notes

- The script includes your provided XPath selectors as fallbacks.
- Fliggy login URL is `https://hotel.fliggy.com/ebooking/hotelBaseInfoUv.htm#/ebk/accountsmanage/manage`.
- Absolute XPaths can break when pages change. If a selector stops working, update it in `login_manager.py`.
- Persistent login data is stored under `sessions/`.

## Inventory management frontend

This project now includes a local management system page to adjust room balance and sync to other platforms by rules.

### Room type baseline

- 度假大床房: 3
- 家庭房: 4
- 豪华双床房: 1
- 度假双床房: 4

### Synchronization rule

- Date range now uses hotel stay semantics: check-in date + check-out date.
- Example: check-in 4.10 and check-out 4.12 means only nights 4.10 and 4.11 are affected (check-out day is excluded).
- Function 1: initialize room inventory. It sets local inventory and all platform inventory fields to the same value for the selected room type and stay range.
- During initialization, UI asks whether to sync platforms:
	- Confirm: create pending sync tasks for platforms.
	- Cancel: assume platform values were already changed manually.
- Function 2: adjust inventory by orders. You select source platform (携程/飞猪/美团/自接), stay range, room type, mode (预订/取消), and quantity.
- 预订 means minus quantity, 取消 means plus quantity.
- The system updates local inventory and applies the same delta to all other platforms (source platform is excluded).
- Platform operation is currently queued as pending sync tasks in local DB (real XPath automation can be plugged in later).
- Any invalid change (less than 0 or larger than total) is rejected entirely.

### Run web app

```powershell
pip install -r requirements.txt
python inventory_app.py
```

Open in browser:

```text
http://127.0.0.1:5000
```

### One-command startup (recommended)

For a packaged multi-platform management workflow, use one command to:

1. Login selected platforms.
2. Persist sessions to `sessions/`.
3. Start Flask management system.

```powershell
python run_system.py --login-platform all
```

Common options:

- `--login-platform all|none|ctrip|fliggy|meituan`
- `--disable-auto-ctrip-sync`
- `--auto-ctrip-sync-headless`
- `--auto-ctrip-sync-limit 20`

When auto Ctrip sync is enabled (default), each `/api/adjust` and `/api/init-local` request will try to execute pending Ctrip tasks immediately and write back result to `syncQueue`.

### Data persistence

- Inventory data and operation history are stored in `data/inventory_store.json`.
- Pending platform sync tasks are also stored in `data/inventory_store.json` under `syncQueue`.
- Home inventory overview uses a calendar-style board and keeps the date search filter as the calendar start date.
- Frontend files are in `templates/index.html`, `static/styles.css`, and `static/app.js`.

### Ctrip automatic sync (first integration)

The backend now supports executing pending Ctrip sync tasks from `syncQueue`.

1. Ensure Ctrip session is logged in first:

```powershell
python login_manager.py --platform ctrip
```

2. Run pending Ctrip sync tasks (default `limit=20`, uses non-headless browser):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/sync/run-ctrip" -ContentType "application/json" -Body '{"limit":20,"headless":false}'
```

Notes:

- Current version uses XPath automation on Ctrip page `batchSetRoomStatusAndQuantity`.
- It processes tasks where `targetPlatform=携程` and `status=pending`.
- On success, task status updates to `success`; failures are marked `failed` with `errorMessage`.

### Windows packaging (start here)

Build script is prepared for Windows desktop packaging with PyInstaller.

Default mode is Edge runtime (smaller package): no bundled browser files.

1. Build executable folder (Edge mode, recommended):

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

This default build creates a windowed exe (no black console window).
Built exe icon uses `static\favicon.ico`.

2. Output folder:

```text
dist\ShanhaiHotelSync
```

3. Start packaged app:

```powershell
.\dist\ShanhaiHotelSync\run_system.exe
```

After startup, the app shows a system tray icon. Right-click tray icon and choose `退出软件` to close app.

Edge mode behavior:

- App defaults to `LOGIN_BROWSER_CHANNEL=msedge`.
- It uses system Edge executable and app-owned user-data-dir under `sessions\`.

Optional offline mode (for PCs without Edge/Chrome):

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1 -BundleBrowser
```

In offline mode, package includes `ms-playwright\` and app auto-uses bundled Chromium.

Packaged folder always includes:

- `run_system.exe`
- `templates\` / `static\` / `data\`

Only offline mode additionally includes:

- `ms-playwright\` (bundled browser runtime)

Optional build flags:

- `-SkipInstall` skip dependency install step.
- `-NoClean` keep existing `build/` and `dist/` files.
- `-BundleBrowser` include Playwright Chromium binaries for no-browser target PCs.
- `-Console` build debug exe with console window.

### Build release installer

To produce a one-file installer for GitHub Releases:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\.venv-build\Scripts\python.exe -m playwright install chromium
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1 -SkipInstall -BundleBrowser
```

Then package `dist\ShanhaiHotelSync` into a release zip and build the installer with `installer\installer_app.py`. The generated installer should be distributed through GitHub Releases because it contains the bundled Chromium runtime and is too large for normal source commits.


# chromium打包（离线模式，包含浏览器文件，适用于没有Edge/Chrome的电脑）：
powershell -ExecutionPolicy Bypass -File build_windows.ps1 -BundleBrowser
