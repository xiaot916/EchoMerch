# 生意参谋客服接口入库

## 当前状态

截至 `2026-08-04`，客服总览和客服账号明细的解析、表结构、入库方法及命令行入口已经完成。

用户提供的 `2026-08-01` 请求会话已失效：

- MTop 返回 `FAIL_SYS_SESSION_EXPIRED`
- 客服账号列表返回 `You must login system first`

因此当前只创建正式表结构，没有把截图值或模拟值写入正式本地库。拿到新的成功响应文件后，可直接执行本文末尾的入库命令。

## 客服经营总览

- MTop API：`mtop.alibaba.sycm.domain.onequery`
- `domainCode`：`tao.shop.qos.sellerkpi`
- 解析器：`backend/app/warehouse/mtop_customer_service_overview.py`
- 业务表：`store_daily_customer_service_overviews`
- 唯一键：`店铺ID + 业务日期`

业务字段映射：

| 接口字段 | 数据库字段 |
| --- | --- |
| `customerServiceGmv` | 客服销售额 |
| `customerServiceSaleCnt` | 客服销售人数 |
| `customerServiceSaleRatio` | 客服销售占比 |
| `customerServiceSalePrice` | 客服销售客单价 |
| `sucRefundAmount` | 成功退款金额 |
| `netPayAmt` | 净销售额 |
| `consultUserCnt` | 咨询人数 |
| `customerServiceRecUserCnt` | 接待人数 |
| `wwConsultPayRate` | 询单转化率 |
| `avgReplyInterval` | 平均响应时长（秒） |
| `customerAllSateRate` | 客户满意率 |
| `wwUserReplayRate` | 旺旺回复率 |
| `jtkCaseEndAvgDur` | 仅退款自主完结时长（小时） |
| `thtkCaseEndAvgDur` | 退货退款完结时长（小时） |
| `pltfHelpRate` | 平台求助率 |
| `pltfRespRate` | 平台判责率 |

兼容的时长别名：

- `rfdAvgEndTime`、`rfdOverTime` -> 仅退款自主完结时长
- `rfdGoodsAvgEndTime`、`rfdGoodsOverTime` -> 退货退款完结时长

比例字段保存接口原始小数，例如 `0.1346`，展示时再格式化为 `13.46%`。接口中的 `-` 保存为 `NULL`，不会误写成 `0`。

## 客服账号明细

- 接口：`/csp/api/user/sale/summary/list.json`
- 解析器：`backend/app/warehouse/sycm_customer_service_accounts.py`
- 业务表：`store_daily_customer_service_accounts`
- 唯一键：`店铺ID + 业务日期 + 旺旺昵称`

业务字段：

- 旺旺昵称
- 咨询人数
- 有效接待人数
- 询单人数
- 下单人数
- 下单金额
- 销售人数
- 销售额
- 销售量
- 订单量
- 个人销售额占比
- 成功退款金额
- 净销售额

解析器兼容 `data`、`list`、`records`、`result`、`rows`、`items` 等常见响应包装，并兼容已发现的多个字段别名。`汇总值`、`汇总`、`合计`、`总计` 和没有旺旺昵称的行不会入库。

同一店铺、同一业务日期重新导入时，会先删除当天旧账号明细，再一次性写入新结果，防止失效账号残留。

## 数据库边界

两张业务表只保存业务数据，不包含：

- 平台名称、店铺名称、平台主体 ID
- Cookie、Token、Sign
- 原始 JSON、来源路径、证据 ID
- 更新时间

平台和店铺信息通过 `店铺ID` 关联 `stores`、`platforms`。原始响应文件的哈希和解析记录单独保存在 `raw_response_artifacts`。

## 入库命令

```powershell
python backend\scripts\ingest_mtop_customer_service_overview.py `
  --response-file <客服总览成功响应文件> `
  --day 2026-08-01

python backend\scripts\ingest_sycm_customer_service_accounts.py `
  --response-file <客服账号明细成功响应文件> `
  --day 2026-08-01
```

两个入口都默认使用：

- 店铺名称：`碧芭宝贝旗舰店`
- 平台主体 ID：`2200573698992`
- 本地数据库：`artifacts/local/echomerch_local.sqlite3`
