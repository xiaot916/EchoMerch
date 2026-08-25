# SYCM Overview Ingestion

The first controlled response test used the daily overview endpoint:

```text
/portal/coreIndex/new/overview/v3.json
```

The request date tested was `2026-08-01`. The response shape is:

```text
content
  code
  data
    self
    rivalAvg   # source-only; ignored by local BI ingestion
    rivalGood  # source-only; ignored by local BI ingestion
    supportQueryByLy
  message
  traceId
```

## Identity Mapping

- `platform_id`: local numeric platform ID, currently `1`
- `platform_name`: `天猫`
- `platform_subject_id`: `content.data.self.userId.value`, currently `2200573698992`
- `store_id`: local numeric store ID, currently `1`
- `store_name`: supplied by the operator, currently `碧芭宝贝旗舰店`
- `business_day`: request `dateRange` day, because `self.statDate.value` was empty

The endpoint exposes `userId`, not a separately named `shopId`. The current
database therefore stores this field as `平台主体ID`; the API still exposes the
legacy-compatible key `platform_store_id` and records that
assumption as an ingestion warning. A later shop metadata endpoint can replace
the mapping without changing the warehouse primary key shape.

The BI-facing daily view also exposes the same value as `平台店铺ID` so database
inspection matches common business language.

## Canonical Metrics

The first daily overview row maps:

- `payAmt.value` -> `paid_amount`
- `uv.value` -> `visitors`
- `payByrCnt.value` -> `buyers`
- `payRate.value` -> `conversion_rate`
- `admCostFamtQzt.value` -> `promotion_cost`
- `payOrdCnt.value` -> `paid_orders`
- `payItmCnt.value` -> `paid_items`
- `pv.value` -> `page_views`
- `cartCnt.value` -> `cart_count`
- `cartByrCnt.value` -> `cart_buyers`
- `p4pExpendAmt.value` -> `p4p_spend`
- `tkExpendAmt.value` -> `taoke_spend`
- `zzExpendAmt.value` -> `zhizuan_spend`

All other `self` fields are retained in `store_daily_metrics` with their original
scope and value envelope for later mapping.

No request Cookie, Token, or signature is persisted by the ingestion script.
