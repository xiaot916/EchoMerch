# Warehouse

Warehouse code owns normalized reporting data after a source adapter returns raw API payloads.

Recommended layers:

- `platforms` and `stores`: stable platform/store identity and display metadata.
- `staging_*`: parser output that stays close to each upstream endpoint shape.
- `fact_*` and `dim_*`: stable analytics tables used by dashboards and BI views.

Source adapters should not write final analytics tables directly. They should hand raw payloads to parser and mapper code owned here.

The first implemented mapper is `sycm_overview.py`. It reads saved response
shapes from `/portal/coreIndex/new/overview/v3.json` and
`/portal/coreIndex/new/trend/v3.json`, creates a Tmall store identity from
`content.data.self.userId`, and writes:

- one `store_daily_overviews` row for the requested business day;
- dedicated wide rows for each business domain, keyed by store and business day.

Business fact tables and BI views intentionally keep only `店铺ID`,
`业务日期`, and metric columns. Platform name, store name, and platform-side
store identifiers stay in `stores` / `platforms` and should be joined only by
read models or UI queries that need display context.

The current sample maps `admCostFamtQzt` to the business column
`全站推广花费`. The same table keeps the confirmed promotion splits
`关键词推广花费`, `精准人群推广花费`, `智能场景花费`, and `淘宝客佣金`;
unconfirmed legacy fields such as `钻展花费` are not created.

Business metric rows are stored in their dedicated wide tables. Raw response
files can remain in the local artifact directory for retry/debug, but raw JSON,
evidence IDs, channel order, and source paths are not stored in SQLite business
tables.

For trend responses, the parser slices the `self.*` arrays by `statDate` and
the requested business day. The 2026-07-04 data overview screenshot confirms
`realPayrealRfdRate` as `签收退款率`: raw `0.006334459...` renders as `0.63%`.
`sucRefundRate` is kept separately as `成功退款率`.

The second mapper is `sycm_flow_overview.py`. It reads saved response shapes
from `/flow/new/guide/trend/overview.json` and writes only long-form metrics
with the `flow.` prefix. This keeps the flow-board values separate from the
home-page overview values for the same business day.

Current flow overview BI fields:

- `flow.uv` -> `访客数`
- `flow.itmUv` -> `商品访客数`
- `flow.payByrCnt` -> `支付买家数`
- `flow.pv` -> `浏览量`
- `flow.avgPv` -> `人均浏览量`
- `flow.oldUv` -> `老访客数`
- `flow.newUv` -> `新访客数`
- `flow.shopCltByrCnt` -> `关注店铺人数`
- `flow.liveRoomUv` -> `直播间访客数`
- `flow.shortVideoUv` -> `短视频访客数`
- `flow.imageUv` -> `图文访客数`
- `flow.shopVisitUv` -> `店铺页访客数`

`跳失率` and the flow endpoint's own `平均停留时长` are still treated as
field candidates until a response body containing those metric values is
captured. The BI view can fall back to the home-page `stayTime` metric for
`平均停留时长` when a same-day overview response has already been ingested.

The Datawar activity calendar endpoint
`/datawar/v4/activity/actList/getActivityCalendar.json` is stored in the
separate `store_activity_calendar_events` table. It keeps only the business
fields needed for calendar-style activity tracking:

- `店铺ID`, `业务日期`, `活动ID`
- `活动名称`, `活动类型`, `活动状态`
- `活动开始时间`, `活动结束时间`
- `报名开始时间`, `报名结束时间`
- `活动标签`, `活动层级`, `活动阶段`, `店铺参与状态`

The read model is exposed as
`/warehouse/stores/{store_id}/activity-calendar`.

The new customer discount overview endpoint
`/s_content/brandnewdiscount/overview.json` is parsed by
`sycm_new_customer_discount.py` and stored in
`store_daily_new_customer_discount_overviews`. The fact table contains only
the store ID, business day, and ten business metrics. Request dimensions and
comparison values such as `channelId` and `cycleCrc` are not duplicated into
the fact table.

Shopping gold, BYBT, content asset overview, and Taojinbi responses are parsed
by dedicated modules and stored in separate daily fact tables. See
`docs/SYCM_MARKETING_CONTENT_INTERFACES.md` for endpoint mappings, Chinese
columns, MTop signing, and ingestion commands.

## Historical Cloud Migration

The one-time read-only migration utilities live in `backend/scripts`:

- `import_legacy_daily_overviews.py` imports the legacy `dailyshopdata` table.
- `import_legacy_datasets.py` imports compatible product, traffic, customer,
  marketing, promotion campaign, and live-streaming datasets.

Both scripts read the old connection from `LEGACY_DATABASE_URL` or an existing
legacy `.env` file, set the MySQL session to read-only, and write only local
SQLite facts. They are idempotent by default: existing local keys are skipped;
pass `--refresh-existing` only when a confirmed source correction should
replace a local fact.

```powershell
python scripts\import_legacy_daily_overviews.py `
  --legacy-env-file D:\PyPrograms\Ador_tmall\.env

python scripts\import_legacy_datasets.py `
  --legacy-env-file D:\PyPrograms\Ador_tmall\.env
```

Legacy traffic rows are normalized by date and source hierarchy. Historical
recursive records that lost a third-level label are aggregated, and their
conversion rate, UV value, and payment-amount share are recalculated from the
aggregated counts and amounts. Promotion plans use `店铺ID + 业务日期 + 推广计划ID`
as their fact key; live-talent rows use `店铺ID + 业务日期 + 合作主播ID`.
