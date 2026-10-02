# KGS Staff app (`/staff`) — warehouse transfers

An installable phone app (PWA) for Stock Users: pick From/To warehouses, scan or search items, and
submit a **Material Transfer** (Stock Entry). Built 2026-10-02 on the pattern of the Betul exec PWA
(`zxrrcpandey/betul_biofuel`, app `trustbit_ethanol`, route `/exec`). Later phases planned in the same
app: Purchase Order approvals, then stock count → Stock Reconciliation.

**Status: LIVE on splashbox.in since 2026-10-02 19:28 IST** (`9cbcaa3`, scope fix `e7f7850` 19:31 IST).
Deployed in shop hours at the owner's request ("deploy now") — no migrate/build/flush; targeted dumps instead of a full
backup. Anchor `/root/predeploy_20261002_staff_app/` (HEAD before `f2bc2c3`, apps.txt, Scheduled Job Type + Stock Entry
Print Format dumps), log `/root/predeploy_20261002_staff_app.log`. Verified: all routes 200 over HTTPS, hooks
registered, job `touch_staff_sessions` (*/10) created, `kgs_staff_session_days` = 7, 0 new Error Log / 5xx.
**Not yet done:** a real phone sign-in + one real transfer with the owner (runbook step 9).

## Bulk transfers (LIVE 2026-10-02 20:11 IST, `8f9f04c` + `41f7438` — owner asked for all four kinds)
Deployed after hours (last bill 19:54): ff + app_hooks drop + HUP + website cache; workers need no restart (RQ forks a
fresh child per job). Anchor `/root/predeploy_20261002_staff_bulk/` (HEAD before `26904ad`). Read-only check on live
data as saransh42: RDPS 10 × 30 expanded in 0.12 s (8 lines, 8 left out with reasons), Stores - KGS all stock 36 lines.
"➕ Add in bulk" on the transfer screen loads many lines into the same draft (same item + unit adds onto the line):
| Kind | Endpoint | Notes |
|---|---|---|
| School set × N | `search_bundles`, `expand_bundle(bundle, sets, from, to)` | Product Bundle rows × qty × sets, in the row's unit; rows marked "Not Available" (`custom_product_bundle_stock`) are left out, as at the POS |
| Everything in From | `warehouse_contents(from, to)` | every bin with stock, at its full qty (van coming back; shop-floor cut-over) |
| Excel / CSV | `parse_sheet(filename, content(base64), from, to)` | A = barcode / ISBN / item code, B = qty, C = unit (optional); header row optional; ≤ 3 MB, ≤ 15,000 rows; numeric ISBN cells handled; unmatched rows come back with their row number |
Items that can never move (not found, disabled, no stock in From, ₹0 cost, unit not on item) are listed as "not added"
with the reason; a shortfall is NOT dropped — the line shows "Only X in …" in red so nothing silently goes missing.

**More than 150 lines** → `create_bulk_transfer`: **Stock Manager only, never in shop hours** (10:30–19:30 IST;
site_config `kgs_staff_bulk_in_shop_hours: 1` overrides). It validates the WHOLE list first (same rules, batched
queries), then queues `run_bulk_transfer` on the **long** queue (`job_id kgs_staff_bulk::<ref>`, deduplicated) which
submits consecutive transfers of ≤ 150 lines, each tagged `[Staff app · ref:<ref>#<part>/<parts>]` and committed one
by one. A re-run skips parts already made; it stops at the first part that can no longer move (stock changed since the
check) and says which part/item — parts already made stay. Progress page `/staff/bulk/<ref>` polls `bulk_status`
(status JSON in plain Redis `kgs_staff_bulk:<ref>`, 14 days; the transfer list itself comes from the DB, so a Redis
flush loses only the "running/stopped" text). Local timing: ~3–4 s per 150-line part on the Mac; expect ~10–20 s on
the 1-vCPU server, i.e. all of SBGD (~12,000 items ≈ 80 parts) ≈ 15–30 min, after hours.
⚠ Don't use frappe.cache.get_value/set_value(expires) for state read back in the same request/job — a miss is cached
in frappe.local and set_value with an expiry writes Redis only (bit us in the bulk tests).

## Short stock → Stock Reconciliation (LIVE 2026-10-03 01:21 IST, `bf21aee`)
Deployed after hours (no bills since 20:34, 0 reposts queued): ff, `sync_jobs` (weekly digest job added, nothing
deleted, 123 → 124), HUP, app_hooks + website cache. Anchor `/root/predeploy_20261003_staff_reco/` (HEAD before
`0b7eb66`). Verified read-only on live data: Stock User scan of a no-stock item refused, Stock Manager allowed;
preview figures correct; 0 errors. Weekly digest OFF (no recipients given yet).

**Owner decision 2026-10-03: NO value cap on app reconciliations** — accepted after being shown that a negative item
books its whole negative value as a gain (ITM-2025-28343 Project Paper: −24,333 PCS, −₹8,72,858.75 → reconciling it
to 10 PCS posts ≈ +₹8,72,863 to Stock Adjustment) and that some last purchase rates are junk (ITM-2025-13580: ₹0.01).
The review warning shows the total value change before Accept; that is the only guard. Do not add a cap without
asking the owner.
Owner asked (01:30 IST) for the warnings **in easy language** — review now says e.g. "⚠ Not enough stock in SBGD - KGS …
If you press Accept, the stock will be set to your count … Stock value will change by ₹… Accept only if the items are
really there", and an item in minus gets its own line: "⚠ System stock is in minus (−24,333). If you accept, stock
value will go up by about ₹…". Keep any new text at that level (short sentences, no ERP terms).
When a transfer asks for more than the system holds in From, a **Stock Manager** (only) can fix it at review instead
of being blocked (Stock Users still get the red "Only X in …" and must ask a manager):
- Managers can scan/add items with **no stock at all** in From (school sets and sheets keep them as short lines);
  zero-cost items stay refused for everyone. Short lines are amber, not red.
- Review shows a red warning with the total stock-value change, and one card per short item: system qty, what the
  transfer needs, **"Physically in <From> now"** (prefilled with the need), **rate for the extra** (prefilled: last
  purchase rate → else current valuation → else must be typed; never 0; warning if > 50% from the last purchase
  rate), **reason** (mandatory: Found extra stock / Count was wrong / Unit mistake / Purchase receipt not entered
  (allowed, with a double-count caution) / Other + note), and the value change. **Reject** / **Accept**.
- Count below the need → not blocked: that item's transfer is reduced to the count (one line in the stock unit);
  count not above the system qty → no reconciliation, transfer reduced to what the system has.
- Accept = one request, all or nothing (`create_transfer(..., recos=[{item_code, counted, rate, reason, note}])`):
  Stock Reconciliation(s) of ≤ 100 rows (ERPNext queues > 100), posted now, Stock Adjustment account, then the
  transfer. Row valuation rate is blended so existing units keep their value and only the extra gets the chosen
  rate; the reported value change is read back from the Stock Ledger (ERPNext rounds the rate to paise).
- Audit: each reconciliation gets a timeline comment `[Staff app · reco · ref:…]` with system → counted qty, rate,
  last purchase rate, value change and reason; the transfer remarks say "Stock reconciled first: MAT-RECO-…"
  (printed on the slip). Weekly e-mail `send_reco_digest` — **off unless** site_config `kgs_staff_reco_digest_to`
  (comma-separated addresses).
- Not on the bulk (> 150 lines) background path.
- Production context (2026-10-02): SBGD has 1,440 negative items (−97,115 units) and 2,749 at zero; 1,408 of them have
  no valuation and only 93 of those a last purchase rate — expect managers to type rates often.

## Owner decisions (2026-10-02)
| Question | Answer |
|---|---|
| Routes | All: SBGD ↔ Stores/KGS Warehouse, godown ↔ vans, godown → shop counter, new locations |
| Flow | Direct one-step transfer (no Goods In Transit leg) |
| Who submits | Any Stock User / Stock Manager |
| Phones | Android + iPhone camera scanning (+ Bluetooth scanners) |
| Login | Longer session for the app |
| Slip | Yes — printable transfer slip |

## Layout
| Path | What |
|---|---|
| `frontend/` | Vue 3 + Vite + Tailwind source. `package.json` lives ONLY here — one at the app root makes `bench build` run yarn and abort production builds (postbuild fails the build if it appears) |
| `frontend/scripts/postbuild.mjs` | moves the shell to `www/staff.html`, stamps the service worker, copies icons + the barcode WASM, safety asserts (no `v-html`, no `.__`, no API keys / `/api/resource`, SW `/api` guard) |
| `trustbit_school_book_seller/public/staff/` | **built, committed** assets (hashed JS/CSS, icons, `zxing-1.3.4/zxing_reader.wasm`) — served from `/assets/…`, so no `bench build` on deploy |
| `trustbit_school_book_seller/www/staff.html` | GENERATED shell — never hand-edit |
| `trustbit_school_book_seller/www/staff.py` | shell context: CSRF token, `window.staffEnv` = `{enabled, sw, allowed, user}`, `no_cache = 1` |
| `trustbit_school_book_seller/www/staff/sw.min.js`, `manifest.webmanifest` | service worker (scope `/staff/`, `.min.js` = served raw, not Jinja) and manifest (not under `/assets`, which is cached ~1 year) |
| `staff_app/api.py` | all endpoints (POST-only, Stock User/Manager, per-user rate limit 120/min) |
| `staff_app/session_extend.py` | longer sessions for logins made through the app |
| `trustbit_school_book/print_format/kgs_transfer_slip/` | standard Print Format "KGS Transfer Slip" (Stock Entry) |
| `staff_app/dev_tests/` | local-bench check scripts (see its README) — `check_*` names on purpose, so `bench run-tests` never imports them |

Rebuild after any frontend change: `cd frontend && yarn install && set -o pipefail && yarn build` (Node 18 OK;
`barcode-detector` is pinned to 2.3.1 because 3.x needs Node 20). Commit the source AND the regenerated
`public/staff/`, `www/staff.html`, `www/staff/*` together.

## Routes
`/staff/home` (home + manifest start_url) · `/staff/login` · `/staff/transfer` · `/staff/transfers` · `/staff/t/<Stock Entry>` · `/staff/bulk/<ref>`.
**Never make `/staff/` a page the app depends on:** production nginx 301s every trailing-slash URL (`/staff/` → `/staff`),
and `/staff` is outside the PWA scope `/staff/` — Android then won't offer install / shows a browser bar (found on
the first deploy, 2026-10-02; fixed by moving home to `/staff/home`). Bare `/staff` still opens the app.
Each top-level path has its own `website_route_rules` entry in `hooks.py`. **There is deliberately no
`/staff/<path>` catch-all** — it would swallow `sw.min.js` and the manifest (Betul lesson 386). A new
screen needs a new rule, or a hard refresh on it 404s.

## Endpoints (`trustbit_school_book_seller.staff_app.api.*`)
| Method | Purpose |
|---|---|
| `boot` | user, manager flag, warehouses (leaf, enabled, not Transit; via `get_list`, so User Permissions apply) with items-in-stock counts, default From (Stock Settings) |
| `lookup_item(code, from, to)` | Item Barcode (→ that barcode's UOM, e.g. PKT) → `custom_isbn_barcode` → item code |
| `get_item`, `search_items(txt, from)` | search: every word must match name/code/ISBN, 15 rows, in-stock first |
| `stock_levels(item_codes, from, to)` | one call to refresh all lines after a warehouse change |
| `create_transfer(from, to, items, client_ref, remarks)` | builds AND submits the Material Transfer |
| `my_transfers(scope, days)`, `get_transfer(name)` | lists (Stock Manager may see everyone) / detail + slip PDF URL |

### Rules `create_transfer` enforces (the phone's checks are only convenience)
- **Availability under a row lock** (`SELECT … FOR UPDATE` on `tabBin`), summed across all lines of an item.
  Production has `allow_negative_stock = 1`, so ERPNext alone would transfer stock that is not there.
- **Never back-dated:** `set_posting_time = 0` → now (CLAUDE.md Rule 15 — back-dated stock documents queue reposts).
- No item with **valuation rate 0** in the source (193 such bins on production, 2026-10-02) — avoids ₹0 moves
  and "Valuation Rate missing".
- UOM must be on the item; whole-number UOMs (Nos, Set, Box) refuse fractions; qty > 0.
- Same company, From ≠ To, no group / Transit / disabled warehouse. ≤ 150 lines per transfer.
- **Idempotent:** `client_ref` (UUID per draft) is stored in `remarks` as `[Staff app · ref:…]` and checked
  first, plus a Redis lock while saving — a retried tap returns the existing transfer, never a second one.
  If the network drops mid-save the phone LOCKS the draft and only offers "Check and finish" (the same
  request again), so edited lines can never be sent under an already-used reference.
- Line-level failures come back as `{"ok": 0, "problems": [{idx, item_code, message}]}`; nothing is created.
- Normal ERPNext permissions apply (`insert()` / `submit()` as the user; Stock User has create + submit).
- India Compliance's Stock Entry GST/e-waybill checks are inert on production (`enable_e_waybill_for_sc = 0`).

## Longer sessions (`session_extend.py`)
Production `session_expiry` is 01:00 and every user has 2FA, so without this staff would type password + OTP
every idle hour. **Only sessions created by a login from the app** (`staff_app: 1` is sent with both the
password and the OTP call) of a **Stock User/Manager** get `kgs_staff_session_days` days. Desk logins keep the
hour. Three mechanisms (ported from Betul `ts_session_extend.py`):
1. `on_session_creation` stamps `session_expiry = "<days*24>:00:00"` + `staff_app = 1` into the session.
2. `after_request` re-issues the `sid` cookie with the long Max-Age for stamped sessions.
3. cron every 10 min (`touch_staff_sessions`) slides `tabSessions.lastupdate` so the DB path (used after a
   Redis FLUSHALL on deploy) and the daily reaper don't expire them — bounded by the session's own activity.

**Off unless** site_config `kgs_staff_session_days` ≥ 1 (max 30). Turning it off stops new long sessions;
existing ones live until they expire — to end them now, clear those users' sessions.

## Kill switches (site_config, no deploy)
- `kgs_staff_app_disabled: 1` — every endpoint refuses, the shell shows "switched off".
- `kgs_staff_app_sw_off: 1` — every phone unregisters its service worker on next launch.
- `kgs_staff_session_days: 0` — no new long sessions.
- `kgs_staff_bulk_in_shop_hours: 1` — allow >150-line background transfers during shop hours (default: refused).
- `kgs_staff_reco_digest_to: "a@x, b@y"` — weekly e-mail of app-made reconciliations (default: off).

## Scanning
Android Chrome uses the native `BarcodeDetector`. iPhone Safari has none, so the `barcode-detector` polyfill
(ZXing → WASM, 0.9 MB) is lazy-loaded — self-hosted under `/assets/…/staff/zxing-1.3.4/`, never from a CDN
(`src/data/scanner.js` `ZXING_DIR` must match the folder; postbuild checks). Production nginx 1.18 has no
`application/wasm` MIME type: the decoder still works (falls back from streaming compile; tested), it just
downloads the file twice on first use. Optional fix: add `application/wasm wasm;` to nginx mime types.
Bluetooth/USB scanners work without focusing a field (fast keystrokes + Enter are caught page-wide).

## Deploy runbook (production) — evening only, after 19:30 IST and a quiet till check
No migrate, no `bench build`, no Redis FLUSHALL (a flush cold-starts the POS catalogue — CLAUDE.md timing notes).
1. Count bills in the last 10 min (`creation >= NOW() + INTERVAL 320 MINUTE`); wait if tills are billing.
2. Anchor: `mkdir /root/predeploy_<date>_staff_app`; save book_seller HEAD (`git rev-parse HEAD`), `sites/apps.txt`;
   niced DB backup.
3. As frappe_user in `apps/trustbit_school_book_seller`: `git pull upstream main` (fast-forward only).
4. Print format (no migrate): `bench --site splashbox.in execute frappe.modules.import_file.import_file_by_path --args '["<abs path>/trustbit_school_book/print_format/kgs_transfer_slip/kgs_transfer_slip.json"]'`
5. Scheduler job row for the new cron (normally made by migrate):
   `bench --site splashbox.in execute frappe.core.doctype.scheduled_job_type.scheduled_job_type.sync_jobs`
6. `bench --site splashbox.in set-config kgs_staff_session_days 7`
7. Hooks changed (route rules, after_request, on_session_creation): graceful web reload
   `supervisorctl signal HUP frappe-bench-web:frappe-bench-frappe-web`, then drop the cached hooks/routes:
   `bench --site splashbox.in execute frappe.cache.delete_value --args '["app_hooks"]'` and
   `bench --site splashbox.in execute frappe.website.utils.clear_website_cache`.
   If `/staff/transfer` still 404s, restart the web program (`supervisorctl restart frappe-bench-web:`).
8. Verify over HTTPS: `/staff`, `/staff/home`, `/staff/transfer` 200 with `window.staffEnv`; `/staff/sw.min.js` is JS with a
   `staff-shell-` name; manifest; one hashed asset; the `.wasm`; 0 new tracebacks / 5xx in the logs.
9. Phone check with the owner: install, sign in (password + OTP), confirm the cookie lives 7 days, scan one
   real book, and — only with the owner's OK — move 1 piece SBGD → Stores - KGS and back; print the slip.
Rollback: `git reset --hard <anchor HEAD>` (as frappe_user) → HUP + step 7 cache drops →
`set-config kgs_staff_session_days 0` → `frappe.delete_doc("Print Format", "KGS Transfer Slip")` →
`sync_jobs` again. Transfers already made are normal Stock Entries (cancel in desk if wrong).

## Before staff use it for real
- **Shop counter route:** every till sells from SBGD - KGS. Moving stock to a counter warehouse only works if
  the 11 POS Profiles are switched to it AND the shop floor gets an opening transfer — otherwise each counter
  sale drives SBGD negative. Needs its own planned evening and the owner's warehouse name.
- **New locations:** create the Warehouse in desk (leaf, under the right company) — it appears in the app.
- Users need the **Stock User** role (17 enabled users hold Stock User/Manager on 2026-10-02).
- Movement of goods worth > ₹50,000 by road may need an e-way bill even between own premises — owner/CA to
  confirm for van loads; the app does not create e-way bills.

## Tests (local bench, 2026-10-02)
`check_staff_api.py` 63/63 · `check_staff_http.py` 36/36 (incl. 2FA login, 7-day vs 1-hour cookies,
keep-alive, session surviving Redis loss vs an idle desk session expiring) · `check_staff_browser.py` 22/22
(phone viewport, native + WASM camera scanning with a fake camera, keyboard-wedge scanner, over-stock block,
draft survives reload, submit, slip link, lists) · `check_wasm_mime.py` (nginx 1.18 MIME) pass.
Bulk (2026-10-02 evening): `check_staff_bulk.py` 43/43 (set expansion, all stock, CSV + XLSX, 320 lines → 3 parts,
re-run safety, stop mid-way, shop-hours + manager gates) · `check_staff_bulk_browser.py` 18/18 with a real local
`bench worker --queue long` (set + CSV merge, Stock User blocked >150, all stock there and back in the background).
Reconciliation (2026-10-03): `check_staff_reco.py` 39/39 · `check_staff_reco_browser.py` 17/17 (both make fresh items per run).
Not testable locally: the PDF itself (wkhtmltopdf cannot resolve `site1.local`; the HTML render was checked)
and real phones — do step 9 of the runbook.
