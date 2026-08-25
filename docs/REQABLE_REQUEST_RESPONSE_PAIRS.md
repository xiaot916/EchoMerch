# Reqable Request/Response Pair Analysis

> Reqable MCP was probed first. It is reachable, but live capture returned zero retained records, so this report derives request contracts from local Reqable raw-body logs and response candidates from the local capture analysis DB.

- Generated at: `2026-07-30T18:15:01.011152+08:00`
- Capture dir: `C:\Users\Moli\AppData\Roaming\Reqable\capture`
- Capture DB: `artifacts\local\reqable_capture.sqlite3`
- Local request DB: `artifacts\local\reqable_api_requests.sqlite3`
- API observations extracted from request logs: `1121`
- Endpoint contracts: `235`
- Daily observations: `253`

## Important Boundary

- The same Reqable record for these request logs usually responds with a 1x1 GIF, because it is the frontend telemetry request that reports API calls.
- The real API request details are inside that telemetry payload: URL, method, status, params, selected headers, duration, and trace presence.
- Response candidates below are matched by endpoint path from local response bodies. They are useful schema evidence, but not guaranteed to be the exact response pair unless marked by future live MCP records.
- Credential values are not written to project artifacts. Sensitive fields are retained as presence markers with length/hash metadata.

## Business Dates

| Business date | Observations |
| --- | ---: |
| `2026-01-01` | 1 |
| `2026-06-30..2026-07-29` | 9 |
| `2026-07-16..2026-07-22` | 2 |
| `2026-07-20..2026-07-26` | 8 |
| `2026-07-23..2026-07-29` | 19 |
| `2026-07-28` | 12 |
| `2026-07-29` | 136 |
| `2026-07-30` | 23 |
| `20260728` | 8 |
| `20260729` | 35 |

## Priority Paths

| Path | Method | Calls | Daily | Dates | Response files | JSON-like | Sample params |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| `/portal/coreIndex/new/overview/v3.json` | `GET` | 1 | 1 | `2026-07-29`:1 | 10 | 6 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `needCycleCrc=true`, `_=1785398110348` |
| `/portal/coreIndex/new/trend/v3.json` | `GET` | 1 | 1 | `2026-07-29`:1 | 10 | 6 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `_=1785398110348` |
| `/portal/coreIndex/new/getTableData/v3.json` | `-` | 0 | 0 | - | 6 | 3 | - |
| `/portal/coreIndex/getShopMainIndexes.json` | `-` | 0 | 0 | - | 0 | 0 | - |
| `/cc/item/view/top.json` | `GET` | 3 | 3 | `2026-07-29`:2, `2026-07-28`:1 | 5 | 0 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `indexCode=payAmt,subPayOrdAmt,sucRefundAmt,payItmCnt,subPayOrdItmQty,payByrCnt,payRate,newPayByrCnt,payOldByrCnt,olderPayAmt,juPayAmt,mtdPayAmt,mtdPayItmCnt,ytdPayAmt,itemStatus,itemCartCnt,itemCartByrCnt,itemCltByrCnt,visitCartRate,visitCltRate,itmUv,itmPv,itmStayTime,itmBounceRate,seGuideUv,seGuidePayByrCnt,seGuidePayRate,uvAvgValue,starLevel001,itemUnitPrice1,fCharge,pDROI`, `page=1`, `pageSize=10`, `order=desc`, `orderBy=payAmt`, `device=0` |
| `/flow/v5/shop/source/tree/v4.json` | `-` | 0 | 0 | - | 2 | 0 | - |
| `/domain/oneQuery.json` | `GET` | 52 | 51 | `2026-07-29`:44, `2026-07-28`:2, `2026-07-30`:5, `2026-06-30..2026-07-29`:1 | 45 | 24 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `domainCode=tao.shop.customer.overview`, `showType=overview`, `indexCodes=statDate,repurchaseTop1ItemId,paylosByrCnt,repurchaseTop1CustomerCnt,repurchaseTop2CustomerCnt,repurchaseTop3CustomerCnt,revisitTop4ItemId,revisitTop5ItemId,revisitTop1CustomerCnt,revisitTop2CustomerCnt,revisitTop3CustomerCnt,revisitTop4CustomerCnt,revisitTop5CustomerCnt,repurchaseTop2ItemId,repurchaseTop3ItemId,repurchaseTopItem,repurchaseRegularCustomerCnt,repeatByrRate6m,repurchaseCycleRivalGood,repurchaseCycleRivalAvg,repeatByrRate1m,repeatByrRate3m,payMordCnt,revisitDays3m,revisitRegularCustomerCnt,revisitPayOrdAmt,revisitTop1ItemId,revisitTop2ItemId,revisitTop3ItemId,revisitTopItem,repurchasePayOrdAmt,regularCustomerCnt,regularCustomerPayOrdAmt,repurchasePayPct,repurchaseRepeatOrdCnt,revisitPayPct,avgRevisitDays,regularCustomerPayPct,regularCustomerRatio,revisitCustomerRatio,repurchaseCustomerRatio,regularCustomerRatioAvgGood,revisitCustomerRatioAvgGood,repurchaseCustomerRatioAvgGood,hasPurchasedCustomerCnt,revisitPaylosTopItem,repurchasePaylosTopItem,regularPaylosTopItem`, `needCycleCrc=true`, `device=0`, `_=1785398296443` |
| `/extend/api/tbhjActivityDataQuery.json` | `-` | 0 | 0 | - | 1 | 0 | - |
| `/report/query.json` | `-` | 0 | 0 | - | 1 | 0 | - |
| `/portal/month/overview.json` | `GET` | 5 | 5 | `2026-07-29`:5 | 3 | 3 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `sellerType=online`, `_=1785391648624` |
| `/portal/month/trend.json` | `GET` | 5 | 5 | `2026-07-29`:5 | 4 | 3 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `sellerType=online`, `_=1785391648624` |
| `/portal/level/info/v3.json` | `POST` | 5 | 5 | `2026-07-29`:5 | 6 | 6 | `dateRange=2026-07-29|2026-07-29`, `body=dateType=day`, `_=1785391648624` |
| `/portal/board/grow/factor/overview.json` | `GET` | 2 | 2 | `2026-07-29`:2 | 7 | 3 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `device=2`, `_=1785391650454` |
| `/portal/board/grow/factor/trend.json` | `GET` | 2 | 2 | `2026-07-29`:2 | 7 | 3 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `_=1785391650454` |
| `/portal/board/grow/factor/promo/top.json` | `GET` | 1 | 1 | `2026-07-29`:1 | 3 | 3 | `dateType=day`, `dateRange=2026-07-29|2026-07-29`, `page=1`, `pageSize=5`, `order=desc`, `orderBy=pSpend`, `_=1785391650539` |

## Top Daily Contracts

| Host | Path | Method | Calls | Dates | Status |
| --- | --- | --- | ---: | --- | --- |
| `sycm.taobao.com` | `/domain/oneQuery.json` | `GET` | 52 | `2026-07-29`:44, `2026-07-28`:2, `2026-07-30`:5, `2026-06-30..2026-07-29`:1 | `200`:52 |
| `sycm.taobao.com` | `/flow/overview/live/shopFlowSourceTop/v4.json` | `GET` | 10 | `2026-07-30`:10 | `200`:10 |
| `sycm.taobao.com` | `/cc/recommend/analysis/item/material/list.json` | `GET` | 10 | `2026-07-29`:10 | `200`:10 |
| `sycm.taobao.com` | `/ipoll/live/summary/getOfflineTrend.json` | `GET` | 8 | `2026-07-29`:8 | `200`:8 |
| `sycm.taobao.com` | `/portal/month/trend.json` | `GET` | 5 | `2026-07-29`:5 | `200`:5 |
| `sycm.taobao.com` | `/portal/month/overview.json` | `GET` | 5 | `2026-07-29`:5 | `200`:5 |
| `sycm.taobao.com` | `/portal/level/info/v3.json` | `GET` | 5 | `2026-07-29`:5 | `200`:5 |
| `sycm.taobao.com` | `/portal/level/info/v3.json` | `POST` | 5 | `2026-07-29`:5 | `200`:5 |
| `sycm.taobao.com` | `/csp/api/user/special/upa/list.json` | `GET` | 4 | `20260729`:4 | `200`:4 |
| `sycm.taobao.com` | `/csp/api/core/monitor/rank/list` | `GET` | 4 | `20260729`:3, `20260728`:1 | `200`:4 |
| `sycm.taobao.com` | `/csp/api/core/monitor/competition/self` | `GET` | 4 | `20260729`:3, `20260728`:1 | `200`:4 |
| `sycm.taobao.com` | `/csp/api/core/monitor/competition/list` | `GET` | 4 | `20260729`:3, `20260728`:1 | `200`:4 |
| `sycm.taobao.com` | `/portal/profile/trip/obj/list.json` | `GET` | 6 | `2026-07-20..2026-07-26`:3, `2026-07-29`:3 | `200`:6 |
| `sycm.taobao.com` | `/xsite/tbFlow/item/list.json` | `GET` | 3 | `2026-07-28`:3 | `200`:3 |
| `sycm.taobao.com` | `/mc/mq/mkt/keyword/rank/pro.json` | `GET` | 3 | `2026-07-29`:3 | `200`:3 |
| `sycm.taobao.com` | `/csp/api/shop/sale/summary/summary.json` | `GET` | 3 | `20260729`:3 | `200`:3 |
| `sycm.taobao.com` | `/csp/api/shop/sale/summary/list.json` | `GET` | 3 | `20260729`:3 | `200`:3 |
| `sycm.taobao.com` | `/cc/item/view/top.json` | `GET` | 3 | `2026-07-29`:2, `2026-07-28`:1 | `200`:3 |
| `sycm.taobao.com` | `/portal/profile/trip/overview/compare.json` | `GET` | 3 | `2026-07-20..2026-07-26`:1, `2026-07-29`:2 | `200`:3 |
| `sycm.taobao.com` | `/portal/profile/trip/overview.json` | `GET` | 3 | `2026-07-20..2026-07-26`:1, `2026-07-29`:2 | `200`:3 |
| `sycm.taobao.com` | `/csp/api/refund/item/view/top.json` | `GET` | 3 | `2026-06-30..2026-07-29`:1, `2026-07-29`:1, `2026-07-28`:1 | `200`:3 |
| `sycm.taobao.com` | `/portal/board/grow/factor/trend.json` | `GET` | 2 | `2026-07-29`:2 | `200`:2 |
| `sycm.taobao.com` | `/portal/board/grow/factor/overview.json` | `GET` | 2 | `2026-07-29`:2 | `200`:2 |
| `sycm.taobao.com` | `/flow/shop/source/tree/platform/support.json` | `GET` | 2 | `2026-07-29`:2 | `200`:2 |
| `sycm.taobao.com` | `/flow/new/live/guide/trend/overview.json` | `GET` | 2 | `2026-07-30`:2 | `200`:2 |
| `sycm.taobao.com` | `/flow/new/live/guide/trend.json` | `GET` | 2 | `2026-07-30`:2 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/user/special/upa/summary.json` | `GET` | 2 | `20260729`:2 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/user/sale/summary/summary.json` | `GET` | 2 | `20260729`:2 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/user/sale/summary/list.json` | `GET` | 2 | `20260729`:2 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/shop/sale/summary/chart.json` | `GET` | 2 | `20260729`:2 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/getAccountId/top5.json` | `GET` | 2 | `2026-07-29`:2 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/effective/Reception/detail/list` | `GET` | 2 | `20260729`:2 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/core/monitor/overview/list` | `GET` | 2 | `20260729`:1, `20260728`:1 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/core/monitor/overview/layer.json` | `GET` | 2 | `20260729`:1, `20260728`:1 | `-1`:1, `200`:1 |
| `sycm.taobao.com` | `/csp/api/core/monitor/operator/tool.json` | `GET` | 2 | `20260729`:1, `20260728`:1 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/core/monitor/list` | `GET` | 2 | `20260729`:1, `20260728`:1 | `200`:2 |
| `sycm.taobao.com` | `/csp/api/core/monitor/diagnoise/advice.json` | `GET` | 2 | `20260729`:1, `20260728`:1 | `200`:2 |
| `sycm.taobao.com` | `/cc/item/crowd/acquisition.json` | `GET` | 2 | `2026-07-28`:2 | `200`:2 |
| `helpcenter.taobao.com` | `/servicehall/widget/guessV2` | `GET` | 27 | `2026-07-29`:1 | `200`:27 |
| `sycm.taobao.com` | `/mc/api/rfdAnalysis/mkt/slrType/list.json` | `GET` | 4 | `2026-07-23..2026-07-29`:3, `2026-07-28`:1 | `200`:4 |

## Contract Details

### `/portal/coreIndex/new/overview/v3.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `1`
- Daily calls: `1`
- Statuses: `{"200": 1}`
- Business dates: `{"2026-07-29": 1}`
- Sample params: `{"_": "1785398110348", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "needCycleCrc": "true", "token": "<present len=9 sha10=8507c4adb2>"}`
- Sample headers: `{"Onetrace-Card-Id": "pc新首页|数据概览", "Sycm-Referer": "/portal/home.htm", "bx-ua": "<present len=91 sha10=e4184fcda2>", "bx-v": "2.5.37"}`
- Response candidate files: `10`
- JSON-like response candidate files: `6`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-103-res-extract-body.reqable`, `1785398097407516-712-93-res-extract-body.reqable`, `1785391823374554-419-87-res-extract-body.reqable`, `1785391823374554-419-97-res-extract-body.reqable`

### `/portal/coreIndex/new/trend/v3.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `1`
- Daily calls: `1`
- Statuses: `{"200": 1}`
- Business dates: `{"2026-07-29": 1}`
- Sample params: `{"_": "1785398110348", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "token": "<present len=9 sha10=8507c4adb2>"}`
- Sample headers: `{"Onetrace-Card-Id": "pc新首页|数据概览", "Sycm-Referer": "/portal/home.htm", "bx-ua": "<present len=91 sha10=49c09d6ba6>", "bx-v": "2.5.37"}`
- Response candidate files: `10`
- JSON-like response candidate files: `6`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-103-res-extract-body.reqable`, `1785398097407516-712-93-res-extract-body.reqable`, `1785391823374554-419-87-res-extract-body.reqable`, `1785391823374554-419-97-res-extract-body.reqable`

### `/portal/coreIndex/new/getTableData/v3.json`

- Host: `unknown`
- Method: `unknown`
- Observed calls: `0`
- Daily calls: `0`
- Statuses: `{}`
- Business dates: `{}`
- Sample params: `{}`
- Sample headers: `{}`
- Response candidate files: `6`
- JSON-like response candidate files: `3`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-103-res-extract-body.reqable`, `1785391823374554-419-97-res-extract-body.reqable`, `1785391627101051-137-37-res-extract-body.reqable`, `1785398099741551-725-1-res-extract-body.reqable`

### `/cc/item/view/top.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `3`
- Daily calls: `3`
- Statuses: `{"200": 3}`
- Business dates: `{"2026-07-28": 1, "2026-07-29": 2}`
- Sample params: `{"_": "1785398331284", "cateId": "", "cateLevel": "", "compareType": "cycle", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "device": "0", "follow": "false", "indexCode": "payAmt,subPayOrdAmt,sucRefundAmt,payItmCnt,subPayOrdItmQty,payByrCnt,payRate,newPayByrCnt,payOldByrCnt,olderPayAmt,juPayAmt,mtdPayAmt,mtdPayItmCnt,ytdPayAmt,itemStatus,itemCartCnt,itemCartByrCnt,itemCltByrCnt,visitCartRate,visitCltRate,itmUv,itmPv,itmStayTime,itmBounceRate,seGuideUv,seGuidePayByrCnt,seGuidePayRate,uvAvgValue,starLevel001,itemUnitPrice1,fCharge,pDROI", "keyword": "", "order": "desc", "orderBy": "payAmt", "page": "1", "pageSize": "10", "token": "<present len=9 sha10=8507c4adb2>"}`
- Sample headers: `{"Onetrace-Card-Id": "sycm-cc-item-rank./cc/item_rank|拆分视角表格", "Sycm-Referer": "/cc/item_rank", "bx-ua": "<present len=91 sha10=3057a60a13>", "bx-v": "2.5.37"}`
- Response candidate files: `5`
- JSON-like response candidate files: `0`
- Response candidate samples: `1785398099741551-725-1-res-extract-body.reqable`, `1785398098843579-722-1-res-extract-body.reqable`, `1785398098843579-722-91-res-extract-body.reqable`, `1785391612372919-79-5-res-extract-body.reqable`

### `/flow/v5/shop/source/tree/v4.json`

- Host: `unknown`
- Method: `unknown`
- Observed calls: `0`
- Daily calls: `0`
- Statuses: `{}`
- Business dates: `{}`
- Sample params: `{}`
- Sample headers: `{}`
- Response candidate files: `2`
- JSON-like response candidate files: `0`
- Response candidate samples: `1785398098843579-722-49-res-extract-body.reqable`, `1785398098843579-722-59-res-extract-body.reqable`

### `/domain/oneQuery.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `52`
- Daily calls: `51`
- Statuses: `{"200": 52}`
- Business dates: `{"2026-06-30..2026-07-29": 1, "2026-07-28": 2, "2026-07-29": 44, "2026-07-30": 5}`
- Sample params: `{"_": "1785398296443", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "device": "0", "domainCode": "tao.shop.customer.overview", "indexCodes": "statDate,repurchaseTop1ItemId,paylosByrCnt,repurchaseTop1CustomerCnt,repurchaseTop2CustomerCnt,repurchaseTop3CustomerCnt,revisitTop4ItemId,revisitTop5ItemId,revisitTop1CustomerCnt,revisitTop2CustomerCnt,revisitTop3CustomerCnt,revisitTop4CustomerCnt,revisitTop5CustomerCnt,repurchaseTop2ItemId,repurchaseTop3ItemId,repurchaseTopItem,repurchaseRegularCustomerCnt,repeatByrRate6m,repurchaseCycleRivalGood,repurchaseCycleRivalAvg,repeatByrRate1m,repeatByrRate3m,payMordCnt,revisitDays3m,revisitRegularCustomerCnt,revisitPayOrdAmt,revisitTop1ItemId,revisitTop2ItemId,revisitTop3ItemId,revisitTopItem,repurchasePayOrdAmt,regularCustomerCnt,regularCustomerPayOrdAmt,repurchasePayPct,repurchaseRepeatOrdCnt,revisitPayPct,avgRevisitDays,regularCustomerPayPct,regularCustomerRatio,revisitCustomerRatio,repurchaseCustomerRatio,regularCustomerRatioAvgGood,revisitCustomerRatioAvgGood,repurchaseCustomerRatioAvgGood,hasPurchasedCustomerCnt,revisitPaylosTopItem,repurchasePaylosTopItem,regularPaylosTopItem", "needCycleCrc": "true", "showType": "overview", "token": "<present len=9 sha10=8507c4adb2>"}`
- Sample headers: `{"Onetrace-Card-Id": "已购客户|客户构成", "Sycm-Referer": "/cc/customer/regular", "bx-v": "2.5.37"}`
- Response candidate files: `45`
- JSON-like response candidate files: `24`
- Response shape preview: `$:object`, `code:number`, `data:object`, `message:string`, `data.id:number`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-113-res-extract-body.reqable`, `1785398097407516-712-565-res-extract-body.reqable`, `1785398097407516-712-567-res-extract-body.reqable`, `1785398097407516-712-569-res-extract-body.reqable`

### `/extend/api/tbhjActivityDataQuery.json`

- Host: `unknown`
- Method: `unknown`
- Observed calls: `0`
- Daily calls: `0`
- Statuses: `{}`
- Business dates: `{}`
- Sample params: `{}`
- Sample headers: `{}`
- Response candidate files: `1`
- JSON-like response candidate files: `0`
- Response candidate samples: `1785398098843579-722-183-res-extract-body.reqable`

### `/report/query.json`

- Host: `unknown`
- Method: `unknown`
- Observed calls: `0`
- Daily calls: `0`
- Statuses: `{}`
- Business dates: `{}`
- Sample params: `{}`
- Sample headers: `{}`
- Response candidate files: `1`
- JSON-like response candidate files: `0`
- Response candidate samples: `1785398225145492-885-19-res-extract-body.reqable`

### `/portal/month/overview.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `5`
- Daily calls: `5`
- Statuses: `{"200": 5}`
- Business dates: `{"2026-07-29": 5}`
- Sample params: `{"_": "1785391648624", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "sellerType": "online", "token": "<present len=9 sha10=32147a7ae3>"}`
- Sample headers: `{"Onetrace-Card-Id": "pc新首页|店铺概况", "Sycm-Referer": "/portal/home.htm"}`
- Response candidate files: `3`
- JSON-like response candidate files: `3`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-113-res-extract-body.reqable`, `1785391823374554-419-107-res-extract-body.reqable`, `1785391627101051-137-47-res-extract-body.reqable`

### `/portal/month/trend.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `5`
- Daily calls: `5`
- Statuses: `{"200": 5}`
- Business dates: `{"2026-07-29": 5}`
- Sample params: `{"_": "1785391648624", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "sellerType": "online", "token": "<present len=9 sha10=32147a7ae3>"}`
- Sample headers: `{"Onetrace-Card-Id": "pc新首页|店铺概况", "Sycm-Referer": "/portal/home.htm"}`
- Response candidate files: `4`
- JSON-like response candidate files: `3`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-113-res-extract-body.reqable`, `1785391823374554-419-107-res-extract-body.reqable`, `1785391627101051-137-47-res-extract-body.reqable`, `1785391623086730-121-7-res-extract-body.reqable`

### `/portal/level/info/v3.json`

- Host: `sycm.taobao.com`
- Method: `POST`
- Observed calls: `5`
- Daily calls: `5`
- Statuses: `{"200": 5}`
- Business dates: `{"2026-07-29": 5}`
- Sample params: `{"_": "1785391648624", "body": "dateType=day", "dateRange": "2026-07-29|2026-07-29", "token": "<present len=9 sha10=32147a7ae3>"}`
- Sample headers: `{"Accept": "application/json, text/plain", "Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "Onetrace-Card-Id": "pc新首页|店铺概况", "Sycm-Referer": "/portal/home.htm"}`
- Response candidate files: `6`
- JSON-like response candidate files: `6`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-113-res-extract-body.reqable`, `1785398097407516-712-93-res-extract-body.reqable`, `1785391823374554-419-107-res-extract-body.reqable`, `1785391823374554-419-87-res-extract-body.reqable`

### `/portal/board/grow/factor/overview.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `2`
- Daily calls: `2`
- Statuses: `{"200": 2}`
- Business dates: `{"2026-07-29": 2}`
- Sample params: `{"_": "1785391650454", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "device": "2", "token": "<present len=9 sha10=32147a7ae3>"}`
- Sample headers: `{"Onetrace-Card-Id": "pc新首页|增长因子-增长因子", "Sycm-Referer": "/portal/home.htm"}`
- Response candidate files: `7`
- JSON-like response candidate files: `3`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-91-res-extract-body.reqable`, `1785391823374554-419-85-res-extract-body.reqable`, `1785391627101051-137-25-res-extract-body.reqable`, `1785398099741551-725-1-res-extract-body.reqable`

### `/portal/board/grow/factor/trend.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `2`
- Daily calls: `2`
- Statuses: `{"200": 2}`
- Business dates: `{"2026-07-29": 2}`
- Sample params: `{"_": "1785391650454", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "token": "<present len=9 sha10=32147a7ae3>"}`
- Sample headers: `{"Onetrace-Card-Id": "pc新首页|增长因子-增长因子", "Sycm-Referer": "/portal/home.htm"}`
- Response candidate files: `7`
- JSON-like response candidate files: `3`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-91-res-extract-body.reqable`, `1785391823374554-419-85-res-extract-body.reqable`, `1785391627101051-137-25-res-extract-body.reqable`, `1785398099741551-725-1-res-extract-body.reqable`

### `/portal/board/grow/factor/promo/top.json`

- Host: `sycm.taobao.com`
- Method: `GET`
- Observed calls: `1`
- Daily calls: `1`
- Statuses: `{"200": 1}`
- Business dates: `{"2026-07-29": 1}`
- Sample params: `{"_": "1785391650539", "dateRange": "2026-07-29|2026-07-29", "dateType": "day", "order": "desc", "orderBy": "pSpend", "page": "1", "pageSize": "5", "token": "<present len=9 sha10=32147a7ae3>"}`
- Sample headers: `{"Onetrace-Card-Id": "pc新首页|增长因子-增长因子", "Sycm-Referer": "/portal/home.htm"}`
- Response candidate files: `3`
- JSON-like response candidate files: `3`
- Response shape preview: `$:object`, `code:number`, `data:object`, `data.id:number`, `message:string`, `data.crowds:array`, `data.location:string`, `data.modifier:string`, `data.packages:array`, `data.pageCode:string`
- Response candidate samples: `1785398097407516-712-91-res-extract-body.reqable`, `1785391823374554-419-85-res-extract-body.reqable`, `1785391627101051-137-25-res-extract-body.reqable`


## Worker Implications

- Good first live-contract candidates now include `/portal/coreIndex/new/overview/v3.json`, `/portal/coreIndex/new/trend/v3.json`, `/cc/item/view/top.json`, and member `/domain/oneQuery.json` variants for `2026-07-29`.
- `/report/query.json`, `/extend/api/tbhjActivityDataQuery.json`, and `/flow/v5/shop/source/tree/v4.json` still need live MCP records or explicit exported API pairs; the current local files only show path/body evidence.
- The importer should treat telemetry-derived params as request contracts, then require one exact live response sample before enabling writes.
