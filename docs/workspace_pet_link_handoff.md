# 桌宠 × 工作台 联动迭代 — 交接简报

> 适用对象：拟组建的「桌面效率产品」专家团（桌面客户端 / 前端 / 产品交互 / LLM 应用）
> 用途：接手 Peko 项目前，快速了解现状、可复用资产、以及建议优先落地的联动方案。

---

## 1. 项目现状一句话

Peko 是一个 **PyQt5 电脑桌宠**，已具备「互动聊天 + 个人计划工作台」两大功能；工作台目前是 **6 个模块**的单文件 HTML 页面，通过「托盘内嵌窗」与「系统浏览器纯网页版」双形态共享同一份本地数据，已实现双向同步。**下一步目标**：让桌宠的主动互动更丰富，并与工作台的增删改查产生真实联动，而非各做各的。

---

## 2. 已具备、可直接复用的资产（不要重写，先读懂）

| 资产 | 路径 | 角色 | 关键能力 |
| --- | --- | --- | --- |
| 单一数据源 | `peko/core/plans_store.py` | 桌面端数据中枢 | 原子写（`temp + os.replace`）；`plans()`/`todos()`/`habits()`/`ledger()`/`review()`/`focus_log()` + 对应 `replace_*`；自动归一化 |
| 本地同步服务 | `peko/ui/workbench_server.py` | 浏览器版后端 | `ThreadingHTTPServer` @ `127.0.0.1:18340`；`GET/POST /api/plans|todos|habits|ledger|review|focus` 读写同一份 `data/*.json` |
| 工作台前端 | `peko/ui/plans/plans_web.html` | 双形态页面 | 6 模块（计划台/待办清单/习惯打卡/记账/专注/周月回顾）；`bridge`/`http`/`local` 三模式自适应；内嵌态隐藏编辑/导入/导出/扩展模块 |
| 托盘入口 | `peko/ui/tray.py` | 入口装配 | 托盘「计划台」→内嵌窗；托盘「工作台」→浏览器打开网页版 |
| 桥接层 | `PlanBridge`（QWebChannel） | 内嵌通信 | `getAll/save/getTodos/saveTodos` 等 |

**数据文件**：`data/plans.json`、`data/todos.json`、`data/habits.json`、`data/ledger.json`、`data/review.json`、`data/focus.json`（均 `{version, items}` 结构）。

**关键约束（务必遵守）**：
- 本地服务必须跑在 **系统 Python**（`C:/Users/502380/AppData/Local/Programs/Python/Python313/python.exe`，唯一装了 PyQt5 的环境），不能用 managed Node 的 venv。
- 网页端三模式：`location.hostname === "127.0.0.1" || "localhost"` → `http`；内嵌窗通过 `QWebChannel` → `bridge`；`file://` 兜底 → `local`（localStorage）。
- 内嵌窗只保留「计划台 / 待办清单」的查看与完成，扩展模块（习惯/记账/专注/回顾）仅网页版可编辑。
- 导出格式 `version:2`，覆盖全部 6 个数组。

---

## 3. 桌宠 × 工作台 联动菜单（按价值排序）

| 编号 | 联动项 | 描述 | 依赖 | 优先级 |
| --- | --- | --- | --- | --- |
| **C5** | 自然语言入口 | 桌宠聊天框输入「记一笔午饭 38」「提醒我 17:00 交周报」「开始 25 分钟专注」→ 识别意图 → 直接调用 `plans_store` / `workbench_server` API 写入对应模块 | LLM 意图识别 + 桌面客户端桥接 | **首刀首选** |
| **B3** | 完成回写宠物 | 工作台勾掉待办 / 打卡习惯 / 完成专注 → 桌宠情绪变好、弹出成就小动画 / 累计「靠谱值」 | 桌面客户端监听数据变化 | **首刀次选** |
| A | 提醒与跳转 | 工作台设的提醒时间到 → 桌宠主动戳你 → 点一下跳到对应工作台模块 | 桌面客户端全局定时器 + 桥接 | 二期 |
| D | 陪伴态联动 | 桌宠根据今日待办/习惯完成情况切换状态（如「今天还有 3 件没做」→ 桌宠戴眼镜加班态） | 桌面客户端读取 `plans_store` 聚合 | 二期 |

> **建议首刀只做 C5 + B3**：一个负责「主动收集」（把桌面上的零散意图变成工作台数据），一个负责「正向反馈」（让收集有即时爽感）。两者形成闭环，对桌宠「更丰富 + 和工作台联动」的需求覆盖最完整。

---

## 4. 建议新专家团成员构成

| 角色 | 负责面 | 与本项目对接点 |
| --- | --- | --- |
| **PyQt / Python 桌面客户端工程师** | 桌宠本体：托盘、悬浮窗、全局热键、`PlanBridge` 桥接、数据变化监听、提醒定时器、NL→API 调用封装 | `peko/ui/tray.py`、`PlanBridge`、调用 `workbench_server` / `plans_store` |
| **零依赖单文件 HTML 前端工程师** | 工作台页面继续迭代（6 模块已成型，需补可视化/交互细节） | `peko/ui/plans/plans_web.html`，沿用小台专家规范 |
| **产品 / 交互设计师** | 联动交互剧本、宠物情绪/成就体系、提醒节奏与打扰度平衡 | 联动菜单 A–D 的体验定义 |
| **LLM 应用工程师** | 聊天人格 + 意图识别 → 结构化调用（C5 核心） | 复用现有聊天模块，新增意图路由到 API |

> 在 WorkBuddy 语境下：**保留「小台」专家做工作台侧**，新增一个 **「Qt 桌面客户端」专家** 做桌宠侧，再配 **产品交互 + LLM 意图** 两个角色，组成本次「桌面效率产品」专家团。

---

## 5. 首刀交付物建议（给新团队的 Sprint 0 目标）

1. **C5 最小闭环**：在桌宠聊天框支持 3 条指令 —— 记账、加待办、开始专注；后端直接落到 `data/*.json`（走 `plans_store` 或 `/api/*`）。
2. **B3 最小闭环**：监听 `todos` 完成事件 → 桌宠播放一次「点赞」微动画 + 累加 `靠谱值` 计数（先存本地即可）。
3. **联调验证**：用 `scripts/wb_modes_test.js`（jsdom，managed Node）跑三模式读写回归，确认新增写入不破坏现有同步。
4. **文档**：在 `docs/plans_module_dev.md` 追加「联动层」一节，记录新 API 与桥接约定。

---

## 6. 已知坑位（新团队避坑）

- `plans_store.py` 曾因重复 `class PlansStore:` 导致方法被覆盖 → 改动后务必 `py_compile` + grep 确认只有一个类。
- `plans_web.html` 内联脚本曾因 `}); });` 双闭合整段失效 → 改动后跑 `node --check` 提取的 inline 脚本。
- **git 索引污染问题未处理**：`data/*.json`、`data/chat_history/*`、`.workbuddy/*` 曾被误加入暂存区，且 `.gitignore` 缺 `data/` 与 `.workbuddy/` 规则。新团队接手后第一件事应是补 `.gitignore` 并清理索引，避免把运行数据/隐私提交进仓库。
