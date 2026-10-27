# Peko 架构参考（2026-08 版，已过时）

> ⚠️ 本文写于 2026-08-14，只覆盖工作台（plans_store / workbench_server / plans_web.html）那一块。2026-09 重构后新增了 `config_store` / `bus` / `pet_registry` / `effect_state` / `pet_parts` / `style_kit`，`pet.py` 也已拆分，本文不再代表当前结构。**现行文档见 [`../architecture.md`](../architecture.md)。** 保留本文仅作历史参考。

桌面桌宠（PyQt5）+ 个人计划工作台的完整文件 / 数据 / API 地图。

## 进程与运行形态

- 桌面端：PyQt5 应用，托盘常驻。托盘菜单两个入口：
  - 「计划台」→ 内嵌 `QWebEngineView` 窗口（嵌入式）。
  - 「工作台」→ 系统浏览器打开网页版。
- 本地同步服务：`peko/ui/workbench_server.py` 起 `ThreadingHTTPServer` @ `127.0.0.1:18340`，让浏览器版与内嵌版读写同一份 `data/*.json`，实现双向同步（内嵌 2s 轮询、网页 3s 轮询）。
- 关键：本地服务必须跑在系统 Python（唯一装 PyQt5 的解释器）。

## 数据层 `peko/core/plans_store.py`

单一数据源。所有写走「临时文件 + `os.replace`」原子写。

- 每个模块一组方法：`X()` 读、`replace_X(arr)` 写，配合 `_normalize_X` 做归一化。
- 通用助手：`_named_path(fname)`、`_load_named(fname, norm)`、`_persist_named(fname, arr)`（写成 `{version: _SCHEMA_VERSION, items: arr}`）。
- 现有模块：`plans / todos / habits / ledger / review / focus_log`。
- ⚠️ 该类有且只能有一个 `class PlansStore:`。曾因重复定义导致原类被遮蔽、plans/todos 方法丢失。改动后 `py_compile` + grep 确认。

## 数据文件（均 `{version, items}`）

| 文件 | 模块 | 说明 |
| --- | --- | --- |
| `data/plans.json` | 计划台 | 计划项 |
| `data/todos.json` | 待办清单 | 待办 |
| `data/habits.json` | 习惯打卡 | 习惯 + 打卡记录 |
| `data/ledger.json` | 记账 | 收支条目 |
| `data/review.json` | 周月回顾 | 回顾记录 |
| `data/focus.json` | 专注 | 专注时段日志 |

## 同步 API `peko/ui/workbench_server.py`

- GET：`/api/plans` `/api/todos` `/api/habits` `/api/ledger` `/api/review` `/api/focus` → 各自 `_store.X()`。
- POST：同一路径集合 → 各自 `replace_*`。
- 新增模块时：GET 加一个分支，POST 把路径加进 dispatch 元组并指向 `replace_X`。

## 工作台前端 `peko/ui/plans/plans_web.html`

单文件、零依赖、CSS/JS 全内联。

- `STATE = { plans:[], todos:[], habits:[], ledger:[], review:[], focusLog:[] }`。
- 模式检测：`location.hostname === "127.0.0.1" || "localhost"` → `http`；内嵌经 QWebChannel → `bridge`；`file://` → `local`。
- 每个扩展模块一个 `persistX`：http→`fetch /api/X`，local→localStorage（键如 `wb_wb_habits`）。
- `loadAll`/`doRefresh` 用 `Promise.all([...6 个 fetch...])` 拉全量。
- 六大模块 tab：计划台 / 待办清单 / 习惯打卡 / 记账 / 专注 / 周月回顾。`switchMod(mod)` 用 `section[id^="mod-"]` 通用切换。
- 习惯：连续打卡 streak + 12 周热力格（84 格，可点 toggle 任意日期）。
- 记账：收入/支出 + 范围与分类过滤 + 统计（¥，支出红 / 收入绿）。
- 专注：SVG 环形计时，预设 25/15/5，`logFocus(min,label)`。
- 回顾：月/年切换 + 自动统计 + `saveReview` 写 `review.json`。
- 导出 `version:2` 覆盖全部 6 个数组。

## 内嵌门控（embedded gating）

`body.embedded` 下隐藏：`.tab-ext`（扩展模块 tab）、`#btnAddHabit`、`#btnAddLedger`，以及编辑/导入/导出/清空。内嵌版只保留 计划台 / 待办清单 的查看 + 完成；扩展模块仅网页版可编辑。

## 桥接 `PlanBridge`（QWebChannel）

内嵌窗通信：`getAll / save / getTodos / saveTodos` 等。扩展模块目前不经 bridge，走 http/local。

## 托盘 `peko/ui/tray.py`

- `_plans_web_action`（内嵌）文本「计划台」。
- `_plans_web_browser_action`（浏览器）文本「工作台」。
