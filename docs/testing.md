# 测试

## 跑法

```bash
# 全量（在项目根目录）
.venv/Scripts/python.exe -m unittest discover -s unit_tests -q

# 单文件
.venv/Scripts/python.exe -m unittest unit_tests.test_relative_imports -v

# 单个用例
.venv/Scripts/python.exe -m unittest unit_tests.test_nl_intent.NlIntentTests.test_xxx -v
```

全绿时输出 `Ran 220 tests ... OK`，约 12 秒（`test_destroy_show` 占九成耗时）。

## 覆盖矩阵

| 文件 | 用例 | 覆盖对象 |
| --- | --- | --- |
| `test_nl_intent.py` | 36 | `peko/core/nl_intent.py` 非 AI 指令解析：记账、待办、专注、金额与时间词；待办截止日按时刻顺延 |
| `test_chat_store.py` | 9 | `peko/core/chat_store.py` 对话落盘：成对写入、空回复丢弃、超限裁剪（不留孤儿 assistant）、旧索引格式兼容、损坏文件恢复 |
| `test_context_builder.py` | 13 | `peko/core/context_builder.py` 上下文工程：system 分层、轮次与字符预算裁剪、连续同角色合并、工作台摘要与降级 |
| `test_user_memory.py` | 13 | `peko/core/user_memory.py` 长期记忆：称呼/喜好/厌恶/习惯抽取、去重覆盖、清空、损坏恢复 |
| `test_plans_store.py` | 3 | `peko/core/plans_store.py` 计划状态：勾选时记住原进度、取消完成还原（不再停在 100%）、进度跨重启不丢 |
| `test_bongo_keys.py` | 24 | `peko/core/bongo_keys.py` 按键归手与键帽映射：左右手分区、shift 符号、空格与中文交替、特殊键与未知键；数字/符号/功能键都要落到 60% 键盘的 61 个键帽 id 上，且 id 必须与 `bongo.svg` 对得上，F 区之类没画的键返回 None |
| `test_bongo_controller.py` | 13 | `peko/ui/bongo.py` 按键状态机：快速连打每次都要抬落（防止延迟回落吞动作）、长按去重、同手多键、release 丢失自愈；键帽高亮的点亮/熄灭/多键并存 |
| `test_bongo_layout.py` | 28 | `peko/ui/bongo.py` 叠加层几何：60% 键盘正对宠物、**整块绕中心旋转 180°**（Q 区在右、Enter 在左、数字行在最下面、空格那排在最上、键帽文字倒置），再**顺时针倾斜 8°**（右端下沉）+ **上窄下宽的透视**（`cap_center` 返回透视+倾斜之后的坐标）、五排倒序、每个键帽都有中心点；爪子跟到该手最近按下的键（左手落画面右爪，`PET_TO_SCREEN` 对调）、落在键帽上方不遮高亮、数字行也够得到、相邻键互相避让且**让位的是闲置那只手**、松手不弹回；`PianoStageTests` 只锁钢琴自己的舞台——素材自带桌面层、桌沿在 `bongo_stage.DESK_EDGE_Y=168`、琴身上沿不高于桌沿、身体不缩放不位移、倾斜参数与 60% 键盘一致、转 8° 后琴体四角仍在画布内（60% 键盘和键鼠仍是各自的老坐标，不在这里管） |
| `test_bongo_piano.py` | 18 | 钢琴造型：25 颗琴键（15 白 + 10 黑）命名与注册、同样**整块转 180°**（w0 在画面最右）、黑键从白键下缘凸出、双爪够得到任意一颗键；`random_caps` 按下就随机抽键（真实键位不参与）、没有键帽映射的方向键与没有左右归属的 F 区也照弹、空池时保持原行为；白键高亮不能把压在它上面的黑键抹掉（分层重绘） |
| `test_weather_anim.py` | 13 | `peko/core/weather_anim.py` 天气现象 → 宠物动作：判定顺序钉死（雷阵雨放打雷、雨夹雪放雪、暴雨放大雨，不能被「雨」抢先）、晴/多云与英文兜底、认不出或没有现象（本地估算）返回 None；素材发现按文件名里的**数字**排序（1,2,10 不能排成 1,10,2）、缺目录/缺参数静默返回空、六类动作在 BB 里都有帧 |
| `test_mood.py` | 6 | `peko/core/mood.py` 心情/饱食/精力状态机与衰减 |
| `test_destroy_show.py` | 5 | `peko/ui/destroy_show.py` 摧毁表演的步骤编排与异常分支（耗时最长） |
| `test_main.py` | 4 | `peko/main.py` 装配：托盘创建参数、警告调度 |
| `test_packaging_paths.py` | 4 | `peko/core/runtime_paths.py` 打包/开发两种环境的可写根解析 |
| `test_pet_bond.py` | 3 | `peko/core/pet_bond.py` 靠谱值计数与完成联动 |
| `test_relative_imports.py` | 2 | 全项目相对导入可解析；`pet_parts/` 禁止 `..core` / `..ai`（静态 AST 校验，不 import） |

## 约定

- 测试统一放 `unit_tests/`，文件名 `test_<模块>.py`，不依赖真实网络与用户 `data/` 内容。
- `peko/core` 不得 import PyQt5，业务层测试才能无 GUI 运行；需要 Qt 的用 `QT_QPA_PLATFORM=offscreen`。
- 涉及文件读写的测试用 `tempfile` 自建目录，禁止改动仓库里的 `data/`、`config/`。
- 导入类回归接 `test_relative_imports.py` 的静态校验，不要真的 import UI 模块。
