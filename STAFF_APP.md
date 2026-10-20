# KGS Staff app (`/staff`) — warehouse transfers + order from paper

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

## Short stock → transfer what the system has + add the extra in the destination ("option B", 2026-10-03)
History: first live 01:21 IST as "option A" (`bf21aee`: reconcile From up to the count, then transfer it all). The
owner then chose **option B** after seeing the documents: a Stock Reconciliation always records the NEW TOTAL (Qty
column) — the real change is its "Quantity Difference" — and they wanted the transfer to show only what existed.
Option B, when a Stock Manager counts a short item at review:
1. the **transfer** moves only what the system has in From (never below 0);
2. a **Stock Reconciliation in the TO warehouse** adds only the extra = min(count, qty moved) − system qty in From.
Examples (system in From → count → move): 5 → 8 → 8: transfer 5, reconciliation in To 5 → 8 (difference 3).
To already 10: transfer 5, To 15 → 18. From 0: no transfer, To 0 → 8 (Home shows "Extra stock added"). From −20:
no transfer, To +8, **From stays −20** (the app never fixes a minus in From; value change is only 8 × rate). Count 6
of 8: transfer 5 + extra 1. To −4: transfer 5 (→ 1), reconcile 1 → 4. To −20: refused ("… is in minus … ask the
office"), nothing saved. Count 10 for a move of 8 (system 5): extra 3, the app says the other 2 stay in From unseen.
Count below the system qty: only the count moves, the app says the system still shows more.
Everything in one request (all or nothing); the transfer remarks/slip say "Extra added in <To>: MAT-RECO-…"; each
reconciliation gets the audit comment `[Staff app · reco · ref:…]` (system/counted/transferred/extra/rate/reason).
Retries are idempotent, including reconciliation-only requests (found by that comment tag).
Same rules otherwise: Stock Managers only (Stock Users stay blocked), managers may add no-stock items, zero-cost items
refused, price = last purchase rate → From valuation → To valuation → typed, never 0, ±50% warning, mandatory reason,
≤ 100 rows per reconciliation, not on the bulk path, weekly digest off unless `kgs_staff_reco_digest_to`.
Shared phone logic: `frontend/src/data/reco.js` (mirrors `_create_transfer_with_recos` — keep in step).

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

## Order from Paper (DEPLOYED 2026-10-20 03:40 IST, `0c103da` — ON since 03:44 IST; net-rate fix 1.11.1 live 05:35 IST `de8bcc8`; live lines while reading = 1.12.0)
Deployed after hours (0 bills in the last 10 min; last bill 19:26 the evening before) by the runbook below: niced DB
backup `20261020_033814-splashbox_in-database.sql.gz` (96 s), anchor `/root/predeploy_20261020_order_from_paper/`
(HEAD before `8867aa7`, apps.txt, reload logs), ff-merge, `reload_doc` × 4, Order Paper Settings saved with
**enabled = 0, so_enabled = 0** (no `kgs_paper_ai_key` on the server yet — a tile that cannot read would only confuse
purchase staff), `app_hooks` + website cache dropped, HUP web. Verified: 8 routes 200 over HTTPS with the new bundle,
Guest 403 on the paper endpoints, 0 Error Log / 0 nginx 5xx / 0 tracebacks after the deploy, all 18 Stock Users keep
the app + long session, the 3 Shop Owners open Settings, `post_deploy_verify_live.sh` all passed.
The user then set `kgs_paper_ai_key` (verified with `GET /v1/models` → 200 and one tiny Haiku call) and switched it ON in
`/staff/settings` at 03:44 IST.

**First real papers (20-10, 04:00–04:30 IST) found a rate bug.** On both papers (a Progress quotation photo, a Selina
PDF) the AI put the LIST price in `rate` and the discount in its own field, and the old `paper_rate()` trusted `rate`
first — PUR-ORD-2026-00710 (Selina, a test draft, never sent) was saved at 605/580 instead of 484/464. Reading and
matching were right; amounts and totals were read exactly. Fix (1.11.1): the net rate is worked out from the numbers,
never from the label (see "Saving" below); a discount printed only at the bottom is put on the lines when it explains
the printed totals exactly; the AI is told to copy rate/amount as printed and never apply a discount itself; the save
screen warns when the rates do not explain the paper's totals.
**Deploys of 20-10 (after hours, 0 bills in the last 10 min, no migrate/build/flush; ff + HUP web + app_hooks/website
cache):** 1.11.1 net-rate fix `de8bcc8` at 05:35 IST (backup `20261020_053339-…`, anchor `/root/predeploy_20261020_rate_fix/`).
OP-2026-00003 (the user's test photo, read at 04:45 by the old code, waiting Ready) had only its lines' `paper_rate`
recomputed with the fix: ₹1,36,400 at list → ₹95,480 = the paper's printed net (before-copy of `lines_json` in the anchor,
timeline comment on the paper). PUR-ORD-2026-00710 (Selina, draft) was NOT touched — still at 605/580.
1.12.0 live lines `a6cd7d3` at 05:58 IST (backup `20261020_055716-…`, anchor `/root/predeploy_20261020_live_lines/`) and
the fine-grained streaming fix `5d1986f` at 06:03 IST. Verified: /staff routes 200, new bundle + pdf.js chunks served as
`application/javascript`, Guest 403, `get_paper(light, since, run)` on the server, 0 Error Log / 0 nginx 5xx,
`post_deploy_verify_live.sh` passed; a real streamed Haiku read of a typed 30-line text (no paper, no document): lines
from 1.4 s to 4.6 s. Not yet seen: the new screen on a real phone with a real paper.
**To switch on:** set the key (runbook step 4), then the owner ticks *Order from paper is on* in `/staff/settings`;
then one real paper end to end (step 7).

A photo or PDF of a supplier's quotation / price list / order list (or a school book list) becomes a **draft
Purchase Order** (optionally sent straight into the "Purchase Order Approval" workflow) or a **draft Sales Order**.
Plan, costs and decisions: `KGS/PLAN_order_from_paper.md`; mockup https://claude.ai/artifact/5oCQ6wG8AHnKJrpm3MpKVB.
Owner decisions (2026-10-20): Claude Haiku 5.5 with automatic fallback to Sonnet 5.5; settings changeable only by
System Manager + Shop Owner; the Anthropic key is OK'd (data leaves the server: pages + candidate item names);
OpenAI and Google Gemini shown as "Coming soon" behind a provider interface. Sales Orders ship switched OFF.

**Sonnet 5.5 / Opus 5.5 refuse a forced tool call (1.13.1).** `tool_choice` "tool"/"any" → HTTP 400 `tool_choice: type
"tool" and "any" are not supported for this model.` (also Fable 5.1 / Mythos 5.1; Haiku 5.5 still takes it). Until 1.13.1
that 400 was shown as "Model … is not available" — every Sonnet/Opus read failed on 20-10. `NO_FORCED_TOOL` models (and
any model that sends that 400, remembered per process) get `tool_choice` `{"type": "auto", "disable_parallel_tool_use":
true}`, the line `TOOL_ONLY` appended to the system prompt, `max_tokens + THINKING_ROOM` (they always think first — a
silent ~8 s before the first line) and, when streamed, `eager_input_streaming: true` on the tool instead of the beta
header. A text answer (`end_turn` without the tool) is asked for once more. "Not available" now means 404 / not found only.
Settings note: on 20-10 the Better model is Haiku (= the main model), so the automatic second read is OFF — the user
chose to leave it so; set Better model = Sonnet 5.5 in `/staff/settings` to turn it back on.
Deployed 2026-10-20 18:51 IST, light (ff-merge `fbbf536`→`ba44307` + HUP web; 0 bills in the 10 min before, 0 papers
reading). Verified: a Sonnet 5.5 read of OP-2026-00042 through the default queue (nothing saved) — 12 s, 5 lines,
₹6,744 = the paper; 0 Error Log, 0 nginx 5xx. Anchor `/root/predeploy_20261020_model_fix/`. Rollback: `git reset --hard
fbbf536` (as frappe_user) + HUP web.

**Flow.** `/staff/paper` → `paper.upload_paper` (≤ 10 photos re-encoded to JPEG ≤ 2000 px, or one PDF ≤ 10 MB /
20 pages; magic-byte check; private Files `OP-…-N.jpg/pdf`; Order Paper "Uploaded") → read job on the **default**
queue (`job_id` per paper, deduplicated, after commit) → AI reading (forced tool `record_paper`) → matching →
"Ready" → the check screen polls every 2 s → person checks lines → `save_order` → draft PO/SO → names learned.

**Reading screen (1.12.0).** The reading is streamed (`stream: true`; the forced tool's input arrives as
`input_json_delta` fragments) WITH the `anthropic-beta: fine-grained-tool-streaming-2025-05-14` header — without it
the API streams a tool's input one whole top-level value at a time, so every line arrives together at the end
(measured on production 20-10, 30 lines, Haiku: all at 5.1 s; with the header from 1.3 s to 5.0 s; same tokens). That
mode does not validate the JSON: a final JSON that does not parse keeps the complete lines; a 400 naming the beta
re-reads without the header (lines then arrive at the end). `paper_read.LineStream` pulls out each finished object of the top-level `lines` array
(and the fields written before it: who sent the paper, its number); `paper.LiveReading` keeps the cleaned lines so far
(`text, qty, unit, rate, mrp, amount, page` — as printed, no matching) in Redis `kgs_paper_live:<paper>` (30 min TTL,
written ≤ once per 0.8 s, deleted when the job ends — never the DB). `get_paper(light=1, since, run)` returns only the
lines the phone lacks; `run` changes when the lines start over (fallback model → `attempt` 2 + the reason in `note`;
a stream broken half-way is retried once). Phases: reading → matching (build_state + AI double-check) → Ready.
Phone (`components/PaperReading.vue`): page strip (✓ read / outlined = being read; a page counts as read when a line
of a later page arrives — the AI writes in page order), the current page large with a sweep band (WHERE on the page is
not known), the last 3 lines as cards (played 90–450 ms apart behind the polls), "Photo/Page n of N · k lines so far",
then "Matching with our items…" and a tick with the real line count (from the Ready payload). Pages just sent come from
the phone's memory (`rememberSent`, last 2 papers); a paper opened later loads the stored files. PDFs are drawn by
pdf.js 4.10.38 (`data/pdfPages.js`, legacy build, lazy chunks ≈ 406 KB + a 1.36 MB worker emitted as `.js` — nginx
1.18 serves `.mjs` without a JavaScript type; `isEvalSupported: false`); if it fails, plain sheets stand in.
`frontend/.yarnrc` has `ignore-engines true` because pdfjs-dist 4 declares Node ≥ 20 and this build Mac runs 18.
If the reading looks wrong (lines don't add up to the printed total, or ≥ 2 unclear lines) it is read once more
with the fallback model, inside the monthly page cap.

**Matching ladder** (`paper_match.py`; green = sure, amber = one tap, red = left out unless chosen):
1. remembered code for this party → 2. remembered wording for this party → 3. ISBN / barcode → 4. our item code,
or their code already in ERPNext (Item Supplier `supplier_part_no` / Item Customer Detail `ref_code`) — all green;
5. another party's remembered name → amber; 6. fuzzy (IDF over item names, short-form synonyms, class guard,
MRP twin bonus — two editions of one book are told apart by the printed MRP) + optional AI double-check
(`choose_items`, may only pick among OUR candidates) → amber; 7. nothing → red.
A remembered line whose printed MRP changed, or whose item is now disabled, turns amber ("new edition?").
The fuzzy index is built only inside the background job (never in a web worker — DANGER 21).

**What `save_order` enforces** (the phone's checks are only convenience):
- Refused while any amber line is unchecked; red/left-out lines are listed in the PO remark / SO comment.
- Never back-dated (transaction date = today); needed-by ≥ today; warehouse = a leaf warehouse of the company.
- PO rate = the paper's NET rate (`paper_read.paper_rate`) or "our usual buying price". Net rate: with a discount, the
  line amount ÷ qty — unless that equals the list price (MRP, else the rate column), then list × (1 − discount); no
  amount → the rate column when it already equals MRP × (1 − discount), else list × (1 − discount). No discount: amount
  ÷ qty, else the rate column. The save screen warns when Σ net rate × qty matches neither printed total (before tax,
  or with 5/12/18/28/40 % GST), and loudly when the final total is BELOW the lines (a discount missing from the
  rates). A line with neither a paper price nor a buying price goes in at ₹0 (the save screen counts those). SO
  prices always come from our selling list, never from the paper.
- Inserted as the user (normal ERPNext permissions); "Send for Approval" via `apply_workflow` inside a savepoint —
  if it fails the PO stays a draft and the screen says why.
- Idempotent: `client_ref` + Redis lock; a paper no. already used for this party → "Save anyway?".
- The pages are attached to the PO/SO (File copies) with a timeline comment.

**Learning** happens only on save, only from lines a person kept: a *Code* alias (their code) and a *Text* alias
(their wording; " C<class>" is added when the wording has no class of its own), plus ERPNext's `supplier_part_no`
when empty. Purchase Managers (suppliers) and Sales Managers (customers) change/delete them under Remembered names.

**Who sees what** — tiles and endpoints per role (each endpoint checks its own roles):
| Role | Gets |
|---|---|
| Purchase User / Manager | "Purchase Order from paper" while the feature is on; Papers list |
| … and listed under *Who may make them* | "Receipt or Bill from paper" while *Receipts and Bills are on* |
| Sales User / Manager | "Sales Order from paper" only while *Sales Orders from paper* is also on |
| Purchase / Sales Manager, System Manager | change or delete remembered names (suppliers / customers) |
| System Manager, Shop Owner | Settings: on/off, model, fallback, double-check, page caps, ₹/$ + GST, model price table |
| Stock User / Manager | transfers as before; no paper tiles unless they also hold a purchase/sales role |

**AI + money.** `paper_read.py`: Anthropic Messages API via `requests`, one retry on 408/409/429/5xx/529, errors
turned into plain staff messages. Every call is recorded in `Order Paper.usage_json` (tokens, USD priced on the
REQUESTED model id — the API may answer with a dated id), shown in Settings as ₹ incl. GST for the month. Estimated
≈ ₹0.26/page on Haiku, ≈ ₹5.19 on Sonnet (7k in / 3k out tokens, ₹100/$, 18% GST — an estimate, not a measurement).

**site_config keys** (never print the key; it is never sent to the phone, an Error Log or a document — tested):
- `kgs_paper_ai_key` — the Anthropic key. Absent → tiles show "The AI service is not set up yet", nothing is read.
- `kgs_paper_ai_fake` — TESTS ONLY: a reading dict or a path to one; honoured only with developer_mode or no real key.
- `kgs_paper_ai_url` — TESTS ONLY: honoured only for 127.0.0.1 / localhost.

**Deploy runbook (when the owner asks) — after 19:30 IST, quiet tills.** No migrate / `bench build` / FLUSHALL.
1. Count bills in the last 10 min; anchor (book_seller HEAD, apps.txt, niced DB backup).
2. `git pull upstream main` (ff only) as frappe_user.
3. New tables without a migrate, child table first:
   `bench --site splashbox.in execute frappe.reload_doc --args '["trustbit_school_book","doctype","<dt>"]'` for
   `order_paper_model_price`, `order_paper_settings`, `order_paper`, `party_item_alias`.
4. The key, without echo / history / process args, from `sites/`: `sudo -u frappe_user ../env/bin/python -c "import
   getpass, frappe; frappe.init(site='splashbox.in', sites_path='.'); from frappe.installer import update_site_config;
   update_site_config('kgs_paper_ai_key', getpass.getpass('key: '))"`.
5. HUP web + drop `app_hooks` + website cache (new route rules: on the dev bench `/staff/papers`, `/staff/names`,
   `/staff/settings` 404'd on a direct load until the cached hooks were dropped).
6. `nginx -T | grep client_max_body_size` ≥ 20m (a 12 MB upload is ~16 MB as base64).
7. Verify: the 5 new routes 200; boot `paper.ready = 1`; Settings opens for the owner; then one REAL paper end to
   end with the owner (Order Paper → PO pending approval → owners' e-mail with the PDF).
Rollback: `git reset --hard <anchor>` + HUP + cache drops; remove the key (`update_site_config(..., "None")` — the
STRING "None"; Python None writes `null`). The four DocTypes are inert and can stay.

### Receipts and Bills from paper (1.13.0 `cf01b91`, LIVE 2026-10-20 15:57 IST — mockup v4 https://claude.ai/artifact/SFuLzMwDr3QV6LXPSGZAGb)
Deployed in shop hours at the user's request, the light way (no migrate / build / flush / restart, no full backup in shop
hours): before-copy = the 09:00 IST backup + dumps of `tabOrder Paper` and the Settings Singles rows in
`/root/predeploy_20261020_pr_pi/` (HEAD before `1f056db`); ff-merge; `reload_doc` order_paper_receiver, order_paper_settings,
order_paper; Settings saved with *Receipts and Bills are on*, receivers dollykhare.sb + vishnuk.kgs, freight account
"Freight & Forwarding Charges - KGS" (the one in use; "Freight and Forwarding Charges - KGS" was last used 13-05); HUP web;
app_hooks + website cache dropped. Verified: routes 200 with the new bundle, Guest 403, pr/pi = 1 only for the two
receivers, six PO papers read by the old code open fine, 0 Error Log / 0 nginx 5xx, `post_deploy_verify_live.sh` passed.
Owner decisions (20-10): (1) totals that don't match **block both Save draft and Submit** until fixed; (2) only the
people on the Settings list make Receipts / Bills (Dolly + Vishnu); (3) a Bill after a Receipt comes from the same
reading, a Bill made directly is read by the AI; match % shown everywhere; last purchase rate + discount shown.
Code: `staff_app/paper_purchase.py` (open documents, linking, money check, build PR/PI) called from `paper.py`.
- **Who:** `can_make` = Purchase role + Order Paper Settings `pr_pi_enabled` + the user in `receivers` (child DocType
  Order Paper Receiver). Boot `paper.pr` / `paper.pi`; the home tile "Receipt or Bill from paper".
- **Link step** (`set_links(name, mode, docs, version)`, modes `docs` / `none` / `change`): Receipt → the supplier's
  submitted POs with something to receive (+ Pending Approval POs greyed — ERPNext receives only a submitted PO); Bill →
  Receipts with `per_billed < 100` (due = qty − already billed incl. draft bills) first, then POs (a bill that adds
  stock). One doctype per paper. Doc % = paper lines found on it ÷ paper lines (scored in the read job against the doc's
  items: `score_docs`, never the index in a web request — DANGER 21); ticked from 60 %. A supplier change re-runs the
  job with reason `rematch` (stored `ai_json`, no AI).
- **Line ↔ row:** sure (exact, or a clear lead ≥ 0.60 by 0.12) → green "On the PO" 90–100 %; weaker → amber
  "Probably X line N"; no row → "Not on the linked PO" (allowed, goes in without a row). Unit and conversion come from the
  row (uom locked). More than due → amber card *Keep N* / *Make it due* (never blocked; over-receipt allowance is 1000 %).
- **Rates:** the paper's NET rate (`paper_read.paper_rate`) ÷ the unit ratio, else the row's rate; a person can type a
  rate (never ₹0 — Rule 16). `line_check`: qty × (rate / rate less discount / MRP less discount) must be within
  max(₹1, 0.6 % × qty, 0.1 % of the amount) of the printed amount, else "Doesn't add up" with *Make it N* when the
  amount ÷ rate is a whole number, or an edit of the numbers as read.
- **Money check** (`pp.totals`, on every change and again in `save_order`): Σ net rate × qty (+ Receipt: amounts of
  left-out lines and quantities not received) must equal the paper's item total, or its grand total less GST and charges,
  within ₹1. A Bill must carry every line. Nothing printed → each line is checked on its own. The save screen
  (`preview_purchase`) builds the document in memory: ERPNext / India Compliance GST template + rows, freight / packing
  charges the person adds (Actual, on Total, account = Settings *freight account*), rounding, grand total vs the paper.
- **Draft only** (Submit refused, Save draft allowed): the bill no. already on a Receipt / Bill of this supplier
  (`repeat_bill` — "Check supplier invoice uniqueness" is off on production), or a posting date inside a FILED GSTR-3B
  period, monthly or its QRMP quarter (`filed_period`, Rule 8 / 14).
- **Documents:** Receipt — posting today, `supplier_delivery_note` = bill no., rows linked `purchase_order` /
  `purchase_order_item`, `price_list_rate` + discount kept for history, the paper's printed MRP → `custom_pack_mrp`
  (Shelf Prices, trustbit_barcode). Bill — `bill_no`, `bill_date` = posting date = the paper's date (`set_posting_time`),
  rows linked `purchase_receipt` / `pr_detail` + PO, `update_stock = 0` when linked to a Receipt (stock never twice), 1
  otherwise. Inserted as the user; Submit inside a savepoint — a failed submit leaves the draft and says why. The paper is
  attached; the remark names the paper and the left-out lines.
- **Bill from the Receipt** (`make_bill`): a new Order Paper (purpose Bill, `source_paper` → the Receipt paper, which
  gets `bill_paper`) with the same reading and decisions, linked to that Receipt, files copied; offered on the saved
  screen once the Receipt is submitted and not fully billed.
- **Ranking** (`paper_match.rank_candidates`): fuzzy score − 0.08 for a dead item (no stock, no sale in 12 months, never
  bought / sold) + 0.06 bought from this supplier (else + 0.03 if active); the choose sheet shows rank, %, reasons and
  last bought (`get_item_facts`). "Xxx…" items and the xxx / DEACTIVATE groups are never suggested (search still finds
  them, flagged). A paper written by US (our GSTIN / name as the sender) has sender and addressee swapped
  (`_swap_if_ours`). Unknown supplier → suggestions from who supplied the matched items.
- **Last bought** (`paper_match.last_bought`): last 3 submitted Purchase Invoice lines per item with `net_rate > 0`,
  per stock unit (`net_rate ÷ conversion_factor`), discount = 1 − net ÷ list; the supplier's usual discount over 12
  months (≥ 5 lines). Shown on the line and in a sheet; never copied into the rate.
- **Kill switch:** untick *Receipts and Bills are on* in `/staff/settings` (POs keep working).

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
| `staff_app/paper.py` · `paper_read.py` · `paper_match.py` | Order from Paper: endpoints + read job · AI providers, files, costs · item matching |
| `trustbit_school_book/doctype/order_paper*`, `party_item_alias` | Order Paper, Order Paper Settings (single) + Order Paper Model Price (child), Party Item Alias |
| `trustbit_school_book/print_format/kgs_transfer_slip/` | standard Print Format "KGS Transfer Slip" (Stock Entry) |
| `staff_app/dev_tests/` | local-bench check scripts (see its README) — `check_*` names on purpose, so `bench run-tests` never imports them |

Rebuild after any frontend change: `cd frontend && yarn install && set -o pipefail && yarn build` (Node 18 OK;
`barcode-detector` is pinned to 2.3.1 because 3.x needs Node 20). Commit the source AND the regenerated
`public/staff/`, `www/staff.html`, `www/staff/*` together.

## Routes
`/staff/home` (home + manifest start_url) · `/staff/login` · `/staff/transfer` · `/staff/transfers` · `/staff/t/<Stock Entry>` · `/staff/bulk/<ref>`
· `/staff/paper` · `/staff/paper/<Order Paper>` · `/staff/papers` · `/staff/names` · `/staff/settings` (Order from Paper).
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
| `trustbit_school_book_seller.staff_app.paper.*` | Order from Paper (upload, get/update paper, parties/items search, save, names, settings) — see that section |

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
password and the OTP call) of a **user the app is open to** get `kgs_staff_session_days` days: Stock User/Manager,
and Purchase / Sales staff only while Order from Paper is on for them (`app_user_allowed(include_settings=False)` —
System Manager / Shop Owner opening only the settings page never get one). Desk logins keep the hour. Three mechanisms (ported from Betul `ts_session_extend.py`):
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
- Order from Paper: untick *Order from paper is on* in Order Paper Settings (owner can do it in the app), or remove
  `kgs_paper_ai_key` — nothing more is sent to the AI; saved orders and remembered names stay.

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
Option B (2026-10-03): `check_staff_reco.py` 43/43 (all six examples) · `check_staff_reco_browser.py` 20/20. All suites now
make fresh items per run (fixed test items drifted as suites moved stock around).
Not testable locally: the PDF itself (wkhtmltopdf cannot resolve `site1.local`; the HTML render was checked)
and real phones — do step 9 of the runbook.
Receipts and Bills (1.13.0, 2026-10-20): `check_paper_purchase.py` 77/77 on a throwaway site with India Compliance
(`setup_paper_purchase_site.py paper.local`: KGS-like company + GSTIN, in-state / out-state / unregistered suppliers,
books nil-rated, stationery 18 %, production's buying / stock / accounts settings) — access, PR from an approved PO
(over-delivery, misread qty fix, money check blocking both buttons, ₹0 refused, GST 72 on the register only, submit,
row links, net rates), repeat bill no. → draft only, Bill from the Receipt (blocked while a line is missing; packing
charge; submitted), direct Bill out-state IGST + freight, filed period → draft only, last bought, rematch, ranking facts ·
`check_paper_purchase_browser.py` 48/48 (phone viewport, paper.local on :8002 with a real worker: tile, link step with
match % + Best fit, red bar, Make it 9, Keep 60, Receipt submitted with linked rows, Make the bill now → Bill check
screen linked to the Receipt with no AI call, owner settings list + freight account). Regressions: `check_paper_api.py`
152/152, `check_paper_browser.py` 83/83.
Order from Paper (2026-10-20; counts after 1.12.0 — live lines): `check_paper_api.py` 152/152 (+ the stream scanner
over random fragment sizes / a cut-off answer, live lines per poll + new run on restart, the fallback starting over,
streamed SSE from the mock incl. a stream broken half-way, the beta header sent / refused, a broken final JSON) · `check_paper_browser.py` 83/83 (+ cards with the printed
text while the fake AI writes slowly, progress text, photo from memory, tick, a 2-page PDF drawn by pdf.js from memory
and after a reload from the stored copy, page 1 ticked when page 2 starts). Earlier (1.11.1): 135/135 (net rate from the
two real papers, bottom-of-paper discount, normalising, class guard, MRP twins, alias ladder,
upload refusals, fallback read, version conflicts, save PO + approval, idempotency, duplicate paper, learning,
SO + copies, roles, long-session rule, settings, page cap, rate limit; the real Anthropic code path against a local
mock server incl. 529 retry / 401 / credit error; the key in no log or document) · `check_paper_browser.py` 70/70
(phone viewport with a real worker: PO paper → choose supplier → Correct / Change twin / search → sent for approval;
same paper again → remembered + duplicate warning + rate-total warning; SO with copies; owner settings + remembered names). Regressions
after it: check_staff_api 63/63, check_staff_http 37/37, check_staff_bulk 43/43, check_staff_reco 43/43,
check_staff_browser 22/22, check_staff_reco_browser 20/20, check_staff_bulk_browser 18/18.
Not proven locally: the owners' approval e-mail (the job runs, but this Mac's wkhtmltopdf is an Intel binary —
"Bad CPU type" — so the PO PDF attachment fails; production's works) and real AI accuracy / cost — that needs the
owner's sample papers and the real key.
