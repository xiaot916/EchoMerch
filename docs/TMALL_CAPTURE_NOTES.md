# 生意参谋抓包分析记录

> 当前阶段不使用浏览器自动化。你提供抓包结果后，只做离线接口与字段分析。

## 已观察首页模块

- 顶部业务导航：首页、交易、流量、客户、商品、营销、服务、内容、市场、自助分析、业务专区。
- 首页核心模块：数据概览、增长因子、数据看板、生意拆解、退款概况、店铺资产、客户概况、竞争动态、直播内容、智能诊断、客户旅程。
- 关键指标：支付金额、净支付金额、访客数、支付买家数、支付转化率、退款金额、金额退款率、加购人数。

## 已观察接口形态

- 页面壳资源：`g.alicdn.com/dt/sycm-micro-v2/...`
- 权限与菜单：`/oneauth/api/permission.json`、`/oneauth/api/getMenuV2.json`
- 首页数据：`/portal/month/overview.json`、`/portal/month/trend.json`、`/portal/level/info/v3.json`
- 通用查询：`/domain/oneQuery.json`
- 活动/营销：`/datawar/activityConfig/getActivityListBy.json`、`/portal/coupon/show.json`

## 后续你给我的材料格式

每个接口尽量包含：

- URL 路径和 Query 参数，敏感值用 `<redacted>`。
- Method、Content-Type、响应状态码。
- Request payload 的字段名和值类型，敏感字段脱敏。
- Response JSON 的顶层结构和关键字段样例，订单号、账号、Token、签名全部脱敏。
- 页面上对应的模块或按钮名称。

## 禁止写入文档的内容

- Cookie、Token、`sign`、`bx-*`、`umid`、鉴权头、二维码、账号 ID 明文。
- 个人身份信息、真实收货信息、订单明细原文。
- 可直接复用的自动化绕检策略。

## 接入判断

- 只读指标接口优先映射到 `analytics` 模块。
- 需要动作的接口先进入 `tasks` 设计文档，不直接接按钮。
- 高频接口先考虑落缓存表，避免页面每次刷新都打平台接口。
