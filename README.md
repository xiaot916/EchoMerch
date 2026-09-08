# EchoMerch

EchoMerch is a modular e-commerce operations console. The first release is a
read-only analytics workspace for the existing Tmall reporting database.

## Current scope

- FastAPI analytics API
- Vue 3 operations dashboard
- Read-only legacy data adapter
- Store, product, traffic, and promotion reporting
- System capability endpoint for feature boundaries
- Multi-page admin shell with empty, loading, and error states
- API contract catalog, daily import dry-run view, and operation guardrail center
- Local SQLite import run registry for previewing daily dry-run batches
- Tmall platform/store warehouse with offline SYCM overview/trend and flow overview parsers

Crawler execution, scheduled jobs, coupon creation, and other business actions
are intentionally not enabled in this release.

See `docs/ARCHITECTURE.md` for the module boundaries and
`docs/TMALL_CAPTURE_NOTES.md` for the offline packet-analysis template.

Offline Reqable analysis can be run against a small date window:

```powershell
python backend/scripts/analyze_reqable.py `
  --capture-dir "C:\Users\Moli\AppData\Roaming\Reqable\capture" `
  --since 2026-07-28 `
  --until 2026-07-30
```

The command writes a local SQLite database under `artifacts/local/` and a
sanitized report under `docs/REQABLE_CAPTURE_ANALYSIS.md`. It stores metadata,
endpoint candidates, field paths, inferred shapes, hashes, and counts only.
It does not replay requests or store raw credentials.

Build a sanitized daily-import dry run from the legacy Tmall script and the
local capture analysis database:

```powershell
python backend/scripts/dry_run_daily_import.py `
  --day 2026-07-29 `
  --source "D:\PyPrograms\Ador_tmall\_core\Tmall_Data.py" `
  --capture-db artifacts/local/reqable_capture.sqlite3
```

The dry run writes `docs/DAILY_DRY_RUN.md` and
`artifacts/local/daily_dry_run_YYYYMMDD.json`. It does not call the platform or
write to MySQL.

Ingest a saved SYCM overview or trend response into the local warehouse:

```powershell
python backend/scripts/ingest_sycm_overview.py `
  --response-file artifacts/local/raw_responses/sycm_overview_20260801.json `
  --day 2026-08-01 `
  --store-name "碧芭宝贝旗舰店"
```

The current sample creates platform `tmall`, store
local `平台ID=1`, `店铺ID=1`, `平台主体ID=2200573698992`, and one daily overview row. The parser keeps only
business metrics in SQLite; request Cookie, Token, raw JSON, evidence IDs, and
source paths are not stored in business tables.

Fetch and backfill the SYCM data overview endpoint by day:

```powershell
$env:SYCM_COOKIE = "<current browser cookie>"
$env:SYCM_TOKEN = "<current sycm token>"
python backend/scripts/backfill_sycm_overviews.py `
  --start 2025-01-01 `
  --end 2026-08-04
```

For daily scheduling, run the same importer for yesterday:

```powershell
python backend/scripts/backfill_sycm_overviews.py `
  --start yesterday `
  --end yesterday
```

### Daily collection entry point

Use the unified collector for the normal daily run. With no `--day`, it always
targets yesterday in `Asia/Shanghai`, so running it on 2026-08-21 collects the
completed business day 2026-08-20. Independent workers run with bounded
parallelism (default 2) to reduce end-to-end latency, while existing rows are
still skipped by the individual workers so retries remain safe by default.

```powershell
python backend/scripts/collect_daily.py `
  --session-source drissionpage
```

Use `--parallelism 1` when diagnosing a platform or browser-session issue; the
range is intentionally bounded to 1-8 workers. You can set the default with
`ECHO_COLLECTION_PARALLELISM`.

Inspect the resolved date and child commands without making network requests:

```powershell
python backend/scripts/collect_daily.py --plan
```

Run only selected datasets or explicitly repair one date:

```powershell
python backend/scripts/collect_daily.py `
  --day yesterday `
  --datasets sycm_overviews,sycm_item_rankings,customer_service `
  --session-source drissionpage

python backend/scripts/collect_daily.py `
  --day 2026-08-20 `
  --datasets sycm_overviews `
  --refresh-existing `
  --session-source drissionpage
```

Use `--list-datasets` to see the selectable names. Each dataset runs in its own
worker process; a failure is recorded but does not prevent later datasets from
running unless `--fail-fast` is set. The final non-secret execution summary is
written under `artifacts/local/daily_collection/`.

### Managed Browser Session

For regular daily imports, use a separate browser profile instead of copying
cookies into code or the database. Start the local session browser once:

```powershell
python backend/scripts/launch_tmall_session_browser.py
```

Log in to SYCM manually in that browser. The importer can then attach to the
local debugging port and use the browser cookies only for its current process:

```powershell
python backend/scripts/backfill_sycm_overviews.py `
  --start yesterday `
  --end yesterday `
  --session-source drissionpage
```

The browser profile lives under `artifacts/runtime/`, which is ignored by Git.
Cookies are not written to SQLite, JSON logs, response artifacts, or `.env`.
When the platform session expires, log in again through the same browser and
rerun the worker.

The collector reuses an already-open matching platform tab before creating a
new one. Jobs that share the same SPA (for example SYCM or Alimama promotion)
are serialized while independent platforms can still run in parallel. This
prevents one worker from navigating another worker's listener and avoids
accumulating temporary `about:blank` tabs.

The frontend keeps chart core and chart-type modules in separate lazy-loaded
chunks, so non-chart pages do not need to download the full chart bundle.

### PZ Brand Zone

The legacy `get_brand_zone_data` worker is available as a separate PZ
brand-zone adapter. It attaches to the managed browser, captures the current
frontend request contract and `csrfID` in memory, then fetches one business
day. Neither the session cookie nor `csrfID` is persisted.

```powershell
python backend/scripts/fetch_brandsearch_report.py `
  --day 2026-08-17 `
  --output artifacts/local/raw_responses/brandsearch_20260817.json `
  --session-source drissionpage

python backend/scripts/ingest_brandsearch_report.py `
  --response-file artifacts/local/raw_responses/brandsearch_20260817.json `
  --day 2026-08-17
```

It writes one idempotent row per store and business day to
`store_daily_brand_zone_overviews`. Confirmed metrics include impressions,
searches, clicks, add-to-cart, paid amount, paid orders, conversion, jump and
interaction clicks, favorites, and page views. `transactiontotal` is converted
from cents to currency units. `cost`, `cpc`, `cpm`, and `view_time` are not
stored until their units and business definitions are confirmed.

### CPS 淘宝客概览

The legacy CPS overview adapter uses
`https://ad.alimama.com/openapi/param2/1/gateway.unionadv/data.home.overview.json`
with `startDate=endDate` for each business day. It captures the short-lived
`_tb_token_` from the live CPS request in the managed browser, fetches the
response, and ingests the 16 fields under `data.result` into
`store_daily_cps_overviews`. The business table contains only store ID,
business date, and CPS metrics; runtime cookies, token values, raw JSON,
evidence IDs, and timestamps are not stored there.

The managed browser profile is reused by daily jobs until the platform expires
the session. The worker obtains the current request token in memory for every
run, so neither the token nor a copied Cookie needs to be configured for the
daily scheduler.

```powershell
python backend/scripts/launch_tmall_session_browser.py `
  --browser-port 9222 `
  --url https://ad.alimama.com/portal/v2/report/promotionDataPage.htm

python backend/scripts/fetch_cps_overview.py `
  --day 2026-08-17 `
  --output artifacts/local/raw_responses/cps_20260817.json `
  --session-source drissionpage `
  --browser-port 9222

python backend/scripts/ingest_cps_overview.py `
  --response-file artifacts/local/raw_responses/cps_20260817.json `
  --day 2026-08-17
```

Money and rate values are kept at the API's raw numeric scale. Amount values
are not converted from cents, and rate values such as `0.0696` are displayed
as percentages by multiplying by 100.

The backfill skips existing `store_daily_overviews` rows by default, writes
non-secret progress logs under `artifacts/local/raw_responses/`, and stops when
the login/session response is no longer usable.

Trend responses from `/portal/coreIndex/new/trend/v3.json` are sliced by
`self.statDate` and the requested `--day`, so a 30-day response can be used to
fill one specific business date. The data overview card field `签收退款率` maps
to `realPayrealRfdRate`; `sucRefundRate` remains a separate `成功退款率` metric.

Ingest a saved SYCM flow overview response into the same local warehouse:

```powershell
python backend/scripts/ingest_sycm_flow_overview.py `
  --response-file "C:\Users\Moli\AppData\Roaming\Reqable\capture\xxx-res-extract-body.reqable" `
  --day 2026-08-01 `
  --store-name "碧芭宝贝旗舰店" `
  --platform-store-id 2200573698992
```

The first flow parser targets `/flow/new/guide/trend/overview.json` and stores
only store-owned metrics with the `flow.` prefix, so it will not overwrite the
home-page data overview metrics for the same day.

For database inspection and BI, SQLite also creates two readable views:

- `store_daily_business_metrics`: a daily business view with the Chinese card fields from the SYCM data overview, including transaction, traffic, promotion, refund, repurchase, customer-service, after-sale, and logistics metrics.
- `store_daily_flow_overview_metrics`: a daily flow overview view with Chinese fields such as `商品访客数`, `跳失率`, `人均浏览量`, `老访客数`, `新访客数`, `直播间访客数`, and `店铺页访客数`.
- `store_daily_metric_values_readable`: all parsed metric rows joined with Chinese metric names, while preserving the original platform metric code for traceability.

The web console can turn a dry-run plan into a local preview record:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8001/api/v1/imports/runs/dry-run `
  -ContentType "application/json" `
  -Body '{"day":"2026-07-29"}'
```

Preview records are stored in `artifacts/local/echomerch_local.sqlite3`.
They keep run status, candidate endpoints, target tables, and mapping notes.

### Shared Console Access

The console has a local role and store-scope access layer. Keep it disabled on
a private development workstation, but enable it before sharing the web
console with another person:

```powershell
$env:ECHO_AUTH_ENABLED = "true"
$env:ECHO_AUTH_COOKIE_SECURE = "true"  # use false only for local HTTP testing
$env:ECHO_BOOTSTRAP_ADMIN_PASSWORD = "replace-with-a-12-character-password"
python backend/scripts/create_local_user.py `
  --username admin `
  --display-name 管理员
```

Open `/access` as a super administrator to create delegated accounts. The
built-in roles are `super_admin`, `admin`, `operations_supervisor`,
`store_manager`, and `operator`. Data management and system settings are
reserved for `super_admin`. Non-super-admin accounts must have one or more store scopes. Every protected
FastAPI route checks the session or Bearer token, the role permission, and the
requested store scope; hiding a menu entry in Vue is only a usability aid.
Sessions are HttpOnly and only a SHA-256 token hash is stored in SQLite. Tmall
and Alimama browser cookies remain a separate runtime integration concern and
are never used as EchoMerch user credentials.

Build a request/response contract map from Reqable capture logs and the local
analysis DB:

```powershell
python backend/scripts/analyze_reqable_pairs.py `
  --capture-dir "C:\Users\Moli\AppData\Roaming\Reqable\capture" `
  --capture-db artifacts/local/reqable_capture.sqlite3
```

The command writes `docs/REQABLE_REQUEST_RESPONSE_PAIRS.md`,
`artifacts/local/reqable_api_requests.sqlite3`, and
`artifacts/local/reqable_api_request_pairs.json`.

## Local development

For the normal local setup, run the root startup script. It always binds both
services to every network interface:

```powershell
.\start-dev.ps1
```

1. Copy `.env.example` to `.env` and set `LEGACY_DATABASE_URL`.
2. Start the API:

```powershell
$env:LEGACY_DATABASE_URL = "mysql+pymysql://..."
python -m uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8001
```

3. Start the web application:

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 9568
```

Both development servers listen on `0.0.0.0` so other devices on the same LAN
can open the dashboard. A fresh local database creates the default super
administrator `admin` with password `123456`; change it after the first login.

The API forces every legacy connection into a read-only transaction and only
contains `SELECT` statements.

Optional frontend API override in `frontend/.env`:

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8001"
```

Leave this override empty when accessing the dashboard from a phone. The
default Vite `/api` proxy works for both the computer and LAN devices, while a
phone would interpret `127.0.0.1` as the phone itself.

When the computer and phone are on the same LAN, open the frontend through the
computer's LAN IPv4 address, for example:

- `http://172.16.12.62:9568/contracts`
- `http://172.16.12.62:9568/imports`
- `http://172.16.12.62:9568/operations`

Useful local pages:

- `http://127.0.0.1:9568/contracts`
- `http://127.0.0.1:9568/imports`
- `http://127.0.0.1:9568/operations`

Useful warehouse APIs:

- `GET /api/v1/warehouse/platforms`
- `GET /api/v1/warehouse/stores`
- `GET /api/v1/warehouse/stores/{store_id}/daily-overview?day=2026-08-01`
- `GET /api/v1/warehouse/stores/{store_id}/daily-flow-overview?day=2026-08-01`
- `GET /api/v1/warehouse/stores/{store_id}/daily-metrics?day=2026-08-01`
