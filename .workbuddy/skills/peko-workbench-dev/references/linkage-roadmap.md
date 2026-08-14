# 桌宠 × 工作台 联动路线图

让桌宠互动更丰富，并与工作台的增删改查产生真实联动。按价值排序。**首刀 C5 + B3 已实现（2026-08-14）**，形成「收集 → 反馈」闭环；下一步做 A / D。

## 优先级总览

| 编号 | 联动项 | 描述 | 状态 |
| --- | --- | --- | --- |
| C5 | 自然语言入口 | 聊天框一句话 → 意图识别 → 写工作台 | ✅ 已实现（`peko/core/nl_intent.py` + `chat.py`） |
| B3 | 完成回写宠物 | 完成待办/打卡/专注 → 情绪+动画+靠谱值气泡 | ✅ 已实现（`pet_bond.py` + `pet_link.py` + `pet.py` + 双触发源） |
| A | 提醒与跳转 | 工作台提醒到点 → 桌宠戳 → 点击跳对应模块 | ⬜ 二期 |
| D | 陪伴态联动 | 桌宠按今日待办/习惯完成情况切状态 | ⬜ 二期 |

## C5 自然语言入口（已实现）

- 解析/落盘在 `peko/core/nl_intent.py`（纯 Python，可单测）：记账/待办落盘，专注由聊天侧 QTimer 提醒（不落盘，避免虚增统计）。
- 接线在 `peko/ui/chat.py` `_on_submit`：命中意图走本地，未命中走 AI。
- 防劫持：仅明确命令句式触发；疑问/感叹/无金额不触发。

## B3 完成回写宠物（已实现）

- 靠谱值数据：`peko/core/pet_bond.py` → `data/pet_bond.json`。
- 进程内通道：`peko/ui/pet_link.py` 单例 notifier；`notify_completion(kind,label)` 一记一播。
- 桌宠反馈：`peko/ui/pet.py` `_on_workspace_completed`（复用 praise 情绪/动画 + 靠谱值气泡）。
- 触发源：浏览器版 `POST /api/event`（`workbench_server.py`）、内嵌版 `bridge.recordEvent`（`plans_web_dialog.py`）；前端 `notifyCompletion()` 挂在 `markDone`/`toggleHabitDate`/`logFocus`。

## A / D（二期，待做）

- A 提醒与跳转：桌面端全局定时器读 `plans_store` 到点 → 桌宠戳 → 点击跳到对应模块（经桥接/唤起网页对应 tab）。
- D 陪伴态联动：桌宠读 `plans_store` 聚合今日待办/习惯完成度 → 切换待机状态（如「还有 3 件没做」→ 加班态）。

## 联调验证

改动后用 `scripts/wb_modes_test.js` 跑三模式读写回归（命令见 SKILL.md 的 Testing 节），并跑 `unit_tests/test_nl_intent.py`、`test_pet_bond.py`。桌面端无 GUI 时至少做：`py_compile` + 单测 + 起服务 `curl /api/event` 验证 B3 服务端通路。

## 边界

- 桌面侧重活（托盘、悬浮窗、全局热键、`PlanBridge`、定时器）在 `peko/ui/tray.py` 等桌面文件。
- 工作台页面交互在 `plans_web.html`。
- 数据一律走 `plans_store` / `workbench_server`，不绕过。

