---
name: data-quality-audit
description: Use when the user asks which ecommerce data is missing or whether a period is complete.
---

# 数据完整性审计

调用 `data.coverage` 返回所有相关数据集的状态。将“未采集日期”“表不存在/字段不存在”和“平台确认无数据”分开报告。只有前两类进入补采队列；平台无数据保留为业务事实，不重复补采。

优先补齐店铺日概览、商品排行、流量来源，再补推广、客户、会员、直播等下游数据。补采完成后重新审计，只有覆盖完整或平台无数据的模块才可进入周期环比结论。
