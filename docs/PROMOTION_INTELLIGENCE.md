# 推广智能模块（Promotion Intelligence）

> 增量扩展，不改现有只读边界。本模块复用已有 `store_daily_promotion_*` 五张表 + `modules.operations` 的安全模型，新增「诊断 → 策略 → 执行 → 回滚 → 复盘」闭环。

## 1. 模块定位

```
┌─────────────────────────────────────────────────────────────────┐
│  数据底座（已有）                                                │
│  store_daily_promotion_campaigns / adgroups / crowds /          │
│  bidwords / items / sycm_overview / sycm_traffic_source         │
└──────────────────────┬──────────────────────────────────────────┘
                       │ 只读
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  智能诊断（新增）  promotion_intel/diagnosis.py                  │
│  · 保本ROI分层：词价 × 溢价 × 分时折扣 × 地域溢价 全因子          │
│  · 渠道 × 出价方式（custom_bid/smart_bid/roi_control）矩阵      │
│  · 人群绑定健康度：报表 ∪ 绑定列表 双源对账（识破裸投/智能定向）  │
│  · 词包花费占比：手动词 vs 流量智选 vs 宝贝词包                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ 诊断结果
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  策略引擎（新增）  promotion_intel/strategy.py                   │
│  · 词价 × 溢价 建议：保本CPC = 单均 × 毛利率 × CVR              │
│  · 溢价公式：建议% = (1+当前%)×目标CPC/实际CPC − 1（clamp 5~500）│
│  · 人群层级：达摩盘包 → 渠道同步门槛（49/74/33/113/54/55）      │
│  · 预算分配：按 ROI 弹性 + 保本线 加权                            │
│  · 输出 OptimizationPlan（可序列化、可回放、可回滚）             │
└──────────────────────┬──────────────────────────────────────────┘
                       │ OptimizationPlan
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  执行通道（新增）  promotion_intel/executor.py                   │
│  · 复用 modules.operations 的 preview/confirm/audit 三态         │
│  · 写操作默认 dry-run；allow_write 才落盘                        │
│  · 每个 plan 绑定 rollback_snapshot（JSON）                     │
│  · 审计日志：操作人 / 时间 / 前后值 / 回滚状态                    │
│  · 外部通道：onebp 接口（onebp-wuji-api 技能）+ 达摩盘 API       │
│    （dmp-crowd-ops 技能）+ UI 兜底（手工清单）                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ 执行完成
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  复盘追踪（新增）  promotion_intel/review.py                     │
│  · T+7 自动复盘：CVR 阈值 / ROI 转正 / 预算下限 触发            │
│  · 台账：每步优化追加一行（对齐《33-优化过程记录与汇报.xlsx》）  │
│  · 效果归因：plan_id × campaign × crowd 三维度                  │
│  · 失败自动回滚：触发 rollback_snapshot 还原                    │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 数据模型（增量表）

在 `local_database.py` 追加 4 张表（沿用中文列名规范）：

| 表 | 粒度 | 用途 |
|---|---|---|
| `promotion_optimization_plans` | 一行 = 一次优化批次 | 记录 plan_id、批次名称、生成时间、生成方式（rule/ai/manual）、状态（draft/confirmed/executed/rolled_back/closed） |
| `optimization_plan_items` | 一行 = 一个操作 | plan_id、目标类型（word/crowd/campaign/budget）、目标 ID、动作（调价/调溢价/调预算/暂停/改匹配/改分时）、前值、后值、执行状态、错误信息 |
| `optimization_snapshots` | 一行 = 一次快照 | plan_id、快照 JSON（含词价+匹配+人群绑定+预算）、生成时间、是否已应用 |
| `optimization_review_runs` | 一行 = 一次复盘 | plan_id、复盘日、触发窗口（T+7）、判定结果（CVR 未过→暂停 / ROI 转正→回加 / 维持）、回滚动作 |

不破坏现有五张 `store_daily_promotion_*` 只读事实表。

## 3. 诊断规则（硬编码 + 可配置）

策略引擎内置 6 条规则，全部基于 30 日实测基线（客单 90.12 / 保本ROI 2.5 / 实际CPC 1.085 / 实际ROI 2.883 / 安全垫 15%）：

1. **词价越界**：词价 > 保本CPC × 1.3 → 下调；< 保本CPC × 0.7 → 上调（custom_bid 场景）
2. **溢价反噬**：人群溢价 > 100% 且 该人群 ROI < 保本线 → 降到 50% 或 0
3. **裸投高消耗**：crowdType=-999 占账户花费 > 50% → 拉新计划加人群包
4. **智能定向漏点**：crowdType=100 花费用 > 1 万且 ROI < 1 → 降预算 30%（无法关智能定向）
5. **词包挤压**：流量智选词包花费 > 60% 且 手动词 ROI 领先 → 压词包出价
6. **渠道门槛失配**：达摩盘包 < 10 万 推到直通车(49) → 标红「推不进」；> 2000 万 推品牌专区(33) → 标黄「超规模」

阈值、保本线、毛利率全部落 `backend/app/core/promotion_config.py`（JSON），可被 AI 决策中心覆盖。

## 4. 执行通道（三态）

```
preview（默认）  → 只打印 plan + rollback_snapshot，不写任何接口
confirm         → 写审计 + 调 executor，默认仍 dry-run 打印 onebp payload
execute         → 调 onebp_client（onebp-wuji-api）/ dmp_api（dmp-crowd-ops）
                  写操作必须带 allow_write=True + 已绑定 rollback_snapshot
```

通道白名单：

| 通道 | 来源 | 用途 | 默认 |
|---|---|---|---|
| `onebp_write` | onebp-wuji-api 技能 | 词价/溢价/预算/分时/地域/改名 | 开 |
| `dmp_write` | dmp-crowd-ops 技能 | 达摩盘建包/推渠道/改有效期 | 开 |
| `ui_manual` | 手工清单 | 智能定向关闭/display 人群挂包等后台动作 | 开 |
| `alimama_api` | 阿里妈妈官方开放 API | 兜底（无会话时） | 关 |

UI 兜底：`ui_manual` 动作渲染成《后台操作清单.xlsx》（含步骤、URL、预期结果），用户做完回勾。

## 5. 复盘闭环

`review.py` 每周一 09:30 自动跑（对齐现有「人群复盘与溢价调优」周更节奏）：

- 输入：plan_id + 复盘窗口（T+7）
- 数据：`store_daily_promotion_campaigns` 7 日切片
- 判定矩阵：

| CVR | ROI vs 保本线 | 动作 |
|---|---|---|
| < 2% | 任意 | 暂停拉新计划（止血） |
| ≥ 2% | < 保本 | 维持 7 天再判 |
| ≥ 2% | ≥ 保本 | 回加预算 25~30% |

- 台账：每行追加到《优化过程记录.xlsx》（01_优化台账 sheet，表头第 3 行）
- 回滚：触发条件 = 复盘判定为暂停 且 已执行 → 调 executor 反向操作 + 应用 snapshot

## 6. 与现有模块的关系

| 现有模块 | 关系 |
|---|---|
| `modules.operations` | 复用其 preview/confirm/audit 三态；本模块新增 `execute` 第四态（默认不启用） |
| `modules.scheduler` | 本模块的周更复盘挂在 scheduler 下，不另起 cron |
| `modules.audit` | 本模块所有 execute 写 audit 表 |
| `modules.ai` | 本模块的诊断结果 + 策略建议自动注入 AI 决策中心的 promotion skill；AI 可生成 OptimizationPlan 草稿 |
| `modules.reviews` | 评价模块的「竞品提及」「客服态度差」结论反哺策略引擎（竞品拦截/客服承接） |

## 7. 不做的事（边界）

- 不做自动出价「学习器」（只出建议，不在线调价）
- 不做跨店聚合（单店闭环）
- 不做创意/素材生成（属于另一域）
- 不破坏现有只读 API；本模块新增路由独立前缀 `/api/v1/promotion-intel`
- 不直连生产数据库；所有写走 `onebp_client` + `dmp_api` 会话通道

## 8. 文件清单

```
backend/app/modules/promotion_intel/__init__.py
backend/app/modules/promotion_intel/schemas.py       # OptimizationPlan / PlanItem / Snapshot / ReviewRun
backend/app/modules/promotion_intel/diagnosis.py     # 诊断器（6 条规则）
backend/app/modules/promotion_intel/strategy.py       # 策略引擎（保本CPC/溢价公式/预算分配）
backend/app/modules/promotion_intel/executor.py       # 三态执行器 + 通道白名单
backend/app/modules/promotion_intel/review.py         # T+7 复盘 + 台账 + 回滚
backend/app/core/promotion_config.py                  # 阈值/保本线/毛利率（可被 AI 覆盖）
backend/app/api/v1/routes/promotion_intel.py          # 新路由（只读 + preview + confirm）
frontend/src/views/PromotionsView.vue                  # 扩展：智能诊断 / 优化台账 / 复盘追踪 三面板
frontend/src/api.ts                                   # 追加 4 个 fetch 函数
backend/skills/promotion-intel/manifest.json          # 新 AI skill（供 AI 决策中心调用）
docs/promotion-intel-runbook.md                       # 运维手册（通道、回滚、复盘触发）
```
