# Daily Endpoint Candidates

- Source script: `D:\PyPrograms\Ador_tmall\_core\Tmall_Data.py`
- Test day: `2026-07-29`
- Note: captures made on 2026-07-30 may request business date `2026-07-29` because daily reports usually pull yesterday.
- Mode: offline contract analysis. No platform request replay was executed.

## Captured Daily-Shaped Requests

| Business date | Date mode | Files | Note |
| --- | --- | ---: | --- |
| `2026-07-29` | `dateRange_day` | 5 | request body has day params; paired response is not necessarily metric data |

## Summary

| Priority | Function | Table | Date mode | Legacy path | Capture evidence |
| --- | --- | --- | --- | --- | --- |
| `A-` | `get_tmall_dailyshopdata` | `dailyshopdata` | `dateRange_day` | `/portal/coreIndex/getShopMainIndexes.json` | related /portal/coreIndex/new/overview/v3.json (10 files) |
| `A` | `get_tmall_product_sales_daily` | `product_sales_daily` | `dateRange_day` | `/cc/item/view/top.json` | exact 5 files |
| `C` | `get_tmall_statistics` | `statistics` | `dateRange_day` | `/mc/bybt/sellerData/businessOverview/statistics.json` | not observed in local body analysis |
| `A` | `get_taobao_seckill` | `taobao_seckill` | `epoch_ms_range` | `/extend/api/tbhjActivityDataQuery.json` | exact 1 files |
| `A` | `get_traffic_source` | `traffic_source` | `dateRange_day` | `/flow/v5/shop/source/tree/v4.json` | exact 2 files |
| `A` | `get_flow_overview` | `store_daily_flow_overview` | `dateRange_day` | `/flow/new/guide/trend/overview.json` | exact local response shape, sample on 2026-07-30 |
| `A` | `get_rtb_plan_data` | `rtb_plan_data` | `date_string_range` | `/report/query.json` | exact 1 files |
| `A` | `get_member_overview` | `member_overview` | `dateRange_day` | `/domain/oneQuery.json` | exact 45 files |
| `C` | `get_store_living_data` | `store_living_data` | `dateRange_day` | `/s_content/shop/broadcast/click/transform.json` | not observed in local body analysis |
| `C` | `get_live_overview` | `live_overview` | `dateRange_day` | `/s_content/shop/broadcast/amount/compose/overview.json` | not observed in local body analysis |
| `C` | `get_live_talent_data` | `live_talent_data` | `dateRange_day` | `/s_content/live/cooperate/room/list.json` | not observed in local body analysis |
| `C` | `get_cps_data_overview` | `cps_overview` | `date_pair` | `/openapi/param2/1/gateway.unionadv/data.home.overview.json` | not observed in local body analysis |
| `C` | `get_brand_zone_data` | `brand_zone_data` | `date_pair` | `/report/query/rptAdvertiserSubListNew.json` | not observed in local body analysis |
| `C` | `get_tmall_shopping_gold` | `shopping_gold` | `dateRange_day` | `/xsite/rc/getRcOverall.json` | not observed in local body analysis |

## Priority A: Good First Daily Tests

These are the safest first candidates for the `2026-07-29` business-date importer contract because they either have exact local evidence or strong same-module evidence.

### `get_tmall_dailyshopdata`

- Priority: `A-`
- URL: `https://sycm.taobao.com/portal/coreIndex/getShopMainIndexes.json`
- Table: `dailyshopdata`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only params: `none`
- Capture related candidates:
  - `unknown/portal/coreIndex/new/overview/v3.json` seen in `10` files
  - `unknown/portal/coreIndex/new/trend/v3.json` seen in `10` files
  - `unknown/portal/coreIndex/new/overview/v2.json` seen in `7` files
  - `unknown/portal/coreIndex/new/getTableData/v3.json` seen in `6` files
  - `unknown/portal/coreIndex/new/trend/v2.json` seen in `4` files
- Metric keys from legacy mapping: `adStrategyAmt.value`, `admCostFamtQzt.value`, `cartByrCnt.value`, `cartItemCnt.value`, `cltItmCnt.value`, `cubeAmt.value`, `oldRepeatByrRate.value`, `olderPayAmt.value`, `p4pExpendAmt.value`, `payAmt.value`, `payByrCnt.value`, `payItmCnt.value`, `payOldByrCnt.value`, `payOrdCnt.value`, `payPct.value`, `payRate.value`, `pv.value`, `rfdSucAmt.value`

### `get_tmall_product_sales_daily`

- Priority: `A`
- URL: `https://sycm.taobao.com/cc/item/view/top.json`
- Table: `product_sales_daily`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29", "page": "1", "pageSize": "10"}`
- Runtime-only params: `token`
- Capture exact match: `unknown/cc/item/view/top.json` seen in `5` files
- Metric keys from legacy mapping: `crtAmt.value`, `crtByrCnt.value`, `crtItmQty.value`, `crtRate.value`, `item.title`, `itemCartByrCnt.value`, `itemCltByrCnt.value`, `itemId.value`, `itemStatus`, `itmBounceRate.value`, `itmPv.value`, `itmUv.value`, `juPayAmt.value`, `mtdPayAmt.value`, `mtdPayItmCnt.value`, `newPayByrCnt.value`, `olderPayAmt.value`, `payAmt`

### `get_taobao_seckill`

- Priority: `A`
- URL: `https://sale.taobao.com/extend/api/tbhjActivityDataQuery.json`
- Table: `taobao_seckill`
- Date params for `2026-07-29`: `{"startTime": "<day_start_ms>", "endTime": "<day_start_ms>"}`
- Runtime-only params: `_tb_token_`
- Capture exact match: `unknown/extend/api/tbhjActivityDataQuery.json` seen in `1` files
- Metric keys from legacy mapping: `ipvUv`, `itemCnt`, `payOrderAmt`, `payOrderCnt`, `payOrderCntCoef`

### `get_traffic_source`

- Priority: `A`
- URL: `https://sycm.taobao.com/flow/v5/shop/source/tree/v4.json`
- Table: `traffic_source`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only params: `none`
- Capture exact match: `unknown/flow/v5/shop/source/tree/v4.json` seen in `2` files
- Metric keys from legacy mapping: `cartByrCnt`, `cltItmCnt`, `crtByrCnt`, `crtRate`, `crtVldAmt`, `flowBizType`, `newUv`, `payAmt`, `payByrCnt`, `payPct`, `payRate`, `traffic_source`, `uv`, `uv,newUv,cartByrCnt,cltItmCnt,payByrCnt,payByrCnt,payRate,payAmt,payPct,uvValue,crtByrCnt,crtVldAmt,crtRate`, `uvValue`

### `get_flow_overview`

- Priority: `A`
- URL: `https://sycm.taobao.com/flow/new/guide/trend/overview.json`
- Table/view: `store_daily_flow_overview_metrics`
- Date params for `2026-08-01`: `{"dateType": "day", "dateRange": "2026-08-01|2026-08-01", "device": "0", "indexCode": "uv,itmUv,payByrCnt"}`
- Runtime-only params: `token`, request session headers/cookies
- Capture evidence: local 2026-07-30 response body has `data.data` metric group
- Metric keys confirmed from sample: `uv`, `itmUv`, `payByrCnt`, `pv`, `avgPv`, `oldUv`, `newUv`, `shopCltByrCnt`, `liveRoomUv`, `shortVideoUv`, `imageUv`, `shopVisitUv`
- Pending value confirmation: `跳失率` and flow endpoint's own `平均停留时长`

### `get_rtb_plan_data`

- Priority: `A`
- URL: `https://one.alimama.com/report/query.json`
- Table: `rtb_plan_data`
- Date params for `2026-07-29`: `{"startTime": "2026-07-29", "endTime": "2026-07-29", "pageSize": "100"}`
- Runtime-only params: `none`
- Capture exact match: `unknown/report/query.json` seen in `1` files
- Metric keys from legacy mapping: `adPv`, `alipayDirAmt`, `alipayDirNum`, `alipayIndirAmt`, `alipayIndirNum`, `alipayInshopAmt`, `alipayInshopAmtAvg`, `alipayInshopCost`, `alipayInshopNum`, `alipayInshopNumAvg`, `alipayInshopUv`, `cartRate`, `click`, `deepInshopPv`, `gmvInshopAmt`, `hyPayAmt`, `hyPayNum`, `hySgUv`

### `get_member_overview`

- Priority: `A`
- URL: `https://sycm.taobao.com/domain/oneQuery.json`
- Table: `member_overview`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only params: `token`
- Capture exact match: `unknown/domain/oneQuery.json` seen in `45` files
- Metric keys from legacy mapping: `totalMbrCnt,paidMbrCnt,mbrPayAmt,mbrUnitPrice,repurMbrRate`, `{"needPeriodsCrc":true}`


## Remaining Candidates

### `get_tmall_statistics`

- Priority: `C`
- URL: `https://sycm.taobao.com/mc/bybt/sellerData/businessOverview/statistics.json`
- Table: `statistics`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only params: `token`
- Capture evidence: no URL/path candidate found in the current offline body analysis
- Metric keys from legacy mapping: `/xsite/frame/bybt`, `adStrategyAmt.value`, `admCostFamtQzt.value`, `bybtCateId`, `bybtItemUv`, `bybtOnlineItemCnt`, `bybtPayAmt`, `bybtPayByrCntNew`, `bybtPayOrdCntNew`, `bybtPayOrdQty`, `cartByrCnt.value`, `cartItemCnt.value`, `cltItmCnt.value`, `cubeAmt.value`, `oldRepeatByrRate.value`, `olderPayAmt.value`, `p4pExpendAmt.value`, `payAmt.value`

### `get_store_living_data`

- Priority: `C`
- URL: `https://sycm.taobao.com/s_content/shop/broadcast/click/transform.json`
- Table: `store_living_data`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only params: `token`
- Capture evidence: no URL/path candidate found in the current offline body analysis
- Metric keys from legacy mapping: `broadcastDealItemCnt`, `broadcastDealOrderCnt`, `broadcastDealUv`, `broadcastItemClickUv`, `broadcastLookUv`, `clickDealRate`, `livePlayPayAmt`, `lookItemClickRate`

### `get_live_overview`

- Priority: `C`
- URL: `https://sycm.taobao.com/s_content/shop/broadcast/amount/compose/overview.json`
- Table: `live_overview`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only params: `token`
- Capture evidence: no URL/path candidate found in the current offline body analysis
- Metric keys from legacy mapping: `afterPlayPayAmt`, `broadcastLivePayAmt`, `broadcastLookUv`, `broadcastPayAmt`, `live_overview`, `payAmtPerThousand`, `shopPlayPayAmt`, `visitUvPerHour`

### `get_live_talent_data`

- Priority: `C`
- URL: `https://sycm.taobao.com/s_content/live/cooperate/room/list.json`
- Table: `live_talent_data`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29", "page": "1", "pageSize": "10"}`
- Runtime-only params: `token`
- Capture evidence: no URL/path candidate found in the current offline body analysis
- Metric keys from legacy mapping: `dealOrderCnt`, `dealPieceCnt`, `goodsAddCartCnt`, `goodsAddCartUv`, `goodsClickCnt`, `goodsClickUv`, `goodsDealAmt`, `goodsDealCnt`, `goodsDealUv`, `goodsSingleAmt`, `liveSessionCount`, `live_talent_data`

### `get_cps_data_overview`

- Priority: `B`
- URL: `https://ad.alimama.com/openapi/param2/1/gateway.unionadv/data.home.overview.json`
- Table: `store_daily_cps_overviews`
- Date params for `2026-07-29`: `{"startDate": "2026-07-29", "endDate": "2026-07-29"}`
- Runtime-only params: `_tb_token_`
- Response path: `data.result`
- Capture status: verified with a live daily response; `success=true`, `resultCode=200`, and `data.result` is a one-row list
- Metric keys from legacy mapping: `pay_bmkt_fee_8`, `pay_ord_amt_8`, `pay_ord_cfee_8`, `pay_ord_cfee_rt_8`, `pay_ord_num_8`, `pay_ord_sfee_8`, `pay_ser_ord_sfee_rt_8`, `uclk_uv_8`, `sett_ord_total_fee_8`, `sett_ord_num_8`, `sett_ord_amt_8`, `dep_ord_num_8`, `dep_ord_dep_amt_8`, `dep_ord_rest_amt_8`, `dep_ord_total_amt_8`, `sett_bmkt_fee_8`

### `get_brand_zone_data`

- Priority: `C`
- URL: `https://brandsearch.taobao.com/report/query/rptAdvertiserSubListNew.json`
- Table: `brand_zone_data`
- Date params for `2026-07-29`: `{"startDate": "2026-07-29", "endDate": "2026-07-29"}`
- Runtime-only params: `csrfID`
- Capture evidence: no URL/path candidate found in the current offline body analysis
- Metric keys from legacy mapping: `brandsearch.taobao.com`, `click`, `click_uv`, `impression`, `requestCnt`

### `get_tmall_shopping_gold`

- Priority: `C`
- URL: `https://sycm.taobao.com/xsite/rc/getRcOverall.json`
- Table: `shopping_gold`
- Date params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only params: `token`
- Capture evidence: no URL/path candidate found in the current offline body analysis
- Metric keys from legacy mapping: `avgRcAmt`, `itmUv`, `rcAmt`, `rcByrCnt`, `rcCapitalAmt`, `rcPayAmt`, `rcPayByrCnt`, `rcPayOrdPbt`, `rcRate`, `rechargeItemCnt`, `rechargeOrdCnt`, `rechargeSucRfdAmt`, `statDate`


## Implementation Notes

- Build the first worker as a dry-run importer: generate URL, normalized params, target table, and expected response shape, but do not write to MySQL until the parsed row count and field mapping are validated.
- Keep legacy cookies/tokens outside code and Markdown. Runtime credential loading should be a separate adapter concern.
- For `dateRange_day`, use `YYYY-MM-DD|YYYY-MM-DD`; for `date_pair`, use `startDate=endDate=YYYY-MM-DD`; for `epoch_ms_range`, convert the local day start to milliseconds.
- `token`, `_tb_token_`, and `csrfID` are contract placeholders only. They must be resolved at runtime and never persisted in reports.
- The 2026-07-30 capture suggests some SYCM old endpoints have moved to `/portal/coreIndex/new/*/v3.json`; keep a versioned adapter instead of hard-coding one URL in the page layer.
