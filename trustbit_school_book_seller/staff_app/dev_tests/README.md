# Staff app dev tests (local bench only — never run against production)

Run on the dev bench (`/Users/warroom/frappe-bench`, site `site1.local`), with Redis up and
`bench --site site1.local serve --port 8001` running. They create test masters (KGS-T-*,
"Godown - DCV", staff1/mgr1/nostock@example.com) and restore every setting they touch.

| Script | Run from | What |
|---|---|---|
| `check_staff_api.py` | `frappe-bench/sites`: `../env/bin/python <path>` | 63 checks: lookup chain, UOM, availability lock, refusals, idempotency, slip render |
| `check_staff_http.py` | same | 37 checks: shell/SW/manifest/assets, 2FA login, 7-day vs 1-hour cookies, keep-alive job, session after Redis loss |
| `check_paper_api.py` | same | 130 checks: Order from Paper — matching, uploads, fake AI reading, save PO/SO, learning, roles, settings; the real Anthropic code path against a local mock server. Makes KGS-PT-* items, "Paper Test Agency", "PT RDPS 3", paper_*@example.com |
| `check_paper_browser.py` | playwright venv + `bench worker --queue default,short` (after check_paper_api.py) | 69 checks: PO paper end to end on a phone viewport, remembered names on the next paper, SO with copies, owner settings. Sets site_config `kgs_paper_ai_fake` and removes it again |
| `check_staff_bulk.py` | same (after check_staff_api.py) | 43 checks: school set, all stock, CSV/XLSX, 320-line background split, re-run, stop mid-way, gates |
| `check_staff_bulk_browser.py` | playwright venv + `bench worker --queue long` running | 18 checks: bulk UI end to end, moves all of Stores - DCV to Godown and back |
| `make_barcode_video.py` | bench python | writes `barcode.y4m` (fake camera) |
| `check_staff_browser.py` | a venv with `playwright` | 22 checks: full transfer on a phone viewport, native + WASM (iPhone path) camera scanning |
| `check_wasm_mime.py` | same | WASM decoder still works when nginx sends `application/octet-stream` (production nginx 1.18) |

The browser scripts point `EXE` at a cached Playwright headless shell; adjust it to your machine.
