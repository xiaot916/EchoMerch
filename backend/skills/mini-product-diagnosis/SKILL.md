---
name: mini-product-diagnosis
description: Use when the user asks about MINI, mini, 尝鲜装 or other trial-size products and needs store product, promotion, VOC and U先 evidence joined by product ID.
---

# MINI/尝鲜商品联动诊断

1. 先从当前店铺商品主档标题、类型、属性和定位识别 MINI/尝鲜商品，保留商品 ID；名称命中是商品身份证据，不把未调用某个业务表误报成没有商品。
2. 以商品 ID 联动商品排行、推广商品、评价、问大家、U先派样和 U先复购；每个数据域分别标记已覆盖、平台无该商品数据或尚未采集。
3. U先复购的 30/90/365 日字段按最新业务日滚动快照读取，不能跨日求和；没有严格对应的派样 cohort 分母时不计算回购率。
4. 评价等级、文本问题和问大家未回答分开解释。它们与成交只能做描述性关联，动作必须落到商品、详情/FAQ、客服、投放或回购权益，并写验证指标和观察窗口。
