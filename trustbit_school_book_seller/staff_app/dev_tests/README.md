# Staff app dev tests (local bench only — never run against production)

Run on the dev bench (`/Users/warroom/frappe-bench`, site `site1.local`), with Redis up and
`bench --site site1.local serve --port 8001` running. They create test masters (KGS-T-*,
"Godown - DCV", staff1/mgr1/nostock@example.com) and restore every setting they touch.

| Script | Run from | What |
|---|---|---|
| `check_staff_api.py` | `frappe-bench/sites`: `../env/bin/python <path>` | 63 checks: lookup chain, UOM, availability lock, refusals, idempotency, slip render |
| `check_staff_http.py` | same | 36 checks: shell/SW/manifest/assets, 2FA login, 7-day vs 1-hour cookies, keep-alive job, session after Redis loss |
| `make_barcode_video.py` | bench python | writes `barcode.y4m` (fake camera) |
| `check_staff_browser.py` | a venv with `playwright` | 22 checks: full transfer on a phone viewport, native + WASM (iPhone path) camera scanning |
| `check_wasm_mime.py` | same | WASM decoder still works when nginx sends `application/octet-stream` (production nginx 1.18) |

The browser scripts point `EXE` at a cached Playwright headless shell; adjust it to your machine.
