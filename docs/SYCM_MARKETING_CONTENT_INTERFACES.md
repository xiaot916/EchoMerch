# 生意参谋营销与内容接口入库

这批接口只负责解析已抓取的响应并写入本地 SQLite。业务表仅保留：

- `店铺ID`
- `业务日期`
- 已确认的中文业务指标

原始响应文件、接口标识和解析器版本统一记录在
`raw_response_artifacts`，不进入业务事实表。

## 购物金

- 接口：`/xsite/rc/getRcOverall.json`
- 样本日期：`2026-08-01`
- 响应文件：`artifacts/local/raw_responses/sycm_shopping_gold_20260801.json`
- 业务表：`store_daily_shopping_gold_overviews`

已解析字段：

`人均充值金额`、`充值总金额`、`支付买家数`、`充值件数`、
`充值成功退款金额`、`支付金额`、`客单价`、`充值本金金额`、
`充值买家数`、`充值转化率`、`商品访客数`、`充值子订单数`。

## 百亿补贴

- 接口：`/mc/bybt/sellerData/businessOverview/statistics.json`
- 样本日期：`2026-08-02`
- 响应文件：`artifacts/local/raw_responses/sycm_bybt_20260802.json`
- 业务表：`store_daily_bybt_overviews`

已解析字段：

`百补访客数`、`百补支付买家数`、`百补在线商品数量`、
`百补支付金额`、`百补子订单数`、`百补支付成交件数`。

不会把数据概览或其他推广接口中的钻展、直通车等字段混入本表。

## 内容概览

- MTop API：`mtop.taobao.guangguang.creator.gateway.oneservice.kind.list`
- 场景：`contentAssertKeyIndicatorsV1`
- 样本日期：`2026-08-02`
- 响应文件：`artifacts/local/raw_responses/mtop_content_overview_20260802.json`
- 业务表：`store_daily_content_overviews`

当前响应中的 29 个指标已全部解析，包括：

`内容查看人数`、`内容互动人数`、`商品点击人数`、`商品加购人数`、
`种草成交人数`、`种草成交金额`、`种草成交金额占比全店`、
`查看内容数`、`曝光人数`、`点击人数`、`曝光UV点击率`等。

比例字段在数据库中保留接口原始小数，例如 `0.085365...`，
展示为百分比时再乘以 100。

## 淘金币

- MTop API：`mtop.hd.marketing.seller.home`
- 样本日期：`2026-08-01`
- 业务表：`store_daily_taojinbi_overviews`

该接口需要分别请求两个场景：

- `shopGeneralInfo`：实时金币余额及概览指标
- `shopDetailedInfo`：订单、成交、流量、补贴和金币收支明细

两份响应可以任意顺序入库，程序会按 `店铺ID + 业务日期` 合并，
不会用另一份响应中的空值覆盖已经存在的指标。

样本文件：

- `artifacts/local/raw_responses/mtop_taojinbi_shopGeneralInfo_20260801.json`
- `artifacts/local/raw_responses/mtop_taojinbi_shopDetailedInfo_20260801.json`

## MTop 签名

实现位置：`backend/app/warehouse/mtop_sign.py`

签名公式：

```text
token = _m_h5_tk 按第一个下划线分割后的第一段
sign_source = token + "&" + timestamp + "&" + appKey + "&" + data_json
sign = md5(sign_source)
```

当前 `appKey` 为 `12574478`。

`data_json` 必须是最终放进查询参数 `data` 的原始 JSON 字符串。
不能在签名完成后再改变字段顺序、空格、布尔值格式或嵌套字符串。

已使用 `2026-08-01` 淘金币请求校验：

```text
timestamp = 1785833317288
计算结果 = 3687c75c458c556076c9c71134dcaece
请求 sign = 3687c75c458c556076c9c71134dcaece
```

## 入库命令

```powershell
python backend\scripts\ingest_sycm_shopping_gold.py `
  --response-file artifacts\local\raw_responses\sycm_shopping_gold_20260801.json `
  --day 2026-08-01

python backend\scripts\ingest_sycm_bybt.py `
  --response-file artifacts\local\raw_responses\sycm_bybt_20260802.json `
  --day 2026-08-02

python backend\scripts\ingest_mtop_content_overview.py `
  --response-file artifacts\local\raw_responses\mtop_content_overview_20260802.json `
  --day 2026-08-02

python backend\scripts\ingest_mtop_taojinbi.py `
  --response-file artifacts\local\raw_responses\mtop_taojinbi_shopGeneralInfo_20260801.json `
  --day 2026-08-01

python backend\scripts\ingest_mtop_taojinbi.py `
  --response-file artifacts\local\raw_responses\mtop_taojinbi_shopDetailedInfo_20260801.json `
  --day 2026-08-01
```
