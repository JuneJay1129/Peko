# 工作台扩展 · 六大模块

## 做了什么
把托盘网页入口改名为「工作台」，并将原「计划台 + 待办清单」网页端扩展为含 **六大模块** 的个人效率中心：
**计划台 · 待办清单 · 习惯打卡 · 记账 · 专注 · 周月回顾**。

> 说明：用户曾明确 reject「月历打卡热力图」式日历图表，因此「打卡」互动感改用「习惯打卡」模块（连续天数 + 12 周打卡网格，可点任意一天补打卡）实现，不引入日历。

## 改动文件
- `peko/core/plans_store.py`：新增通用命名文件机制（原子写）+ `habits/ledger/review/focus_log` 读写与 `_normalize_*` 校验。
- `peko/ui/workbench_server.py`：新增 `GET/POST /api/habits`、`/api/ledger`、`/api/review`、`/api/focus`。
- `peko/ui/plans/plans_web.html`：重写为六模块工作台；三模式 `persist*` 分派；`switchMod` 通用切换；今日要处理含未打卡习惯；导出/导入覆盖六模块（`version:2`）。
- `peko/ui/tray.py`：网页入口改名「工作台」（内嵌仍叫「计划台」）。
- `docs/plans_module_dev.md`：更新双入口/职责切分/文件清单/模式说明 + 新增扩展节。

## 同步架构（不变）
- `bridge`（内嵌）：WebChannel 桥接，仅查看+完成；扩展模块在内嵌隐藏。
- `http`（浏览器经 `127.0.0.1:18340`）：读写同一份 `data/*.json`，每 3s 轮询双向同步。
- `local`（file://）：localStorage 独立副本。

## 验证
`scripts/wb_modes_test.js`（jsdom + 真实本地服务）三模式全绿，且 http 模式覆盖 habits/ledger/review/focus 的「读服务端 + 写回服务端」；local 模式示例数据已含习惯/记账/专注。

## 运行预览
浏览器全功能需经托盘「工作台」启动本地服务（http 模式）。直接打开 html 为 local 模式（含示例数据，可体验全部 UI）。
