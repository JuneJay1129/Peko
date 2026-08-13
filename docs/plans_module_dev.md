# 计划工作台模块 · 开发记录

> 个人计划台：日 / 月 / 年周期计划 + 待办清单，工作/学习/生活/运动/饮食(+自定义) 分类。
> 双入口：托盘「计划台」（桌面内嵌 QWebEngine，WebChannel 桥接，**仅查看+完成**）+ 托盘「工作台」（系统浏览器经本地服务打开，读写同一份数据，承担全部增删改/导入/导出/清空）。
> 两端经同一个 `PlansStore`（磁盘 `data/plans.json` / `data/todos.json`）保持实时同步。

## 设计决策（用户确认）
1. **同步方式**：内嵌 QWebEngine 实时桥接（WebChannel 读写 `data/plans.json`）；网页版经本地 HTTP 服务（`127.0.0.1:18340`）读写**同一份**文件。两端共用 `PlansStore` 单一真相源，天然同步。
2. **职责切分（最新）**：内嵌「计划台」**只做查看计划 + 完成计划 + 完成待办**（CSS `body.embedded` 隐藏新增/编辑/删除/导入/导出/清空与全部扩展模块入口）；其余所有操作放到浏览器「工作台」。
3. **工作台定位**：「工作台」为浏览器侧总管理壳，已接入六大模块——计划台 / 待办清单 / 习惯打卡 / 记账 / 专注 / 周月回顾；内嵌「计划台」是其中的轻量查看+完成伴侣。
4. **分类**：固定 5 类 + 自定义（兜底桶）。

## 文件清单
| 文件 | 作用 |
|---|---|
| `peko/core/plans_store.py`（新） | Plan 模型 + `data/plans.json` 读写（原子写）+ 逾期/顺延/统计/增删改查。单一真相源。 |
| `peko/ui/plans/plans_web.html`（新） | Web 工作台：日/月/年看板 + 分类筛选 + 进度 + 今天焦点 + 导入/导出。有桥接走 `plans.json`，无桥接回退 localStorage。 |
| `peko/ui/plans/qwebchannel.js`（新） | 官方 Qt WebChannel JS（LGPL），随包提供，使 HTML 无需运行时联网。 |
| `peko/ui/plans_web_dialog.py`（新） | Web 工作台宿主窗：`QWebEngineView` + `QWebChannel`(`PlanBridge`) 实时桥接（仅查看+完成）；并导出 `open_plans_web_browser()` 经本地服务打开网页版。 |
| `peko/ui/workbench_server.py`（新） | 本地工作台 HTTP 服务（`127.0.0.1:18340`，随进程启停，外部不可访问）。静态页 + `/api/plans`、`/api/todos`、`/api/habits`、`/api/ledger`、`/api/review`、`/api/focus`（GET 读 / POST 整表替换），读写同一个 `PlansStore`。 |
| `peko/ui/tray.py`（改） | 托盘「计划台」（内嵌 Web 宿主窗，仅查看完成）+「工作台」（经本地服务打开，全功能六大模块）。 |
| `peko/main.py`（改） | 创建 `QApplication` 后设置 `Qt.AA_ShareOpenGLContexts`，允许随后懒导入 `QtWebEngineWidgets`。 |
| `packaging/main.spec`（改） | 打包 datas 增加 `peko/ui/plans`；hiddenimports 增加 `QtWebEngineWidgets/QtWebEngineCore/QtWebChannel`。 |

## 数据 Schema
```json
{ "version": 1, "plans": [ {
  "id": "p...", "title": "完成季度复盘", "cat": "work", "cycle": "daily",
  "period": "2026-08-13", "pri": "P0", "status": "pending",
  "progress": 40, "note": "细节", "created_at": "...", "updated_at": "...", "done_at": null
} ] }
```

## 关键实现点
- **单一真相源**：桌面小窗与 Web 桥接都经 `PlansStore` 读写 `data/plans.json`（开发期=项目根，冻结版=`runtime_paths.get_writable_root()`）。
- **跨界面实时**：Web 宿主窗每 2s 拉取一次 `getAll()`，仅数据变化才重渲染；桥接侧 `save()` 后 `dataChanged` 信号推送，两个界面一致。
- **原子写**：临时文件 + `os.replace`，避免半截写入损坏。
- **顺延**：日计划昨天未完成在「今天要处理」中标红显示（不清空、不改期，保留历史）。

## 已知限制 / 待本机验证
- **WebChannel 渲染**：QWebEngine 需真实显示环境，无头（offscreen）下会 segfault，无法在 CI/沙箱实测。
  代码、桥接 Python 侧、JS 语法、官方 `qwebchannel.js` 均已验证；Chromium 渲染请在本机（有桌面）打开托盘「计划台」（内嵌）确认。
- `qwebchannel.js` 取自 Qt `dev` 分支（兼容 Qt5/Qt6 WebChannel 协议）；若桥接异常可换 5.15.x 版本。
- 未装 `PyQtWebEngine` 时，托盘「计划台」会自动降级：用系统浏览器打开（经本地服务 → 走 http 模式，仍与磁盘共享同一份数据，只是不在桌宠内嵌）；
  若本地服务也起不来，则回退 `file://` 纯 localStorage 独立副本（导入/导出 JSON 与桌面数据互换）。
- **依赖**：`requirements.txt` 已加 `PyQtWebEngine>=5.15`（内嵌桥接与 PyInstaller 打包必需）。

## 复用的踩坑
- **导入顺序**：`PyQt5.QtWebEngineWidgets` 必须在 `QApplication` 创建前导入，或创建前设置
  `Qt.AA_ShareOpenGLContexts`。否则报 *"QtWebEngineWidgets must be imported ... before a QCoreApplication instance is created"*。
  本项目在 `main.py` 创建 app 后立刻 `app.setAttribute(Qt.AA_ShareOpenGLContexts)`。
- **样式表**：`setStyleSheet("font-weight:...")` 会覆盖父级 color/font-size；粗体用 `setFont(QFont.Bold)`。
  下拉框 `cursor: pointer` 不被 QSS 解析 → 改为 `setCursor(Qt.PointingHandCursor)`。
  弹出列表 `border-radius` 在无边框+`WA_TranslucentBackground` 下会触发遮罩重绘卡顿 → 弹窗用直角。

## 工作台标准重做（小台专家 · 2026-08-13）
- `peko/ui/plans/plans_web.html` 按「工作台搭建师」标准整体重写：纯电脑端、单文件 HTML、零外链（仅本地 `qwebchannel.js` 供内嵌桥接）。
- **双模块**：`计划台`（日/月/年计划，分类+优先级+进度+所属期）+ `待办清单`（标题/分类/优先级(P0-P2)/截止日/完成态）。数据 key 前缀 `wb_planbench_`。
- **今日要处理**置顶跨模块：逾期未完成 + 今天该做 + 当月/当年计划；逾期标红、一键完成；日计划昨天未做完自动顺延到今天。
- **本地存储**：localStorage 持久化；首屏「导出 JSON / 导入恢复 / 清空（二次确认）」；数据≥30 条顶部温和提示备份。
- **预置示例数据**：5 条计划（含 1 条昨日逾期日计划）+ 3 条待办（含 1 条逾期），首次打开即有内容，带 seed 标记避免重复注入。
- **三种运行模式（boot() 模式判定）**：
  - `bridge`：内嵌桌宠（`window.qt.webChannelTransport` + `QWebChannel` 存在）→ 经 `bridge.getAll()/save()/getTodos()/saveTodos()` 读写共享文件。
  - `http`：经本地服务打开（`location.hostname === "127.0.0.1" || "localhost"`）→ `fetch('/api/plans'、'/api/todos'、'/api/habits'、'/api/ledger'、'/api/review'、'/api/focus')` 读写**同一份** `data/*.json`，每 3s 轮询实现与内嵌窗双向同步。
  - `local`：其余（含直接双击 `file://` 打开）→ localStorage 独立副本回退，可导入/导出与桌面数据互换。**不会**误入 http 模式。
- **桥接契约（关键）**：内嵌于桌宠时，`boot()` 检测 `window.qt.webChannelTransport` → `QWebChannel` 读 `bridge.getAll()`（返回**数组**，非 `{version,plans}`）、写 `bridge.save(计划数组)`；待办走 `bridge.getTodos()/saveTodos(数组)`。
  注意 `PlanBridge.save()/saveTodos()` 期望**直接收数组**——HTML 侧 `persistPlans()/persistTodos()` 已按数组发送。
- **内嵌即「仅查看 + 完成」**：`applyEmbeddedMode()` 给 `body` 加 `embedded` 类；CSS 隐藏 `#btnAddPlan/#btnAddTodo/#btnExport/#btnImport/#btnClear` 及所有 `.iconbtn`（编辑/删除）。空数据提示去网页版添加，内嵌不注入示例。

## 功能1：内嵌「计划台」补齐待办清单 tab（2026-08-13）
- 之前内嵌窗只桥接计划，待办仅存嵌入式 localStorage（不与磁盘/浏览器版互通）。现统一：待办也桥接落盘。
- `peko/core/plans_store.py` 扩展：`data/todos.json` 单一真相源；新增 `_normalize_todo` + `todos()/add_todo/update_todo/remove_todo/toggle_todo/replace_todos/to_json_todos`，原子写复用 `_persist_todos`。
- `plans_web_dialog.py` 的 `PlanBridge` 新增 `@pyqtSlot getTodos()` 与 `saveTodos(arr)`（同样期望数组），`dataChanged` 推送 todos JSON。
- `plans_web.html`：`persistTodos()` 桥接感知（有 `bridge.saveTodos` 走桥接，否则 localStorage）；`boot()` 桥接分支 `getAll` 后 `getTodos` 再渲染（无 getTodos 时降级读 localStorage）。
- 验证：jsdom 双路径测试均过——本地模式（badge 本地模式、增删持久化）+ 桥接模式（mock QWebChannel，badge 已连接桌宠，计划/待办来自桥接，新增待写回桥接存储），无 console 报错。
- 结果：桌面内嵌「计划台」现为完整工作台（计划+待办，均落盘 `plans.json`/`todos.json`）；浏览器版仍为 localStorage 独立副本。

## 同步 bug 修复 · 两个地方数据不互通（2026-08-13）
- **现象**：内嵌「计划台」与「计划台（网页版）」看到的数据不一致，网页版改了内嵌看不到、反之亦然。
- **根因（两层）**：
  1. `PlansStore.to_json()` 返回的是 **JSON 数组**，但早期 HTML 用 `JSON.parse(pjson).plans` 取对象字段，解析为空 → 内嵌读到空。已改为 `parseList()` 优先按数组解析。
  2. 网页版此前走**独立 localStorage**（`file://` 双击或系统浏览器打开），与磁盘 `plans.json` 不是同一份 → 天然不互通。
- **修复方案**：网页版改为经**本地 HTTP 服务**（`127.0.0.1:18340`）读写同一个 `PlansStore`（新增 `peko/ui/workbench_server.py`，随桌宠进程启动/退出，仅绑 127.0.0.1 外部不可达）。网页版 `http` 模式每 3s 轮询 `/api/*` 拉取，内嵌窗 2s 轮询 → 两端对同一份文件实时一致。
- **模式判定修正（关键，防回归）**：原 `boot()` 用 `location.protocol.indexOf("http")===0` 判定 http 模式，会误把任意 `https://` URL 当 http 模式去调 `fetch`（undefined）→ 崩溃。改为按服务主机判定：`location.hostname === "127.0.0.1" || "localhost"` 才进 http 模式，否则回退 local（localStorage）。这样 `file://` 双击与误入的非本机 http(s) 都安全走本地回退，不污染共享数据。
- **验证**：`scripts/wb_modes_test.js`（jsdom + 真实本地服务）三模式全绿——
  - `local`：badge「本地模式」、示例注入、新增待办落 localStorage、无 fetch 报错（原 bug 场景 `https://local.test` 已正确回退）。
  - `bridge`：badge「已连接桌宠」、`body.embedded` 已加（编辑/新增/导入/导出/清空被隐藏）、计划来自桥接、完成写回桥接存储。
  - `http`：badge「网页版 · 已同步」、首屏读到服务端数据（证明读同步）、完成计划与新增待办均写回服务端 `plans.json/todos.json`（证明写同步）。
- **结论**：内嵌（bridge）与网页版（http）共用磁盘同一真相源，双向实时同步；纯 `file://` 双击为独立本地副本（导出/导入可与之互换）。

## 职责切分收尾（2026-08-13）
- 内嵌「计划台」仅保留：查看计划、完成计划（含「今天要处理」一键完成）。新增/编辑/删除/导入/导出/清空全部只在浏览器「工作台」提供（CSS `body.embedded` 屏蔽）。
- 内嵌完成计划经 `bridge.save()` 写回共享文件 → 网页版 3s 轮询即时看到；网页版改动经 POST 写回共享文件 → 内嵌 2s 轮询即时看到。

## 工作台扩展：六大模块（2026-08-13）
- **需求**：用户把托盘网页入口改名为「工作台」，并要求按「工作台」思路扩展功能（更强互动感、更直观感受计划打卡）。
- **取舍**：用户此前明确 reject 了「月历打卡热力图」式日历图表；因此改用「习惯打卡」模块（连续天数 + 14×6 打卡热力网格，可点任意一天补打卡）替代，更贴合「打卡」互动诉求且不引入日历。
- **新增四大模块**（与 计划台/待办清单 并列，浏览器「工作台」全功能；内嵌仅查看+完成，扩展模块在内嵌隐藏）：
  1. **习惯打卡**：习惯清单 + 今天打卡/取消 + 连续天数（streak）+ 最近 12 周打卡热力网格（可点历史补卡）。数据 `data/habits.json`：`{id,title,cat,created_at,records:{日期:1}}`。
  2. **记账**：收入/支出记录（分类 + 金额 + 日期 + 备注），本月/全部切换 + 按分类汇总（收入/支出/结余/分类数）。数据 `data/ledger.json`。
  3. **专注**：番茄钟（25/15/5 预设，开始/暂停/重置 + 圆环进度）+ 手动「记一笔」+ 今日专注总时长 + 最近记录。数据 `data/focus.json`。
  4. **周月回顾**：月度/年度切换，自动汇总 计划完成率 / 待办完成率 / 习惯打卡率 / 专注分钟；可写复盘笔记并保存。数据 `data/review.json`。
- **数据层 `plans_store.py`**：新增通用命名文件机制（`_load_named`/`_persist_named`，原子写复用），与 `plans.json`/`todos.json` 对称；`habits()/replace_habits()`、`ledger()`/`replace_ledger()`、`review()`/`replace_review()`、`focus_log()`/`replace_focus()`。各自 `_normalize_*` 轻量校验（空标题/文本不落盘）。
- **服务 `workbench_server.py`**：新增 `GET/POST /api/habits`、`/api/ledger`、`/api/review`、`/api/focus`，与 plans/todos 同构。
- **同步**：三模式统一经 `persist*()` 分派——`bridge` 走 localStorage 回退（内嵌隐藏扩展模块，不会触发）、`http` 走本地服务 `/api/*`、`local` 走 localStorage。导出/导入覆盖全部六模块（`version:2`）。
- **内嵌屏蔽**：`body.embedded` 隐藏 `.tab-ext`（四个扩展模块 tab）+ `#btnAddHabit/#btnAddLedger` + 原有编辑/导入/导出/清空，内嵌保持「计划台/待办清单 仅查看+完成」。
- **验证**：`scripts/wb_modes_test.js` 三模式全绿，且新增覆盖 http 模式对 habits/ledger/review/focus 的「读服务端 + 写回服务端」；local 模式 seed 已包含习惯/记账/专注示例。
- 结论：浏览器「工作台」已是含六大模块的个人效率中心，与内嵌「计划台」共用磁盘同一真相源、双向实时同步。

