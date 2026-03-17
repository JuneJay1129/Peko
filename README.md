# 🐈 Peko - AI 桌宠

可爱、可交互的桌面宠物，支持**多宠物模板**与**统一 API / 模型选择**。每个宠物独立配置，可快速新增仓鼠、小狗等新宠物；用户只需在**配置文件**中填写 API Key、选择模型即可与任意宠物对话。

---

## 🎮 功能概览

- **多宠物**：每个宠物独立配置（动画、人设、气泡样式、插槽），托盘内可切换
- **统一 API**：在配置文件中填写 Key、选择模型，所有宠物共用
- **快速新增宠物**：使用脚手架一条命令生成新宠物模板，放入资源即可
- **插槽**：公共插槽（如 AI 模型）、每宠物独立插槽（可扩展不同功能）
- **动画 / 气泡 / 快捷键**：L+Enter 对话、托盘显示/隐藏/停止移动
- **操控模式**：托盘选择「操控模式」后，用**方向键 ↑↓←→** 控制宠物移动、**空格** 待机，长按持续执行；**长时间无操作**（默认 15 秒）则自动循环播放该宠物的 **sleep** 动作，直到收到新指令后结束并重新计时（可扩展更多按键与动作）

---

## 🔧 安装与运行

- **环境**：Python 3.8+，PyQt5  
- **可选**：`openai`（OpenAI 兼容接口）、`sparkai`（讯飞星火）

```bash
pip install PyQt5 keyboard
pip install openai        # 使用 SiliconFlow / OpenAI / 豆包等
# 可选: pip install sparkai  # 使用讯飞星火
python main.py
```

---

## 📦 打包为可执行程序（Windows / macOS）

### 一次得到两个平台（推荐）

用 **GitHub Actions** 一次构建出 Windows 和 macOS 两个可执行程序：

1. 把本仓库推送到 GitHub（或已有仓库直接 push）。
2. 打开仓库 → **Actions** → 选择 **"Build Peko (Windows + macOS)"**。
3. 若未自动运行，点击 **Run workflow** 手动触发。
4. 跑完后在本次运行页面下方 **Artifacts** 中下载：
   - **Peko-Windows**：内含 `Peko.exe`（仅 Windows）
   - **Peko-macOS**：内含 **`Peko`**（单文件可执行程序，macOS 10.15+）

**macOS 使用**：解压后得到 **一个文件 `Peko`**（无后缀）。请把它放到**桌面**等目录，在终端执行：`chmod +x Peko` 然后 `./Peko`；或把 Peko 拖进终端窗口回车。不要从微信/QQ 下载目录直接运行。

推送 `main` 或 `master` 分支时也会自动触发该构建。

### 本机单独打包

- **Windows**：在项目根目录执行 `pyinstaller main.spec`，或双击 **`build.bat`**。产物：`dist/Peko.exe`。
- **macOS**：在项目根目录执行 `./build_mac.sh`。产物：**`dist/Peko`**（单文件，macOS 10.15+）。

**自定义 exe/应用图标**：在项目根目录放置 **`icon.ico`**（Windows）或 **`icon.icns`**（macOS），重新打包即可；未放置则使用系统默认图标。

首次运行 exe/可执行文件时，会在其**同目录**下自动创建 `config` 并写入 `api.json`、`secrets.json` 模板；在 `config/secrets.json` 中填写 API Key 即可使用。宠物资源已打进包内，无需单独携带 `pets` 目录。

---

## ⚙️ 配置 AI（config 模板 + 本地配置）

配置分为**可提交的模板**与**本地实际配置**（不提交，避免泄露 API Key）：

1. **复制模板**（首次使用）  
   - `config/api.json.example` → `config/api.json`（模型与 endpoint）  
   - `config/secrets.json.example` → `config/secrets.json`（API Key）
2. **填写 API Key**：在 **`config/secrets.json`** 中把 `"your-api-key-here"` 改成你的 API Key（SiliconFlow / OpenAI 等）。
3. **选择模型**：在 **`config/api.json`** 中设置 **modelId**，需与其中 `models` 列表里某一项的 `id` 一致（如 `1`、`qwen-72b`、`deepseek-v3` 等）。

`config/api.json` 与 `config/secrets.json` 已加入 `.gitignore`，仅本机存在；可推送的只有 `api.json.example` 和 `secrets.json.example`。

示例：

- **secrets.json**（仅本地，勿提交）：
```json
{
  "apiKey": "你的 API Key"
}
```

- **api.json** 顶层字段：
```json
{
  "modelId": "1",
  "defaultModel": "1",
  "models": [ ... ]
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
├── main.py                 # 入口：python main.py
├── peko/                   # 主包
│   ├── main.py             # 应用逻辑入口
│   ├── ui/                 # UI 组件
│   │   ├── pet.py          # 桌宠组件（宠物包 + 插槽）
│   │   ├── tray.py         # 托盘：显示/隐藏、切换宠物、退出
│   │   ├── input_dialog.py  # 对话输入框
│   │   └── api_settings_dialog.py  # API/模型设置对话框
│   ├── ai/                 # AI 服务
│   │   ├── config_loader.py # API/模型配置加载
│   │   └── service.py      # 统一 AI 调用（OpenAI 兼容 + 讯飞星火）
│   └── core/               # 核心逻辑
│       └── pet_manager.py  # 宠物包注册与发现
├── config/
│   ├── api.json.example    # 模型配置模板（可推送）
│   ├── secrets.json.example # API Key 模板（可推送）
│   ├── api.json             # 本地：模型选择（不提交）
│   └── secrets.json         # 本地：API Key（不提交）
├── pets/
│   └── <宠物id>/
│       ├── pet_config.json
│       └── resource/       # 该宠物专属资源（stand、walk_left、icon.png 等）
├── scripts/
│   ├── scaffold_pet.py     # 快速新增宠物脚手架
│   ├── devide_frames.py   # 分割精灵表为单帧
│   └── test_animation.py   # 动画预览测试
```

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
