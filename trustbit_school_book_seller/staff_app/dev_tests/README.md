# Staff app dev tests (local bench only — never run against production)

Run on the dev bench (`/Users/warroom/frappe-bench`, site `site1.local`), with Redis up and
`bench --site site1.local serve --port 8001` running. They create test masters (KGS-T-*,
"Godown - DCV", staff1/mgr1/nostock@example.com) and restore every setting they touch.

| Script | Run from | What |
|---|---|---|
| `check_staff_api.py` | `frappe-bench/sites`: `../env/bin/python <path>` | 63 checks: lookup chain, UOM, availability lock, refusals, idempotency, slip render |
| `check_staff_http.py` | same | 37 checks: shell/SW/manifest/assets, 2FA login, 7-day vs 1-hour cookies, keep-alive job, session after Redis loss |
| `check_paper_api.py` | same | 161 checks: Order from Paper — net rate from real papers, matching, uploads, fake AI reading, live lines while reading (stream scanner, polls, fallback restart), save PO/SO, learning, roles, settings; the real Anthropic code path (streamed SSE) against a local mock server. Makes KGS-PT-* items, "Paper Test Agency", "PT RDPS 3", paper_*@example.com |
| `check_paper_browser.py` | playwright venv + `bench worker --queue default,short` (after check_paper_api.py; restart both after Python changes) | 84 checks: PO paper end to end on a phone viewport incl. the live reading screen (cards, progress, tick), a 2-page PDF drawn by pdf.js (from memory + after a reload), remembered names + rate-total warning on the next paper, SO with copies, owner settings. Sets site_config `kgs_paper_ai_fake` (with `_stream_delay`) and removes it again |
| `setup_paper_purchase_site.py` | `frappe-bench/sites`: `../env/bin/python <path> paper.local` | ONE-TIME setup of a THROWAWAY site with erpnext + india_compliance + trustbit_school_pro + this app, setup wizard not yet run: KGS-like company + GSTIN, GST templates, in-state / out-state / unregistered suppliers. Refuses site1.local / splashbox.in |
| `check_paper_purchase.py` | same, `<path> paper.local` | 77 checks: Receipts and Bills from paper — access list, link to PO / Receipt, money check, GST preview, submit, repeat bill / filed period → draft only, Bill from the Receipt, direct Bill IGST + freight, last bought, ranking. Read jobs run in-process (fake AI) |
| `check_paper_purchase_browser.py` | playwright venv + `bench --site paper.local serve --port 8002` + a `default,short` worker (after check_paper_purchase.py) | 48 checks: Receipt → Bill on a phone viewport (link step, red bar, fixes, submit, Make the bill now), owner settings |
| `check_staff_bulk.py` | same (after check_staff_api.py) | 43 checks: school set, all stock, CSV/XLSX, 320-line background split, re-run, stop mid-way, gates |
| `check_staff_bulk_browser.py` | playwright venv + `bench worker --queue long` running | 18 checks: bulk UI end to end, moves all of Stores - DCV to Godown and back |
| `make_barcode_video.py` | bench python | writes `barcode.y4m` (fake camera) |
| `check_home_browser.py` | a venv with `playwright` (after check_staff_api.py + check_paper_api.py) | 65 checks: Home / tab bar / More (1.14.0) — `po_waiting` per role (owner, purchase user, stock user, no role, Guest), owner / purchase-only / stock-only Homes, tabs + badge, `?status=` filter, More, Sign out, Continue transfer. Plants 2 papers for home_owner@example.com and turns Receipts and Bills on for it; puts the settings back |
| `check_staff_browser.py` | a venv with `playwright` | 22 checks: full transfer on a phone viewport, native + WASM (iPhone path) camera scanning |
| `check_wasm_mime.py` | same | WASM decoder still works when nginx sends `application/octet-stream` (production nginx 1.18) |

The browser scripts point `EXE` at a cached Playwright headless shell; adjust it to your machine.
