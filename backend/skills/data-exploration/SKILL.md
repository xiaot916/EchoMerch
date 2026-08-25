---
name: data-exploration
description: Use for open-ended ecommerce data questions that do not yet identify a single business diagnosis.
---

# 通用数据探索

先通过 `data.catalog` 确认数据集的粒度、维度和指标，再通过 `data.query` 查询。只能使用目录中的字段，不拼接 SQL。

结果必须保留日期范围、行数、覆盖状态和物理表证据。缺失日期不得当作 0；平台确认无数据要单独标记。探索结果只能描述事实，涉及预算、商品、流量或客户动作时转交对应业务 Skill。
