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


## 桌宠×工作台联动：C5 自然语言入口 + B3 完成回写（2026-08-14）

> 首刀联动闭环：C5 负责「主动收集」（把桌面上一句话变成工作台数据），B3 负责「正向反馈」（完成动作即时激励）。

### C5 自然语言入口（聊天 → 工作台写入）
- **新增 `peko/core/nl_intent.py`**（纯 Python，无 Qt，可单测）：`parse(text)` 把一句话识别为意图，`apply(intent, store)` 落盘并返回确认文案。
  - 记账：`记一笔午饭 38` / `午饭花了38` / `收入 5000 工资` → 写 `data/ledger.json`（`_normalize_ledger`，含 cat 猜测：午饭→饮食、工资→工作）。
  - 待办：`提醒我 17:00 交周报` / `加一个待办 买牛奶` → `add_todo`（时间进 note，due=今天）。
  - 专注：`开始专注 25 分钟` / `番茄钟` → **不落盘**（避免虚增专注统计），由聊天侧用 QTimer 做结束提醒。
  - 防劫持：只在明确命令句式触发；疑问/感叹语气（吗/呢/?）或无金额的「记一笔」返回 None，走正常 AI 聊天。
- **接线 `peko/ui/chat.py`**：`ChatHandler._on_submit` 先 `nl_intent.parse`，命中则 `_handle_workspace_intent`（落盘 + 气泡确认，专注类再 `_schedule_focus_reminder` 用 `QTimer.singleShot` 提醒），未命中才走原 AI `stream_chat`。
- 数据一致性：`nl_intent.apply` 用 `PlansStore(__file__)`（peko/core 下 → 项目根 data/），而 PlansStore 每次读都重新从磁盘加载，故聊天写入与内嵌/网页版天然同一份。

### B3 完成回写桌宠（工作台完成 → 桌宠反馈）
- **新增 `peko/core/pet_bond.py`**（纯 Python）：靠谱值计数，原子写到 `data/pet_bond.json`（`{version,total,by_kind}`）。`record_completion(kind)` / `get_total()` / `get_by_kind()`。
- **新增 `peko/ui/pet_link.py`**：进程内单例 notifier（`QObject` + `workspace_completed(str kind, str label, int total)`）。`notify_completion(kind,label)` 先记靠谱值再发射信号；Qt 缺失时降级为仅计数。跨线程经 Qt 队列连接，槽函数在主线程执行。
- **桌宠反馈 `peko/ui/pet.py`**：`__init__` 连接 notifier → `_on_workspace_completed`；复用 `apply_mood_interaction("praise")` 拿情绪/浮字/动画/自动暂停，再把气泡换成「靠谱值 +1（当前 N）\n{类型}完成：{label}」。
- **触发源**（两路汇聚到 `pet_link.notify_completion`）：
  - 浏览器「工作台」：前端 `notifyCompletion()` 在 http 模式 `POST /api/event {kind,label}` → `workbench_server.py` 新端点调 `notify_completion`（新增 `_read_object` 读对象请求体）。
  - 内嵌「计划台」：前端 `notifyCompletion()` 在 bridge 模式调 `bridge.recordEvent(kind,label)` → `PlanBridge.recordEvent` 新槽调 `notify_completion`。
  - 前端触发点：计划/待办勾到 done（`markDone`）、习惯打卡（`toggleHabitDate` 仅打卡非取消）、专注记录（`logFocus`）。local 模式无桌宠不触发。

### 验证
- `py_compile` 全部改动文件通过。
- 新增单测 `unit_tests/test_nl_intent.py`（12 例：解析 + 落盘 + 防劫持 + 专注不落盘）、`unit_tests/test_pet_bond.py`（3 例：计数/持久化/坏文件恢复），连同 `test_mood.py` 全绿。
- B3 服务端通路实测：起本地服务后 `POST /api/event` → `{"ok":true,"total":1}` 且落盘 `data/pet_bond.json`（已清理测试残留）。
- `scripts/wb_modes_test.js` 三模式（local/bridge/http）回归 ALL PASS，无破坏；内联脚本 `node --check` 通过。
- 修复：`_parse_todo` 提取时间需在清理数字之前，否则 `17:00` 残留冒号。

### C5 体验优化：快捷按钮 + 模板填入（2026-08-14，非 AI 路线）
- **背景**：AI 功能不公测、API 相关不上线，新功能全部走非 AI，且要好理解好操作。
- **`peko/ui/input_dialog.py`**：聊天输入框新增「记账 / 待办 / 专注」快捷按钮（`QUICK_COMMANDS`）。点击即填入模板并**选中关键字段**（记账选中「午饭 38」、待办选中「17:00 交周报」、专注选中「25」），用户直接 typing 替换后发送。模板与 nl_intent 识别句式一一对应，必中非 AI 路径。附灰色小字用法提示；窗口调至 320×230。
- **`peko/core/nl_intent.py`**：新增 `suggest_usage(text)`——文本含命令触发词但 parse 未命中（如「记一笔」缺金额、「提醒我」缺内容）时返回用法模板提示。
- **`peko/ui/chat.py`**：`_on_submit` 在 parse 未命中后先查 `suggest_usage`，有提示则气泡展示模板（不走 AI）；AI 未配置的兜底文案改为引导用快捷按钮/指令（不再引导填 API Key）。
- **验证**：新增单测 4 例（快捷模板必命中 parse；suggest_usage 的提示/不提示边界），共 19 例全绿；py_compile 通过。

### C5 快捷按钮：拆分「记支出 / 记收入」（2026-08-14）
- **需求**：记账输入时标注「收入 / 支出」，便于用户理解。
- **做法**：`QUICK_COMMANDS` 把原「记账」按钮拆为「记支出」（模板 `记一笔 支出 午饭 38`，选中「午饭 38」）与「记收入」（模板 `记一笔 收入 兼职 500`，选中「兼职 500」）。模板里的「支出/收入」字样既标明类型，也教用户口语句式；nl_intent 原有逻辑按该词自动判 kind，且标题不含「支出/收入」。
- 按钮行去掉「快捷记录：」前缀标签（4 按钮在 320px 窗口内刚好放下）；输入框下方提示语同步展示收入/支出两种写法。
- `nl_intent._USAGE_HINT` 与 `chat.py` AI 未配置兜底文案同步更新为「记支出/记收入」版本。
- **验证**：单测 19 例全绿（快捷模板断言 kind=expense/income 且标题剔除类型词）；选中区间脚本核对精确（记支出选「午饭 38」、记收入选「兼职 500」、待办选「17:00 交周报」、专注选「25」）；py_compile 过。

## 桌宠「动画删除」：拖拽摧毁表演（2026-08-14）

> 灵感来自 MonsterDeleter（怪兽走过去→指文件→踹爆→飞离），按 Peko 常驻桌宠形态适配：
> 不需召唤/瞄准层，触发改为「把文件拖到宠物身上」。

### 决策（用户拍板）
- 触发：拖拽文件到宠物身上（非右键菜单/注册表）。
- 摧毁动作：`fight` 出拳（含蓄版，非 angry_fire 喷火）。
- 仅 BB（hamster）可用；neko 不做任何适配（后续会删除 neko）——代码用「无 fight 动作则婉拒」的能力检查天然覆盖。

### 实现
- **新增 `peko/ui/destroy_show.py`**：`DestroyShow` 五阶段回调链（全部 caller 侧编排，直接操作 pet.current_state，同 actions/control.py 约定）：
  1. **接住**：朝屏幕中心方向 `walk_right/left` + `QPropertyAnimation(pos)` 走 60px（700ms）。
  2. **确认**：`listen` + 气泡「要摧毁《xx》吗？」+ `_ConfirmDialog`（红「摧毁」/灰「算了」，样式同输入框）。
  3. **摧毁**：`fight` 播一遍，55% 处浮字「砰！」（复用 `_show_floating_effects`）+ `send2trash` 删文件。
  4. **庆祝**：`wave` + 气泡「已丢进回收站～」。
  5. **收场**：回 `stand`，`_auto_actions.resume()`。
  - 支持多文件拖入（确认文案「xx 等 N 个文件」，全部进回收站）；取消/失败均有对应气泡。
  - 守卫：表演中重入、操控/跟随模式、无 fight 动作、路径无效 → 各自气泡提示并拒绝。
- **`pet.py`**：`setAcceptDrops(True)` + `dragEnterEvent`/`dropEvent`（取本地文件路径 → `start_destroy_show`）+ `_destroy_running` 标志。
- **依赖**：`send2trash>=1.8.0` 入 requirements.txt，已装入系统 Python（桌宠运行时）。删除进回收站可恢复。

### 用到的动作（4 个，全部 BB 现有，零新素材）
`walk_right/walk_left`（走位）、`listen`（确认）、`fight`（摧毁）、`wave`（庆祝）；收场回 `stand`。

### 验证
- 新增 `unit_tests/test_destroy_show.py`（离屏 QT_QPA_PLATFORM=offscreen）：完整流程（文件进回收站+回 stand）、取消保留文件、无 fight 婉拒，3 例过。全套 37 例系统 Python 全绿。
- **测试环境特有坑**：离屏时确认窗是「最后一个可见窗口」，关闭它触发 `quitOnLastWindowClosed` 退出事件循环 → 后续 QTimer 全失效。测试必须 `setQuitOnLastWindowClosed(False)` + `pet.show()`。真实 App 宠物常显无此问题。

### 动画删除改版：托盘入口 + 选文件 + 跑过去摧毁（2026-08-14 v2）
- **需求变更**：去掉「拖拽到宠物身上」；改为托盘菜单「摧毁文件…」→ 文件选择框选文件 → 全屏引导层「点一下文件在屏幕上的位置」（十字准星，Esc 取消）→ 宠物长途跑过去 → listen 确认 → fight 摧毁 → wave 庆祝。
- **入口**：`tray.py` 新增 `_destroy_file_action` → `destroy_show.begin_destroy_flow(pet, pet)`（QFileDialog 多选 → `_TargetOverlay` 全屏半透明引导层取坐标 → `start_destroy_show_at(pet, paths, pos)`）。
- **长途走位**：`QPropertyAnimation(pos)` 平滑移动（时长按距离 0.8s~4s，OutQuad），停在目标侧边。关键：走路动作自带逐帧位移（update_position）会与属性动画叠加导致走过头——**冻结该动作的 moveSpeed**（`pet._state_config[state]["moveSpeed"]=0`，caller 侧临时调整，确认阶段恢复；`_UNSET` 哨兵区分原本未设置）。
- **「删除失败」bug 修复**：根因是 send2trash 现代（IFileOperation）/legacy 两条路都可能失败，且旧代码静默吞异常。现 `_trash_one` 双保险：send2trash → 回退 PowerShell（Microsoft.VisualBasic FileSystem DeleteFile，SendToRecycleBin）；每步成败 + 完整 traceback 打印控制台（`[Peko 摧毁]` 前缀）；失败气泡带简要原因。注意：WorkBuddy 沙箱 shim 会拦截删除（SAFE_DELETE_FAIL_CLOSED），从 WorkBuddy 终端启动的桌宠删除必失败——属环境拦截，气泡会提示「请从普通终端启动桌宠再试」。
- **测试**：`test_destroy_show.py` 改为新 API（`start_destroy_show_at` + 坐标），真实删除换成可确定的桩（os.remove），断言走位方向/停点（含屏幕钳制）/取消保留/无 fight 婉拒；新增 `_trash_one` 不存在文件分支。全套 38 例系统 Python 全绿。离屏虚拟屏较小会触发停点钳制，断言须复刻钳制公式。

### 动画删除 v3：狙击点选文件（2026-08-14）
- **需求**：不要文件对话框、不要屏幕变暗；红色准星 + 直接点击桌面/文件夹里的文件图标即选中（参考 MonsterDeleter 的狙击体验，但保留桌面可见性）。
- **新增 `peko/core/file_picker.py`**（点坐标 → 真实文件路径）：
  - `uiautomation.ControlFromPoint` 取点击处控件，向上找最近的有名字控件（优先 ListItem）作显示名；
  - `WindowFromPoint` + `GetAncestor(GA_ROOT)` 定位资源管理器顶层窗口，`Shell.Application` 取该窗口文件夹路径；点在桌面则搜 用户/公共 Desktop；
  - `match_name_in_folder` 两级匹配（全名 → 去扩展名，兼容「隐藏扩展名」设置）。
- **`_TargetOverlay` 改透明狙击层**：不变暗，仅顶部提示条 + 红色准星光标（QPixmap 手绘圆环+十字，参考 MonsterDeleter）。点击后**先 hide 遮罩再延迟 150ms 识别**（否则 ControlFromPoint 命中遮罩自己）。认不出 → 气泡提示 + 遮罩重开可再点，Esc 取消。
- **依赖**：requirements.txt 加 `uiautomation`（已装系统 Python 2.0.29）、`pywin32`。
- **测试**：新增 `FilePickerTests`（名称匹配纯函数：全名/去扩展名/大小写/不存在），managed Python 可跑；全套 39 例系统 Python 全绿，managed 36 例（1 个历史 test_main PyQt5 报错 + 4 个 Qt 守卫跳过）。UIA 识别部分需真实桌面，手动测试。

### 动画删除 v3.1：真机反馈修复（2026-08-14）
- **Esc 无法取消**：Tool 窗默认无键盘焦点 → `showEvent` 里 `activateWindow + setFocus + grabKeyboard`（hideEvent 释放），并补「右键=取消」兜底。
- **准星只在提示条范围生效**：双根因——(1) 全透明（alpha=0）区域在 Windows 上光标/点击穿透到下层 → 全屏刷 `QColor(0,0,0,1)` 不可见底色；(2) `primaryScreen().geometry()` 只盖主屏（用户双屏）→ 改 `QApplication.desktop().geometry()` 覆盖整个虚拟桌面；提示条居中于主屏。
- **摧毁动画延长到 3s**：fight 循环 3s（`DESTROY_DURATION_MS=3000`），命中点 `DESTROY_STRIKE_MS=1650`（浮字+删除）。
- **摧毁后跑回右下角**：新增 `_phase_walk_home`（老家坐标与 init_ui 一致：screen-width-20 / height-50），庆祝后走回再收场；取消也走回家。
- **重构**：走位抽成 `_walk_to(x, y, on_done)`（冻结 moveSpeed + 属性动画），`_frozen_speeds` 改 dict 支持多次走位。
- 测试：终态断言改为「回到右下角 + moveSpeed 已恢复」，超时放宽到 14s；全套 39 例系统 Python 全绿。
