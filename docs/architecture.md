# Peko 架构说明

桌面桌宠（PyQt5）+ 个人计划工作台的完整分层与模块职责。当前结构对应 2026-09 那轮重构（配置读写收敛、`DesktopPet` 拆 Mixin、事件总线与宠物注册中心）。

## 1. 总体分层

```
入口层   main.py / peko/main.py          启动 QApplication、加载宠物包、装配托盘与热键
界面层   peko/ui/                        窗口、托盘、对话框、特效；唯一依赖 PyQt5 的层
拆分件   peko/ui/pet_parts/              DesktopPet 的六个 Mixin（阶段 B）
基建层   peko/core/{config_store,bus,pet_registry,effect_state}.py + peko/ui/style_kit.py
业务层   peko/core/                      心情、舒适对话、计划数据、天气、意图解析、宠物包管理
模型层   peko/ai/                        OpenAI 兼容调用与配置加载
资源     pets/<id>/resource/             每个宠物独立帧图，无公共资源目录
数据     config/ 用户设置，data/ 运行状态
```

依赖方向单向：`ui → core → runtime_paths`。`peko/core` 除 `style_kit` 位于 `ui/` 外全部为纯 Python，不 import PyQt5，因此可直接单测。

## 2. 四项基建（阶段 A / C）

### 2.1 config_store —— JSON 读写门面（新模块优先用）

```python
from peko.core import config_store
config_store.read_json("data/foo.json", default={})   # 读不到/损坏 → default，绝不抛异常
config_store.write_json("data/foo.json", data)        # 自动建目录 + 临时文件原子替换，失败返回 False
```

现状：只有 `effect_state.py` 迁入。`appearance` / `mood` / `plans_store` / `weather` /
`config_loader` 仍是各自手写 `open` + `json`，按需迁移，不强求一次性铺开——新写的持久化代码请直接用它。

`rel_path` 一律用 `/` 分隔，首段决定语义：

| 首段 | 语义 | 判断标准 | 例子 |
| --- | --- | --- | --- |
| `config/` | 用户设置 | 改了影响行为、用户可能手工编辑 | `appearance.json`、`effects.json`、`api.json` |
| `data/` | 运行状态 | 程序自管、删掉可再生成 | `mood_state.json`、`weather_cache.json`、`plans.json` |

历史遗留：`config/mood_state.json` 是迁移前的位置，`MoodStore` 首次加载时自动复制到 `data/`，旧文件保留不删。

### 2.2 effect_state —— 特效选择持久化

```python
effect_state.get_current() -> str      # 读 config/effects.json 的 current
effect_state.set_current(name) -> bool
```

此前 `main.py` 与 `tray.py` 各自实现过三份同样的读写，现已全部改为调用此模块。

### 2.3 bus —— 进程内事件总线

```python
from peko.core.bus import bus
bus.subscribe("theme_changed", self._on_theme_changed)
bus.unsubscribe("theme_changed", self._on_theme_changed)   # 组件关闭时退订，防泄漏
bus.emit("theme_changed", "dark")
```

- 回调在 `emit` 的调用线程同步执行；跨线程更新 UI 仍走 Qt 信号。
- 单个回调抛异常只打印 `[Bus] ...` 日志，不影响其它订阅者。
- 纯 Python、不依赖 Qt，可直接单测。

当前唯一事件 `theme_changed(key)`：

| 角色 | 代码位置 |
| --- | --- |
| 发布 | `peko/ui/settings_dialog.py` 切换主题后 `bus.emit("theme_changed", key)` |
| 订阅 | `peko/ui/pet.py` → `refresh_theme`（气泡 + 侧栏） |
| 订阅 | `peko/ui/tray.py` → `_on_theme_changed`（托盘 / Dock 菜单配色） |

新增可刷新组件时只需订阅，不必再改设置页，这是替换「手工逐个调 `refresh_theme`」的原因。

### 2.4 pet_registry —— 当前宠物注册中心

```python
registry = PetRegistry()
registry.set_master(pet)          # 替换主宠
registry.set_clones(clone_pets)   # 引用同一列表：原地增删自动同步
registry.current()                # 当前主宠，可能为 None
registry.clones() / registry.all_pets()
registry.on_master_replaced(fn)   # 主宠变更回调（含旧、新）
```

替代旧的 `pet_holder = [pet]` 闭包共享约定（`pet_holder[0] is 主宠`）。传参时传 `registry`，取用一律 `registry.current()`，并判空。

### 2.5 style_kit —— 样式唯一出口

```python
style_kit.palette()            # 当前主题色板 dict（bg / card / ink / ink_soft / border / accent / accent_hover）
style_kit.font_family()        # 跨平台字体族
style_kit.app_font(size, bold) # QFont 便捷构造（惰性 import Qt）
style_kit.menu_qss()           # 托盘 / Dock 菜单 QSS
style_kit.input_dialog_qss()   # QInputDialog 主题化 QSS
```

各弹窗不再各自写 `try/except` 兜底色板；缺主题时的默认值只在 `palette()` 里维护一份。

## 3. DesktopPet 的 Mixin 拆分（阶段 B）

`peko/ui/pet.py` 只保留窗口、动画帧、拖拽与组装，其余职责拆到 `pet_parts/`：

| Mixin | 文件 | 职责 |
| --- | --- | --- |
| `BubbleMixin` | `bubbles.py` | 普通气泡、打字机、主题应用、气泡定位 |
| `ComfortFlowMixin` | `comfort_flow.py` | 头顶气泡多轮安慰对话 + 侧面面板 |
| `InteractionPanelMixin` | `interaction_panel.py` | 心情面板开关、互动锁定、飘字动画 |
| `SayingsMixin` | `sayings.py` | 闲时随机说话与动作气泡 |
| `StateParamsMixin` | `state_params.py` | 帧率 / 动作参数 / 显示缩放 |

另有 `bubble_style.py`：气泡 / 侧栏 QSS 的纯函数模块（不是 Mixin），由 `bubbles.py` 调用。

组合方式：

```python
class DesktopPet(BubbleMixin, ComfortFlowMixin, SayingsMixin,
                 StateParamsMixin, InteractionPanelMixin, QWidget):
```

Mixin 之间通过 `self` 共享状态，不反向 import `pet.py`，避免循环依赖。拆分保证行为等价——判断标准是 MRO 顺序不变、方法名不变。

## 4. 启动与运行形态

`main.py`（根目录）→ `peko/main.py`：

1. `QApplication` + `setQuitOnLastWindowClosed(False)`（托盘常驻）。
2. `pet_manager` 发现 `pets/*/pet_config.json`，按默认 id 加载主宠，`PetRegistry.set_master`。
3. 创建托盘 `TrayIcon(app, registry, ...)`，系统托盘不可用时返回 `None` 并降级。
4. 注册全局热键；分身模式下按 `cloneModeActions` 创建多个宠物实例。

工作台两种形态：

- 托盘「计划台」→ `plans_web_dialog.py` 内嵌 `QWebEngineView`。
- 托盘「工作台」→ 系统浏览器打开 `plans_web.html`。
- 两者由 `workbench_server.py` 的 `ThreadingHTTPServer`（`127.0.0.1:18340`）共享同一份 `data/*.json`，实现双向同步（内嵌 2s、网页 3s 轮询）。

## 5. 托盘菜单同源

`peko/ui/tray.py` 用 `_MENU_SPEC` 描述菜单结构，`_build_menu_from_spec(owner, menu, dock)` 同时构建托盘菜单与 macOS Dock 菜单：

```python
("action", 属性名)                    # QAction
("sep",)                              # 分隔线
("submenu", 显示名, 填充器, (托盘属性, Dock 属性))
```

新增功能只需在 action 创建区加一个 QAction 并在 `_MENU_SPEC` 注册一行，两个入口自动同步，不会再出现「托盘有、Dock 漏」的问题。

## 6. 数据文件

| 路径 | 模块 | 入库 |
| --- | --- | --- |
| `config/api.json` / `config/secrets.json` | AI 三要素 | 否（`.gitignore`） |
| `config/api.json.example` / `secrets.json.example` | 模板 | 是 |
| `config/appearance.json` | 主题 | 是 |
| `config/effects.json` | 特效选择 | 否（运行状态） |
| `config/weather.json` | 天气城市记忆 | 否 |
| `data/plans.json` `todos.json` `habits.json` `ledger.json` `review.json` `focus.json` | 工作台六模块（`{version, items}`） | 否 |
| `data/pet_bond.json` | 靠谱值 | 否 |
| `data/mood_state.json` | 心情状态 | 否（运行状态） |
| `data/weather_cache.json` | 天气缓存 | 否（运行状态） |
| `data/chat_history/*.json` | 对话记录 | 否 |

`data/` 整目录被 `.gitignore` 的 `data/*` 排除（仅 `data/README.md` 入库），本地数据不进版本库。

改 `data/*.json` 请走 `plans_store` / `workbench_server`；新写的持久化代码用 `config_store`，不要手写 `open()`。

## 7. 既有约束与坑

- `plans_store.py` 有且只能有一个 `class PlansStore:`，重复定义会遮蔽原类导致方法丢失，改完用 `py_compile` + grep 自查。
- 所有持久化写必须原子（临时文件 + `os.replace`），`config_store.write_json` 已内置。
- `peko/core` 不得 import PyQt5，否则单测无法在无 GUI 环境运行。
- `peko/ui/pet_parts/` 位于 `peko/ui/` 下一层，引用 `peko.core` / `peko.ai` 必须用绝对导入（`from peko.core import ...`）。从 `pet.py` 搬过来的 `from ..core` 会解析成 `peko.ui.core` 而不存在——被 `try/except` 吞掉时只表现为主题跟随失效，没被吞的那处会让整个进程 abort（`unit_tests/test_relative_imports.py` 已固化该约束）。
- 宠物包资源路径相对 `pets/<id>/` 解析，不存在公共 `resources/`。
- 全局热键与托盘回调里取宠物必须先 `registry.current()` 判空。

## 8. 文档索引

- 测试与跑法：[`docs/testing.md`](testing.md)
- 历史架构（2026-08，工作台专项，已过时）：[`docs/archive/architecture-2026-08.md`](archive/architecture-2026-08.md)
- 项目总览与安装：[`README.md`](../README.md)
