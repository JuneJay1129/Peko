# 🐹 Peko - AI 桌宠

可爱、可交互的桌面宠物，支持**多宠物模板**与**统一 API / 模型选择**。每个宠物独立配置，可快速新增仓鼠、小狗等新宠物；用户只需在**配置文件**中填写 API Key、选择模型即可与任意宠物对话。

---

## 🎮 功能概览

- **多宠物**：每个宠物独立配置（动画、人设、气泡样式、插槽），托盘内可切换
- **统一 API**：在配置文件中填写 Key、选择模型，所有宠物共用
- **快速新增宠物**：使用脚手架一条命令生成新宠物模板，放入资源即可
- **插槽**：公共插槽（如 AI 模型）、每宠物独立插槽（可扩展不同功能）
- **动画 / 气泡 / 快捷键**：L+Enter 对话、托盘显示/隐藏/停止移动
- **操控模式**：托盘选择「操控模式」后，用**方向键 ↑↓←→** 控制宠物移动、**空格** 待机，长按持续执行；**长时间无操作**（默认 15 秒）则自动循环播放该宠物的 **sleep** 动作，直到收到新指令后结束并重新计时（可扩展更多按键与动作）
- **个人工作台**：计划台 / 待办清单 / 习惯打卡 / 记账 / 专注 / 周月回顾六大模块；托盘「计划台」内嵌窗与「工作台」网页版双入口，共用同一份本地数据、实时同步
- **快捷指令（无需 AI）**：对话输入框内置「记支出 / 记收入 / 待办 / 专注」快捷按钮，自动填入模板并选中关键字段，改几个字即发；也可直接输入「记一笔 支出 午饭 38」「提醒我 17:00 交周报」「开始专注 25 分钟」这类口语指令，自动落入工作台对应模块
- **完成联动**：在工作台完成待办 / 打卡习惯 / 记录专注时，宠物即时给出情绪 + 动画反馈，并累计「靠谱值」
- **动画删除**：托盘「摧毁文件…」→ 红色狙击准星直接点选桌面 / 文件夹里的文件图标 → 宠物长途跑过去确认、出拳「摧毁」并送入回收站（可恢复），随后自行跑回桌面右下角
- **天气播报**：托盘「查询城市天气…」输入城市名即可直查（无需 API Key），聊天框也能问；实时源失败时按缓存 → 本地推断逐级降级
- **外观主题**：设置页切换主题后，宠物气泡、侧面操作面板、托盘菜单（macOS 含 Dock 菜单）同步换色

---

## 🔧 安装与运行

- **环境**：Python 3.8+，Windows / macOS
- **可选**：`sparkai`（讯飞星火）

```bash
pip install -r requirements.txt   # PyQt5、PyQtWebEngine、send2trash、uiautomation 等
# 可选: pip install sparkai       # 使用讯飞星火
python main.py
```

> 「摧毁文件」功能目前仅支持 Windows（依赖回收站与 UI Automation）。

---

## 📦 打包为可执行程序（Windows / macOS）

### 一次得到两个平台（推荐）

用 **GitHub Actions** 一次构建出 Windows 和 macOS 两个可执行程序：

1. 把本仓库推送到 GitHub（或已有仓库直接 push）。
2. 打开仓库 → **Actions** → 选择 **"Build Peko (Windows + macOS)"**。
3. 若未自动运行，点击 **Run workflow** 手动触发。
4. 跑完后在本次运行页面下方 **Artifacts** 中下载：
   - **Peko-Windows**：内含 `Peko.exe`（仅 Windows）
   - **Peko-macOS**：内含 **`Peko.app` 的压缩包**（macOS 10.15+）

**macOS 使用**：解压后得到 **`Peko.app`**。将它拷贝到本地后直接在 Finder 中双击运行即可；若首次运行被 Gatekeeper 拦截，请在“系统设置 → 隐私与安全性”中允许后再次打开。不要直接从微信/QQ 下载目录内运行。

推送 `main` 或 `master` 分支时也会自动触发该构建。

### 本机单独打包

- **Windows**：在项目根目录执行 `packaging\build.bat`。产物：`dist/Peko.exe`。
- **macOS**：在项目根目录执行 `bash packaging/build_mac.sh`。产物：**`dist/Peko.app`**（可双击运行的应用包，macOS 10.15+）。

**自定义 exe/应用图标**：在项目根目录放置 **`icon.ico`**（Windows）或 **`icon.icns`**（macOS），重新打包即可；未放置则使用系统默认图标。

首次运行 Windows exe 时，会在其**所在目录**下自动创建 `config` 并写入 `api.json`、`secrets.json` 模板；首次运行 macOS `Peko.app` 时，会在 `~/Library/Application Support/Peko/config` 自动创建配置模板；之后在托盘「AI 设置」里填 API URL / Key / 模型名即可使用。宠物资源已打进包内，无需单独携带 `pets` 目录。

---

## ⚙️ 配置 AI（通用三要素：URL + Key + 模型名）

Peko 对接**任意 OpenAI 兼容服务**（SiliconFlow / DeepSeek / Kimi / GLM / 通义 / OpenRouter / 本地 Ollama 等），只需三要素：

1. **API URL**：完整请求地址，如 `https://api.siliconflow.cn/v1/chat/completions`
2. **API Key**：你的密钥（写在 `config/secrets.json`，不提交）
3. **模型名**：如 `deepseek-ai/DeepSeek-V3.2`、`gpt-4o`、`deepseek-chat`

**推荐方式**：托盘菜单 →「AI 设置」，在页面里填入 URL / Key / 模型名，可先点「测试连接」验证，再「保存并应用」。

**手动方式**：把模板复制为本地配置后编辑：
- `config/api.json.example` → `config/api.json`（填 `apiUrl` 与 `model`）
- `config/secrets.json.example` → `config/secrets.json`（填 `apiKey`）

旧版 `models` 数组格式会自动迁移为新格式。`config/api.json` 与 `config/secrets.json` 已加入 `.gitignore`，仅本机存在；可推送的只有 `api.json.example` 和 `secrets.json.example`。

示例：

- **api.json**（URL 与模型名）：
```json
{
  "version": "2.0.0",
  "apiUrl": "https://api.siliconflow.cn/v1/chat/completions",
  "model": "deepseek-ai/DeepSeek-V3.2",
  "temperature": 0.8,
  "maxTokens": 2000
}
```

- **secrets.json**（API Key，仅本地勿提交）：
```json
{
  "apiKey": "你的 API Key"
}
```


---

## 🐾 快速新增一只新宠物（脚手架）

与 SimuEngine 的「快速新增话题」类似，在项目根目录执行：

```bash
python scripts/scaffold_pet.py <宠物id> "<宠物名称>" "[作者]"
```

示例：

```bash
python scripts/scaffold_pet.py hamster "仓鼠"
python scripts/scaffold_pet.py dog "小狗" "我"
```

会在 `pets/<宠物id>/` 下生成：

- `pet_config.json`：id、name、character（人设 systemPrompt）、animations、bubbleStyle、slots
- `resource/stand/`、`walk_left/` 等目录

**下一步**：将对应动画帧（如 `0.png`, `1.png`）放入 `pets/<id>/resource/stand/` 等目录。每个宠物独立 `resource` 和 `animations`，无公共模块。然后运行 `python main.py`，在托盘「切换宠物」中选择新宠物。

---

## 📁 项目结构

```
Peko/
├── main.py                     # 入口：python main.py
├── requirements.txt
├── packaging/                  # 打包脚本与 PyInstaller 配置
│   ├── build.bat               # Windows 本地打包
│   ├── build_mac.sh            # macOS 本地打包
│   ├── build_mac_universal.sh  # macOS 通用二进制
│   └── main.spec               # PyInstaller 配置
├── peko/
│   ├── main.py                 # 应用装配：QApplication + 宠物包 + 托盘 + 热键
│   ├── core/                   # 纯 Python 业务层（不依赖 PyQt5，可单测）
│   │   ├── config_store.py     # JSON 读写门面（config/ 用户设置 vs data/ 运行状态）
│   │   ├── bus.py              # 进程内事件总线（theme_changed）
│   │   ├── pet_registry.py     # 主宠 / 分身注册中心
│   │   ├── effect_state.py     # 特效选择持久化（config/effects.json）
│   │   ├── runtime_paths.py    # 源码态 / 冻结态可写目录与图标查找
│   │   ├── pet_manager.py      # 宠物包发现与加载
│   │   ├── mood.py             # 心情 / 饱食 / 精力状态机
│   │   ├── comfort.py          # 安慰打气对话状态机
│   │   ├── nl_intent.py        # 口语指令 → 工作台写入
│   │   ├── plans_store.py      # 工作台数据层（六模块，原子写）
│   │   ├── pet_bond.py         # 靠谱值计数
│   │   ├── weather.py          # 天气获取 / 缓存 / 降级
│   │   ├── appearance.py       # 外观主题注册与持久化
│   │   └── file_picker.py      # 狙击点选文件识别
│   ├── ui/                     # 界面层（唯一依赖 PyQt5）
│   │   ├── pet.py              # DesktopPet：窗口 / 动画帧 / 拖拽 / Mixin 组装
│   │   ├── pet_parts/          # DesktopPet 拆出的五个 Mixin + 气泡样式函数
│   │   │   ├── bubbles.py      # 气泡 + 打字机
│   │   │   ├── bubble_style.py # 气泡 / 侧栏 QSS（纯函数）
│   │   │   ├── comfort_flow.py # 安慰对话流程
│   │   │   ├── interaction_panel.py  # 心情面板 / 飘字
│   │   │   ├── sayings.py      # 随机文案
│   │   │   └── state_params.py # 帧率 / 动作参数 / 缩放
│   │   ├── tray.py             # 托盘 + macOS Dock 菜单（_MENU_SPEC 同源）
│   │   ├── style_kit.py        # 色板 / 字体 / 通用 QSS
│   │   ├── settings_dialog.py  # 设置页（切主题广播 theme_changed）
│   │   ├── chat.py             # 对话窗口
│   │   ├── input_dialog.py     # 对话输入框（快捷指令）
│   │   ├── mood_dialog.py      # 心情面板
│   │   ├── action_params_dialog.py  # 动作参数调节
│   │   ├── effects.py          # 特效装饰系统
│   │   ├── follower.py         # 召唤跟班
│   │   ├── destroy_show.py     # 摧毁表演编排
│   │   ├── weather_report.py   # 天气播报入口
│   │   ├── pet_link.py         # 工作台完成事件 → 宠物反馈
│   │   ├── plans_web_dialog.py # 内嵌工作台窗口（QWebChannel）
│   │   ├── plans/plans_web.html # 单文件工作台前端
│   │   └── workbench_server.py # 本地同步服务（127.0.0.1:18340）
│   └── ai/
│       ├── config_loader.py    # AI 三要素配置（含 v1→v2 迁移）
│       └── service.py          # OpenAI 兼容调用
├── pets/<宠物id>/              # 每个宠物独立 pet_config.json + resource/
├── config/                     # 用户设置：appearance / effects / api / secrets
├── data/                       # 运行状态与工作台数据：plans / todos / habits / ledger / review / focus / mood_state / weather_cache（不入库）
├── unit_tests/                 # 55 个单元测试（见 docs/testing.md）
├── docs/
│   ├── architecture.md         # 分层与模块职责
│   ├── testing.md              # 测试跑法与覆盖矩阵
│   └── archive/                # 过时设计稿
└── scripts/
    ├── scaffold_pet.py         # 新增宠物脚手架
    ├── devide_frames.py        # 精灵表切帧
    └── _wb_server_runner.py    # 独立启动工作台服务
```

分层与模块职责、测试覆盖矩阵见 [`docs/architecture.md`](docs/architecture.md) 与 [`docs/testing.md`](docs/testing.md)；2026-08 的工作台设计稿已归档到 [`docs/archive/`](docs/archive/)。

---

## 📦 宠物资源说明

每个宠物**独立**拥有自己的 `resource/` 和 `animations` 配置，无公共 resources 模块。`pet_config.json` 中的路径（如 `resource/stand/0.png`）均相对该宠物目录 `pets/<id>/` 解析。

- 动画帧：`resource/stand/`、`resource/walk_left/` 等
- 托盘图标：`resource/icon.png`（可选，缺省时使用 stand 首帧）

若之前使用过项目根 `resources/`，请将对应文件移入各宠物的 `pets/<id>/resource/` 下。

---

## 🐱 宠物配置说明（pet_config.json）

| 字段 | 说明 |
|------|------|
| `id` / `name` | 唯一 id、显示名称 |
| `character.systemPrompt` | 对话人设（系统提示词） |
| `animations` | 各状态对应图片路径列表（相对宠物目录，如 `resource/stand/0.png`） |
| `actionConfig` | 动作时间配置：`stateSwitchInterval`（状态切换间隔 ms）、`frameRate`（帧率）、`moveSpeed`（移动速度） |
| `cloneModeActions` | 分身模式下可随机到的动作列表。不配置则使用默认：站立 + 左右走 + 所有原地动作。每一项可为字符串（仅指定动作）或对象（可覆写该动作在分身模式下的 `frameRate`/`stateSwitchInterval`）：`{"state":"walk_left","frameRate":12,"stateSwitchInterval":1500}` |
| `cloneModeActionJitter` | 分身模式动作属性随机抖动（每个分身一组随机系数），用于让同一动作在不同宠物上表现略有差异。字段示例：`{"frameRatePct":0.2,"stateSwitchIntervalPct":0.2,"moveSpeedPct":0.2}`（*Pct* 支持 0~1 或 0~100）|
| `bubbleStyle` | 气泡样式（backgroundColor、border、fontSize 等） |
| `actionDisplayNames` | 可选。动作 key→显示名映射，用于「动作参数」面板；未配置的 key 显示为 key 本身 |
| `slots` | 该宠物独立插槽（预留扩展） |

**actionConfig 动作时间**（可选）：
- `stateSwitchInterval`：状态切换等待时间（毫秒），默认 3000
- `frameRate`：动画帧率（帧/秒），默认使用 main 传入值
- `moveSpeed`：行走时每帧移动像素数，默认 5

**animations 动作说明**：
- **公共动作**：`stand`（站立）、`walk_left/right/up/down`（行走会位移）、`dragged`（拖拽时）
- **自定义动作**：在 `animations` 中新增任意 key（如 `wave`、`eat`），配置对应 `resource/` 路径即可参与随机切换，原地播放不位移
- **动作专属气泡**：每个动作可配置 `bubble`（字符串）或 `bubbles`（字符串数组）。在随机动作模式或分身模式下切换到该动作时，若当前无气泡则弹出对应文案；不配置或为空则不弹。与 `randomSayings` 互斥（有气泡显示时随机文案会延后）
- **快速三击触发 fight**：在自动模式（非操控/非跟随鼠标）下，在宠物上**快速点击 3 次及以上**（约 0.5 秒内、位移小于约 15px 视为一次点击），若该宠物配置了 `fight` 动作，会切换到 `fight` 并播放，播放时长由该动作的 `stateSwitchInterval` 控制，结束后恢复随机动作。

公共能力（如调用 AI 模型）通过全局配置与 `ai_service` 提供，无需在每个宠物里重复配置。

---

## 📌 后续可扩展

- 更多公共插槽：如主题、快捷键、多语言
- 每宠物插槽：如心情值、喂食、小游戏
- 讯飞星火在设置中支持 APP_ID / KEY / SECRET 或环境变量

---

## 💖 许可

MIT License.
