# data/

本目录存放**本地运行数据**，不入版本库（`.gitignore` 里 `data/*` + `!data/README.md`）。

| 文件 | 内容 |
| --- | --- |
| `plans.json` | 工作台六模块数据（这是单一真相源，其余文件多为派生） |
| `todos.json` / `habits.json` / `ledger.json` / `review.json` | 待办、习惯打卡、记账、周月回顾 |
| `focus.json` | 专注记录：分钟数、标签、日期（网页番茄钟与聊天「开始专注」都写这里） |
| `mood_state.json` | 宠物心情 / 饱食 / 精力与互动计数 |
| `pet_bond.json` | 靠谱值 |
| `weather_cache.json` | 天气缓存 |
| `chat_history/` | 对话记录：`index.json` 会话索引、`conv_<id>.json` 消息、`memory.json` 长期记忆（称呼/喜好/习惯） |

删除后程序会按默认值重建，但历史台账与聊天记录不可恢复，迁移机器时记得手动拷贝。
