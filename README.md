# 🐈 Peko - AI 桌宠

可爱、可交互的桌面宠物，支持**多宠物模板**与**统一 API / 模型选择**。每个宠物独立配置，可快速新增仓鼠、小狗等新宠物；用户只需在**配置文件**中填写 API Key、选择模型即可与任意宠物对话。

---

## 🎮 功能概览

- **多宠物**：每个宠物独立配置（动画、人设、气泡样式、插槽），托盘内可切换
- **统一 API**：在配置文件中填写 Key、选择模型，所有宠物共用
- **快速新增宠物**：使用脚手架一条命令生成新宠物模板，放入资源即可
- **插槽**：公共插槽（如 AI 模型）、每宠物独立插槽（可扩展不同功能）
- **动画 / 气泡 / 快捷键**：L+Enter 对话、托盘显示/隐藏/停止移动

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

## ⚙️ 配置 AI（在 config/api.json 中填写）

在 **`config/api.json`** 中完成配置即可：

1. **apiKey**：填写你的 API Key（SiliconFlow / OpenAI 等）。
2. **modelId**：当前要使用的模型 ID，需与下方 `models` 列表中某一项的 `id` 一致（如 `qwen-72b`、`1`、`deepseek-v3` 等）。

同一文件中的 **models** 为可用的模型列表，可自行增删；**modelId** 必须为其中某个模型的 **id**。

示例（api.json 顶层字段）：

```json
{
  "apiKey": "你的 API Key",
  "modelId": "qwen-72b",
  "defaultModel": "qwen-72b",
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
- `resources/stand/`、`walk_left/` 等目录

**下一步**：将对应动画帧（如 `0.png`, `1.png`）放入 `pets/<id>/resources/stand/` 等目录，或修改 `pet_config.json` 中 `animations` 的路径指向已有资源（如项目根 `resources/`）。然后运行 `python main.py`，在托盘「切换宠物」中选择新宠物。

---

## 📁 项目结构（重构后）

```
Peko/
├── main.py                 # 入口：加载宠物包、托盘、快捷键
├── pet.py                  # 桌宠组件（宠物包 + 插槽）
├── pet_manager.py          # 宠物包注册与发现
├── api_config_loader.py    # API/模型配置加载
├── ai_service.py           # 统一 AI 调用（OpenAI 兼容 + 讯飞星火）
├── api_settings_dialog.py  # API/模型设置对话框（可选）
├── tray.py                 # 托盘：显示/隐藏、切换宠物、退出
├── input_dialog.py         # 对话输入框
├── config/
│   └── api.json            # AI 配置：apiKey、modelId、模型列表（可编辑）
├── pets/
│   ├── neko/
│   │   └── pet_config.json # 默认小猫（动画指向根目录 resources/）
│   └── <宠物id>/
│       ├── pet_config.json
│       └── resources/      # 可选：该宠物专属帧
├── scripts/
│   └── scaffold_pet.py     # 快速新增宠物脚手架
└── resources/              # 默认 Neko 动画资源
```

---

## 🐱 宠物配置说明（pet_config.json）

| 字段 | 说明 |
|------|------|
| `id` / `name` | 唯一 id、显示名称 |
| `character.systemPrompt` | 对话人设（系统提示词） |
| `animations` | 各状态对应图片路径列表（相对宠物目录或项目根） |
| `bubbleStyle` | 气泡样式（backgroundColor、border、fontSize 等） |
| `slots` | 该宠物独立插槽（预留扩展） |

公共能力（如调用 AI 模型）通过全局配置与 `ai_service` 提供，无需在每个宠物里重复配置。

---

## 📌 后续可扩展

- 更多公共插槽：如主题、快捷键、多语言
- 每宠物插槽：如心情值、喂食、小游戏
- 讯飞星火在设置中支持 APP_ID / KEY / SECRET 或环境变量

---

## 💖 许可

MIT License.
