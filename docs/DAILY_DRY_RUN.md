# Daily Import Dry Run

> Offline dry run only. No Tmall/Qianniu request was replayed, no MySQL table was changed, and no raw Cookie/Token/signature value is written here.

- Business day: `2026-07-29`
- Timezone: `Asia/Shanghai`
- Source script: `D:\PyPrograms\Ador_tmall\_core\Tmall_Data.py`
- Capture DB: `artifacts\local\reqable_capture.sqlite3`
- Generated at: `2026-07-30T17:55:29.009469+08:00`

## Guardrails

| Check | Value |
| --- | ---: |
| Platform requests executed | `0` |
| MySQL writes | `0` |
| SQLite access mode | `read_only_uri` |
| Raw cookie/token persisted | `False` |

## Captured Day Params

| Business date | Date mode | Files |
| --- | --- | ---: |
| `2026-07-29` | `dateRange_day` | 5 |

## Dry-Run Batch

Selected priorities: `A, A-`

| Priority | Function | Method | Table | Date mode | Capture fit | Shape status |
| --- | --- | --- | --- | --- | --- | --- |
| `A-` | `get_tmall_dailyshopdata` | `GET` | `dailyshopdata` | `dateRange_day` | `related` `/portal/coreIndex/new/overview/v3.json` (10 files) | `related_json_metric_candidate` |
| `A` | `get_tmall_product_sales_daily` | `GET` | `product_sales_daily` | `dateRange_day` | `exact` `/cc/item/view/top.json` (5 files) | `path_seen_without_json_metric_body` |
| `A` | `get_taobao_seckill` | `GET` | `taobao_seckill` | `epoch_ms_range` | `exact` `/extend/api/tbhjActivityDataQuery.json` (1 files) | `path_seen_without_json_metric_body` |
| `A` | `get_traffic_source` | `GET` | `traffic_source` | `dateRange_day` | `exact` `/flow/v5/shop/source/tree/v4.json` (2 files) | `path_seen_without_json_metric_body` |
| `A` | `get_rtb_plan_data` | `POST` | `rtb_plan_data` | `date_string_range` | `exact` `/report/query.json` (1 files) | `path_seen_without_json_metric_body` |
| `A` | `get_member_overview` | `GET` | `member_overview` | `dateRange_day` | `exact` `/domain/oneQuery.json` (45 files) | `json_shape_seen_but_metric_mapping_unconfirmed` |

## Request Contracts

### `get_tmall_dailyshopdata`

- Priority: `A-`
- Legacy path: `/portal/coreIndex/getShopMainIndexes.json`
- Method: `GET`
- URL: `https://sycm.taobao.com/portal/coreIndex/getShopMainIndexes.json`
- Target table: `dailyshopdata`
- Query params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only keys: `none`
- Execute request: `False`
- Write database: `False`
- Capture evidence:
  - `related` `/portal/coreIndex/new/overview/v3.json`: json-like `6` files
    Metric-like fields: `payAmt`, `rfdSucAmt`, `uv`
  - `related` `/portal/coreIndex/new/trend/v3.json`: json-like `6` files
    Metric-like fields: `payAmt`, `rfdSucAmt`, `uv`
  - `related` `/portal/coreIndex/new/overview/v2.json`: json-like `3` files
    Shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`
- Legacy metric mapping preview: `adStrategyAmt.value`, `admCostFamtQzt.value`, `cartByrCnt.value`, `cartItemCnt.value`, `cltItmCnt.value`, `cubeAmt.value`, `oldRepeatByrRate.value`, `olderPayAmt.value`, `p4pExpendAmt.value`, `payAmt.value`, `payByrCnt.value`, `payItmCnt.value`, `payOldByrCnt.value`, `payOrdCnt.value`

### `get_tmall_product_sales_daily`

- Priority: `A`
- Legacy path: `/cc/item/view/top.json`
- Method: `GET`
- URL: `https://sycm.taobao.com/cc/item/view/top.json`
- Target table: `product_sales_daily`
- Query params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29", "page": "1", "pageSize": "10"}`
- Runtime-only keys: `token`
- Execute request: `False`
- Write database: `False`
- Capture evidence:
  - `exact` `/cc/item/view/top.json`: json-like `0` files
- Legacy metric mapping preview: `crtAmt.value`, `crtByrCnt.value`, `crtItmQty.value`, `crtRate.value`, `item.title`, `itemCartByrCnt.value`, `itemCltByrCnt.value`, `itemId.value`, `itemStatus`, `itmBounceRate.value`, `itmPv.value`, `itmUv.value`, `juPayAmt.value`, `mtdPayAmt.value`

### `get_taobao_seckill`

- Priority: `A`
- Legacy path: `/extend/api/tbhjActivityDataQuery.json`
- Method: `GET`
- URL: `https://sale.taobao.com/extend/api/tbhjActivityDataQuery.json`
- Target table: `taobao_seckill`
- Query params for `2026-07-29`: `{"startTime": "1785254400000", "endTime": "1785254400000"}`
- Runtime-only keys: `_tb_token_`
- Execute request: `False`
- Write database: `False`
- Capture evidence:
  - `exact` `/extend/api/tbhjActivityDataQuery.json`: json-like `0` files
- Legacy metric mapping preview: `ipvUv`, `itemCnt`, `payOrderAmt`, `payOrderCnt`, `payOrderCntCoef`

### `get_traffic_source`

- Priority: `A`
- Legacy path: `/flow/v5/shop/source/tree/v4.json`
- Method: `GET`
- URL: `https://sycm.taobao.com/flow/v5/shop/source/tree/v4.json`
- Target table: `traffic_source`
- Query params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only keys: `none`
- Execute request: `False`
- Write database: `False`
- Capture evidence:
  - `exact` `/flow/v5/shop/source/tree/v4.json`: json-like `0` files
- Legacy metric mapping preview: `cartByrCnt`, `cltItmCnt`, `crtByrCnt`, `crtRate`, `crtVldAmt`, `flowBizType`, `newUv`, `payAmt`, `payByrCnt`, `payPct`, `payRate`, `traffic_source`, `uv`, `uv,newUv,cartByrCnt,cltItmCnt,payByrCnt,payByrCnt,payRate,payAmt,payPct,uvValue,crtByrCnt,crtVldAmt,crtRate`

### `get_rtb_plan_data`

- Priority: `A`
- Legacy path: `/report/query.json`
- Method: `POST`
- URL: `https://one.alimama.com/report/query.json`
- Target table: `rtb_plan_data`
- Query params for `2026-07-29`: `{"bizCode": "universalBP"}`
- Runtime-only keys: `csrfId`
- Execute request: `False`
- Write database: `False`
- Body template: `{"bizCode": "universalBP", "source": "baseReport", "rptType": "campaign", "splitType": "day", "startTime": "2026-07-29", "endTime": "2026-07-29", "pageSize": 100, "page": 1, "queryFieldIn": ["adPv", "alipayDirAmt", "alipayDirNum", "alipayIndirAmt", "alipayIndirNum", "alipayInshopAmt", "alipayInshopAmtAvg", "alipayInshopCost", "alipayInshopNum", "alipayInshopNumAvg", "alipayInshopUv", "cartRate", "click", "deepInshopPv", "gmvInshopAmt", "hyPayAmt", "hyPayNum", "hySgUv", "inshopPotentialUv", "inshopPotentialUvRate", "inshopPv", "inshopPvRate", "inshopUv", "itemColCart", "itemColCartCost", "itemColDirNum", "itemColIndirNum", "itemColInshopCost", "itemColInshopNum", "itemColInshopRate", "naturalPayAmt", "newAlipayInshopUv", "newAlipayInshopUvRate", "orgNaturalPv", "prepayDirAmt", "prepayDirNum", "prepayIndirAmt", "prepayIndirNum", "prepayInshopAmt", "prepayInshopNum"]}`
- Capture evidence:
  - `exact` `/report/query.json`: json-like `0` files
- Legacy metric mapping preview: `adPv`, `alipayDirAmt`, `alipayDirNum`, `alipayIndirAmt`, `alipayIndirNum`, `alipayInshopAmt`, `alipayInshopAmtAvg`, `alipayInshopCost`, `alipayInshopNum`, `alipayInshopNumAvg`, `alipayInshopUv`, `cartRate`, `click`, `deepInshopPv`

### `get_member_overview`

- Priority: `A`
- Legacy path: `/domain/oneQuery.json`
- Method: `GET`
- URL: `https://sycm.taobao.com/domain/oneQuery.json`
- Target table: `member_overview`
- Query params for `2026-07-29`: `{"dateType": "day", "dateRange": "2026-07-29|2026-07-29"}`
- Runtime-only keys: `token`
- Execute request: `False`
- Write database: `False`
- Capture evidence:
  - `exact` `/domain/oneQuery.json`: json-like `24` files
    Shape preview: `$:object`, `code:number`, `data:object`, `message:string`, `data.id:number`, `data.crowds:array`, `data.location:string`, `data.modifier:string`
- Legacy metric mapping preview: `totalMbrCnt,paidMbrCnt,mbrPayAmt,mbrUnitPrice,repurMbrRate`, `{"needPeriodsCrc":true}`


## Deferred

| Priority | Function | Legacy path | Reason |
| --- | --- | --- | --- |
| `C` | `get_tmall_statistics` | `/mc/bybt/sellerData/businessOverview/statistics.json` | not in dry-run priority set |
| `C` | `get_store_living_data` | `/s_content/shop/broadcast/click/transform.json` | not in dry-run priority set |
| `C` | `get_live_overview` | `/s_content/shop/broadcast/amount/compose/overview.json` | not in dry-run priority set |
| `C` | `get_live_talent_data` | `/s_content/live/cooperate/room/list.json` | not in dry-run priority set |
| `C` | `get_cps_data_overview` | `/openapi/param2/1/gateway.unionadv/data.home.overview.json` | not in dry-run priority set |
| `C` | `get_brand_zone_data` | `/report/query/rptAdvertiserSubListNew.json` | not in dry-run priority set |
| `C` | `get_tmall_shopping_gold` | `/xsite/rc/getRcOverall.json` | not in dry-run priority set |

## Next Adapter Step

- First live-capable worker should keep the same contract shape: build request -> parse response -> validate row count -> preview rows -> write only after explicit enablement.
- `path_seen_without_json_metric_body` means the endpoint path was observed in local response text, but the current body sample is not a metric JSON response.
- `json_shape_seen_but_metric_mapping_unconfirmed` means JSON exists, but legacy metric keys were not found in the captured shape; it needs a closer paired request/response sample from Reqable.
- `related_json_metric_candidate` means a newer or neighboring endpoint has JSON plus metric-like fields, so it is useful for adapter design but still needs exact request/response pairing.
- Runtime credential keys are listed only as names. Values must come from a local secret provider at execution time.
