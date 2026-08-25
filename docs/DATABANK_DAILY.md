# 天猫品牌数据银行日报采集

已接入品牌数据银行首页两套稳定日报接口。老首页接口使用 `dateType=day`、`ds=YYYYMMDD`、`dateRange=YYYY-MM-DD|YYYY-MM-DD`；新版首页接口使用 `dateType=d`、`ds=YYYYMMDD`、`xcatId=-999`：

- 核心资产：消费者资产、AIPL 各层体量、品牌成交金额、会员成交贡献、关系加深率、蓄水购买比、消费者价值预测；
- AIPL 分层：认知、兴趣、购买、忠诚、机会人群的体量和成交表现；
- 成交拆解：品类、渠道、触点的成交金额、成交人数、客单价；
- AIPL 资产占比：认知、兴趣、购买、忠诚人群占比；
- AIPL 对比分析：品牌自身与行业对比人群的消费者数、浏览、加购收藏、成交人数/金额、转化率、客单价及成交贡献占比。
- 新版经营面板：资产、活跃、成交人群，AIPL 增减/加深/维持/变浅/流失，成交金额、新老客人数、客单价、触达次数和活跃时长；
- 新版增长策略：触达人数、人均触达次数、人均停留时长、点击率、转化率，以及品牌值、行业中位值和日趋势。

新版首页已验证接口：

- `/homepage/queryPanel`
- `/homepage/queryPanelDetail`：`active`、`aipl`、`deal`
- `/homepage/queryGrowthStrategy`
- `/homepage/queryGrowthStrategyMap`：`touch`、`avgTouch`、`activeTime`、`ctr`、`cvr`

所有请求都通过 `/api/paasapi?path=...` 网关发送。接口返回 `null` 的指标保留在原始响应中，但不写入指标表，避免用空值污染日报。

运行：

```powershell
$env:DATABANK_COOKIE = "..."
python backend/scripts/backfill_databank_daily.py `
  --start yesterday --end yesterday `
  --session-source env `
  --cookie-env DATABANK_COOKIE `
  --database-path artifacts/local/echomerch_local.sqlite3
```

也可以让 worker 从已登录的本地 Chrome 临时读取会话：

```powershell
python backend/scripts/backfill_databank_daily.py `
  --start yesterday --end yesterday `
  --session-source drissionpage `
  --browser-port 9222
```

每日总编排已增加数据集名 `databank_daily`：

```powershell
python backend/scripts/collect_daily.py --datasets databank_daily
```

落库表包括 `brands`、`brand_asset_daily_overviews`、`brand_asset_daily_stages`、`brand_asset_daily_dimensions`、`brand_asset_daily_metrics`。其中 `brand_asset_daily_metrics` 用长表保存首页子模块中无法合理塞进宽表的日指标。每次同一品牌和业务日期重复执行会先替换当天快照，不产生重复行。

## 其他子页面评估

当前适合每日采集的是老首页 7 个接口和新版首页 10 个接口。资产分布/经营效果页面如果后续确认其请求直接接受日粒度参数，也可按日接入。

下列页面不混入自然日报：

- 行业排名：`/ranking/monthly/list` 等接口是月粒度；
- 内容分析：`/duplo/v1/report/.../55` 为异步报告；
- 老客/自定义分析：`customizeReport`、`crowddiff` 为异步任务；
- 一方人群：`/v1/landscape/pageQuery` 是上传数据管理；
- 活动复盘：属于事件型区间数据，应按活动单独落库。
