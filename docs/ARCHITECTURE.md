# 家庭智能膳食管家 — 系统架构设计文档

> 版本: 2.0 | 日期: 2026-07-29 | 作者: 软件架构师

## 1. 系统定位与架构原则

### 1.1 系统定位

家庭智能膳食管家是一套面向个人/家庭的 **PWA 膳食规划与库存管理平台**。核心能力：

- **智能菜谱生成**：基于营养目标、过敏约束、价格预算、库存状态，自动生成周/长期膳食计划
- **进销存一体**：库存批次管理 + FEFO 消耗 + 临期预警 + 采购清单
- **真实菜价追踪**：当地发改委政府价 + 慢慢买电商比价兜底，取代模拟数据
- **移动端 PWA**：Vant UI 移动优先、可安装到主屏幕、离线缓存

### 1.2 架构原则

| 原则 | 含义 | 实践 |
|------|------|------|
| **适配器解耦** | 外部数据源通过统一接口接入，核心逻辑不感知具体源 | `PriceSourceAdapter` ABC，Mock / 政府价 / Ecommerce 三实现 |
| **单体优先** | 先单体后微服务——家庭用户规模不需要分布式复杂度 | FastAPI 单体、按领域分路由/服务/模型 |
| **离线可用** | PWA Service Worker + 核心数据本地缓存 | Workbox NetworkFirst(CacheFirst 静态) |
| **渐进增强** | 核心链路先跑通，再逐步替换模拟数据源、补充智能化 | PriceEngine: Mock → 政府价 → Ecommerce |
| **配置驱动** | 环境差异靠环境变量切换，不作代码级判断 | DATABASE_URL, ECOMMERCE_PROXY, PRICE_BACKFILL_DAYS |
| **防御式集成** | 外部依赖失败不影响核心功能 | 每个 PriceSource 失败 → `{}` → 上层灰标兜底 |

---

## 2. 系统全景架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端层                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ PWA (已安装)  │  │ 浏览器/WebView│  │ 系统日历 (ICS导入)   │  │
│  │ SW + manifest│  │ Vant UI 移动端│  │ 浏览器通知 (8AM)     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼──────────────────┼─────────────────────┼──────────────┘
          │                  │                     │
     ┌────▼──────────────────▼─────────────────────▼──────────────┐
     │                    Nginx 网关层                              │
     │  · 静态文件服务 (SPA)                                       │
     │  · /api/* → backend:8000 反向代理                           │
     │  · /uploads/* → backend:8000                                │
     │  · gzip 压缩、DNS resolver 动态解析                          │
     └──────────────────────────┬──────────────────────────────────┘
                                │
     ┌──────────────────────────▼──────────────────────────────────┐
     │                FastAPI 应用层 (单体)                         │
     │                                                             │
     │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
     │  │ dashboard │  │ planner  │  │inventory │  │ shopping │   │
     │  │  .router  │  │  .router │  │  .router │  │  .router │   │
     │  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
     │  ┌─────┴─────┐  ┌───┴──────┐  ┌──┴────────┐  ┌──┴──────┐  │
     │  │  prices   │  │ recipes  │  │nutrition  │  │ingred.  │  │
     │  │  .router  │  │ .router  │  │ .router   │  │.router  │  │
     │  └─────┬─────┘  └────┬─────┘  └─────┬──────┘  └────┬─────┘  │
     └────────┼─────────────┼──────────────┼──────────────┼────────┘
              │             │              │              │
     ┌────────▼─────────────▼──────────────▼──────────────▼────────┐
     │                      服务层                                  │
     │  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
     │  │recommender  │  │ price_engine │  │ gov_price_source     │  │
     │  │·generate    │  │·Adapter(ABC) │  │·discover_issues   │  │
     │  │·replace     │  │·MockPriceSrc │  │·parse_issue       │  │
     │  │·nutrition   │  │·get_source() │  │·match_products    │  │
     │  └──────┬──────┘  └──────┬───────┘  └───────┬───────────┘  │
     │  ┌──────┴──────┐  ┌──────┴───────┐  ┌──────┴───────────┐  │
     │  │ long_term   │  │ecommerce_src│  │ scheduler        │  │
     │  │·batch_plan  │  │·mmb(主)     │  │·fetch_today()    │  │
     │  │·build_ics   │  │·jd/tb(兜底) │  │·start_scheduler()│  │
     │  └─────────────┘  └──────────────┘  └──────────────────┘  │
     └──────────────────────────┬─────────────────────────────────┘
                                │
     ┌──────────────────────────▼─────────────────────────────────┐
     │                    数据层                                    │
     │  ┌─────────────────┐  ┌────────────┐  ┌─────────────────┐  │
     │  │ SQLAlchemy ORM  │  │ JSON 种子   │  │ 外部 API/爬虫    │  │
     │  │ 12 模型         │  │ingred/recipes│  │gov.cn（示例）    │  │
     │  │ SQLite / PG     │  │alias/cache  │  │manmanbuy.com    │  │
     │  └─────────────────┘  └────────────┘  └─────────────────┘  │
     └─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心子系统设计

### 3.1 菜价数据源引擎 (Price Engine)

**问题**：菜价来源从「模拟数据」逐步过渡到「多源真实数据」，且任一源失败不能影响核心功能。

**设计**：策略模式 + 适配器 + 组合

```
           PriceSourceAdapter (ABC)
           ├── fetch(ingredients, day) → dict[int,float]
           │
    ┌──────┼─────────────────────────────┐
    │      │                             │
MockPriceSource   GovPriceSource   EcommercePriceSource
  (演示)            (当地发改委)           (慢慢买→京东→淘宝)
  └── 内置算法       └── httpx+bs4+alias    └── Playwright+bs4+限流
```

**路由逻辑** (CompositePriceSource，当前实现待落地 Phase 2)：

```
对于每种食材：
  1. GovPriceSource → 命中？→ 政府真实价 ✔
  2. EcommercePriceSource → 命中？→ 电商参考价 ✔
  3. MockPriceSource → 静默兜底（仅成本估算，不展示在价格页）
```

**关键决策**：
- 每源独立缓存 (24h)，组合器只做编排
- 降级链：政府价(优先) → 电商(兜底) → 模拟(静默)
- 电商限流：最小间隔 3s + 随机抖动 + 每日预算 100
- 代理策略：`ECOMMERCE_PROXY` 环境变量控制（URL | direct | 不设）

### 3.2 智能推荐引擎 (Recommender)

**问题**：给定营养目标、预算、库存、过敏约束，生成 N 天的菜谱计划，质量要求「营养均衡 + 成本可控 + 品种多样 + 优先消耗临期食材」。

**设计**：贪心构造 + 局部随机优化

```
generate_plan:
  ┌───────────────────────────────────────┐
  │ 1. 构建 Ctx (价格快照, 库存副本, 候选) │
  │ 2. 贪心逐格填充 (每餐评分选最优)       │
  │    ├── 性价比得分 (1.0)               │
  │    ├── 营养缺口得分 (2.0)             │
  │    ├── 临期消耗奖励 (1.5)             │
  │    └── 重复惩罚 (-3.0)               │
  │ 3. 局部随机优化 (400 次迭代)           │
  │    └── 随机替换一餐 → 若总分提升则保留 │
  │ 4. 营养报告 + 不可行建议              │
  └───────────────────────────────────────┘
```

**为什么不用 ILP/整数规划？**
- 家庭场景规模小（7-90天 × 3餐 = 21-270个决策变量）
- 贪心+局部搜索在实验中得到接近最优解、秒级完成
- 代码可读可维护，家庭用户不需要最优解、需要「足够好且可解释」

### 3.3 库存管理 (Inventory Engine)

**模型**：Batch 批次管理 + FEFO 消耗 + 进销存日志

```
InventoryBatch (进/存)
  ├── batch_id, ingredient_id
  ├── qty, remaining_qty
  ├── purchase_date, expire_date
  └── unit_price, storage_method

ConsumptionLog (销)
  ├── batch_id (FEFO 选择批次)
  ├── qty, date, reason (plan|manual|discard)
  └── plan_meal_id (追溯)

ShoppingItem (采)
  ├── ingredient_id, need_qty
  ├── suggest_date (分批建议日期)
  └── bought (已购标记)
```

**FEFO 规则**：确认计划时按「剩余保质期最短优先」扣减库存。

---

## 4. 数据架构

### 4.1 核心实体关系

```
FamilySettings (1行)         NutritionTemplate (多条, 启用标记)
       │
MealSchedule (7行 weekdays)
       │
MealPlan ──< PlanMeal ──> Recipe ──< RecipeIngredient ──> Ingredient
       │                    │                                   │
ShoppingItem               │                              PriceRecord (趋势)
       │                   │                              InventoryBatch (批次)
       └───────── Ingredient ──────┘                    ConsumptionLog
```

### 4.2 扩展预留

| 字段 | 用途 | 状态 |
|------|------|------|
| `PriceRecord.market_detail` | 当地 8 市场详细价格 | 待加 (Task #12) |
| `Ingredient.barcode` | 真实扫码入库 | 已定义、demo 占位 |
| `FamilySettings.allergies` | JSON 数组，当前单用户 | 预留家庭成员粒度 |
| `PlanMeal.done_status` | pending/done/skipped | 已实现 |

---

## 5. 部署架构

### 5.1 Docker Compose (生产推荐)

```yaml
services:
  frontend:     # nginx:alpine, port 8080:80
    depends_on: backend

  backend:      # python:3.12-slim, uvicorn, port 8001:8000
    volumes:    meal_data:/data (SQLite + uploads)
    environment: DATABASE_URL=sqlite:////data/meal.db

  # db:         # postgres:16 (可选, 需取消注释)
```

### 5.2 性能边界 (建议值)

| 指标 | 值 | 说明 |
|------|-----|------|
| 并发用户 | < 10 (家庭) | 无需连接池调优 |
| 数据库大小 | < 100MB | SQLite 完全胜任 |
| API 响应时间 | < 200ms (P95) | 无复杂联表 |
| 电商抓取频率 | 每日 ≤ 100 次 | 限流硬约束 |

---

## 6. 演进路线图

### Phase 1 — 核心闭环 (已完成 ✅)
- [x] 菜谱生成 + 库存管理 + 采购清单
- [x] 模拟菜价 + 演示数据
- [x] PWA + Docker 部署
- [x] 前端浏览器冒烟测试 11 路由全绿

### Phase 2 — 真实数据源 (进行中 🔄)
- [x] #8–#11 当地发改委价格适配器 (discover + parse + alias)
- [x] #21 电商兜底 (慢慢买 Playwright 实跑验证 5/5 命中)
- [ ] #12 PriceRecord.market_detail 列迁移
- [ ] #14 CompositePriceSource 工厂切换 + 降级链
- [ ] #15 回填近 1 年历史价
- [ ] #16 调度改为周更 (每周一 00:10)
- [ ] #19 /api/prices/latest 周环比 + 真实价标注
- [ ] #17 /api/prices/source 数据来源接口
- [ ] #20 前端来源标注 + 均值/明细展开
- [ ] #18 端到端实测

### Phase 3 — 智能化增强 (规划中)
- [ ] LLM 对话式菜谱生成 ("冰箱里有X、想吃Y，帮我规划")
- [ ] 营养深度分析 (微量元素、膳食结构雷达图)
- [ ] 菜价预测 (基于历史趋势 + 季节性)
- [ ] 食材替代建议 ("没牛肉时用什么替代")

### Phase 4 — 协作与生态 (远期)
- [ ] 多成员家庭管理 (过敏约束按成员)
- [ ] 社区食谱共享
- [ ] 线上生鲜平台一键下单 (集成叮咚/盒马 API)
- [ ] Capacitor 原生应用 (替代 PWA)

### Phase 5 — 智能家居 (愿景)
- [ ] 智能冰箱库存同步 (拍照识别/传感器)
- [ ] 语音助手集成 ("今晚吃什么")
- [ ] 餐后反馈闭环 (跳过/重做 → 口味偏好学习)

---

## 7. 扩展点与插件化设计

### 7.1 已实现的扩展点

| 扩展点 | 接口 | 注册方式 |
|--------|------|----------|
| 菜价数据源 | `PriceSourceAdapter` ABC | 实现 → 注册到 `CompositePriceSource.adapters` 列表 |
| 营养目标 | `NutritionTemplate` 模型 | 用户通过 Settings 页面自由CRUD |
| 餐次配置 | `MealSchedule` 模型 | 每天3餐独立开关 |
| 过敏约束 | `FamilySettings.allergies` JSON | Settings 页面选择 |

### 7.2 建议新增的扩展点

| 扩展点 | 接口设计 | 优先级 |
|--------|----------|--------|
| 通知渠道 | `NotifyAdapter(ABC).send(msg, channel)` → Email/WeChat/Web Push | P3 |
| 食谱导入 | `RecipeSource(ABC).fetch(query) → [RecipeIn]` → 社区/API/URL | P3 |
| 生鲜下单 | `OrderAdapter(ABC).place(shopping_items) → order_id` | P4 |
| 语言/本地化 | i18n 资源文件 → Vue I18n | P2 |

---

## 8. 技术债 & 重构建议

| 项目 | 当前状态 | 建议 |
|------|----------|------|
| 价格源切换 | 硬编码 `get_price_source()` | 改为 `CompositePriceSource` 组合器 (Phase 2 已规划) |
| 前端数据来源标注 | 硬编码字符串 | 从 `/api/prices/source` 动态读取 |
| 测试覆盖 | 仅价格源离线单测 | 补充推荐引擎 + 库存逻辑单元测试 |
| 错误处理 | 路由层 catch-all | 增加业务层自定义异常 → 统一错误码 |
| 日志 | print + log | 统一 `structlog` JSON 格式 → 可接入 ELK |
| 迁移脚本 | 无 | 引入 Alembic 管理 schema 变更 |

---

## 9. 关键决策记录 (ADR)

| ID | 决策 | 理由 | 日期 |
|----|------|------|------|
| ADR-1 | 单体 FastAPI 而非微服务 | 家庭场景并发 < 10，微服务无收益 | 2026-07 |
| ADR-2 | 推荐引擎用贪心+局部搜索而非 ILP | 规模小、秒级求解、可解释 | 2026-07 |
| ADR-3 | 菜价三源降级链 (政府/电商/模拟) | 真实价优先、电商兜底、静默估算 | 2026-07 |
| ADR-4 | 电商抓取用慢慢买优先、京东淘宝兜底 | 慢慢买无登录墙、价格直出 | 2026-07 |
| ADR-5 | 前端 Vant4 移动优先、PWA 而非原生 | 快速迭代、跨平台、离线可用 | 2026-07 |
