# 生意参谋新客折扣效果概览

## 接口

- 路径：`/s_content/brandnewdiscount/overview.json`
- 日期参数：`dateType=day`
- 日期范围：`dateRange=YYYY-MM-DD|YYYY-MM-DD`
- 当前渠道：`channelId=450`
- 本地接口标识：`sycm.s_content.brandnewdiscount.overview`

## 业务表

表名：`store_daily_new_customer_discount_overviews`

主键：

- `店铺ID`
- `业务日期`

业务表不保存 Cookie、Token、原始 JSON、证据 ID、抓取时间或更新时间。
原始响应文件只在独立的 `raw_response_artifacts` 表中登记。

## 字段映射

| 接口字段 | 中文字段 | 2026-08-01 |
| --- | --- | ---: |
| `uv.value` | 店铺访客数 | 38654 |
| `guideNewUv.value` | 商品新访客数 | 4571 |
| `guideNewPayByrCnt.value` | 新客支付人数 | 213 |
| `guideNewPayByrCntRatio.value` | 新客支付人数占比 | 0.19906542056074766 |
| `guideNewPayAmt.value` | 新客支付金额 | 8248.88 |
| `guideNewPayAmtRatio.value` | 新客支付金额占比 | 0.4087347323043382 |
| `guideNewPayRate.value` | 新客支付转化率 | 0.04659811857361627 |
| `newbuyerPayByrCnt.value` | 店铺新客支付人数 | 1070 |
| `newbuyerPayAmt.value` | 店铺新客支付金额 | 20181.50 |
| `shopNewbuyerPayRate.value` | 店铺新客支付转化率 | 0.027681481864748798 |

比例字段在数据库中保存接口原值。页面展示时再乘以 100 并保留两位小数，
例如 `0.19906542056074766` 展示为 `19.91%`。

## 不进入业务表的字段

- `statDate`：用于校验响应日期是否与请求日期一致。
- `channelId`：当前为固定请求维度 `450`，由接口配置管理。
- `cycleCrc`：较前一日的环比结果，可通过相邻业务日期重新计算。
- `traceId`：仅用于请求排查。

## 导入命令

```powershell
python backend\scripts\ingest_sycm_new_customer_discount.py `
  --response-file artifacts\local\raw_responses\sycm_new_customer_discount_20260801.json `
  --day 2026-08-01 `
  --database-path artifacts\local\echomerch_local.sqlite3
```
