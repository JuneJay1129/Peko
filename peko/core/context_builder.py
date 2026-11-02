"""
上下文工程：把「人设、宠物状态、用户长期记忆、今日工作台进展、最近对话」
按预算组装成一次请求的 `messages`。

三条原则：

1. **稳定信息进 system，易变信息靠后**：人设 → 长期记忆 → 当前状态 →
   最近对话 → 本次提问。越靠前的越不容易被裁掉，也越省 token 缓存。
2. **预算是硬约束**：中文大致 1 字 ≈ 1 token，按字符数粗估即可（不引 tokenizer，
   为了给 PyQt 桌面端省依赖）。超预算时从**最旧的整轮对话**开始丢，
   system 与本次提问永不裁剪。
3. **对话按轮裁剪**：绝不从 assistant 中间开始，否则模型会接着半句话往下编。
   裁完若首条不是 user，就再丢一条。

纯 Python、不依赖 Qt，可直接单测。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

# 单次请求的上下文字符预算（含 system + 历史 + 本次提问）
DEFAULT_CHAR_BUDGET = 6000
# 默认带最近几轮对话（一轮 = 一次提问 + 一次回复）
DEFAULT_TURNS = 8

DEFAULT_REPLY_RULES = (
    "- 用中文口语回答，1~3 句就够，不要用 Markdown 列表、标题或表情符号堆砌\n"
    "- 你是在桌宠头顶的小气泡里说话，太长会被截断\n"
    "- 不确定的事直说不知道，不要编造\n"
    "- 别自称「AI 助手」，你就是这只宠物本人"
)


def _period(hour: int) -> str:
    if 5 <= hour < 9:
        return "清晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 23:
        return "晚上"
    return "深夜"


def build_system_prompt(
    base_prompt: str,
    *,
    mood_context: str = "",
    workspace_digest: str = "",
    memory_text: str = "",
    now: Optional[datetime] = None,
    reply_rules: str = DEFAULT_REPLY_RULES,
) -> str:
    """组装 system：人设在最前（模型最重视），状态与记忆在后，规则收尾。"""
    blocks: List[str] = []
    base = (base_prompt or "").strip()
    if base:
        blocks.append(base)

    moment = now or datetime.now()
    state_lines = ["现在是 %s（%s）。" % (moment.strftime("%Y-%m-%d %H:%M"), _period(moment.hour))]
    mood = (mood_context or "").strip()
    if mood:
        state_lines.append(mood)
    digest = (workspace_digest or "").strip()
    if digest:
        state_lines.append("用户今天的工作台状态：%s。" % digest)
    if state_lines:
        blocks.append("## 当前状态\n" + "\n".join("- " + line for line in state_lines))

    memory = (memory_text or "").strip()
    if memory:
        blocks.append("## 关于用户（长期记忆）\n" + memory)

    if (reply_rules or "").strip():
        blocks.append("## 回复要求\n" + reply_rules.strip())
    return "\n\n".join(blocks)


def _clean_history(history: Optional[Iterable[Any]]) -> List[Dict[str, str]]:
    cleaned: List[Dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    return cleaned


def _merge_consecutive(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """合并连续同角色消息：部分模型对「连续两条 user」表现不稳定。"""
    merged: List[Dict[str, str]] = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] = merged[-1]["content"] + "\n" + msg["content"]
        else:
            merged.append(dict(msg))
    return merged


def pick_history(
    history: Optional[Iterable[Any]],
    *,
    turns: int = DEFAULT_TURNS,
    char_budget: int = DEFAULT_CHAR_BUDGET,
) -> List[Dict[str, str]]:
    """按轮数与字符预算挑选历史；返回可直接拼进 messages 的列表。"""
    cleaned = _clean_history(history)
    if not cleaned:
        return []
    # 先限定「最近 N 轮」，再从新往旧累加字符
    tail = cleaned[-(max(1, int(turns)) * 2):]
    picked: List[Dict[str, str]] = []
    used = 0
    for msg in reversed(tail):
        cost = len(msg["content"])
        if picked and used + cost > char_budget:
            break
        picked.append(msg)
        used += cost
    picked.reverse()
    # 不能以 assistant 开头，否则上下文里出现「无头回复」
    while picked and picked[0]["role"] != "user":
        picked.pop(0)
    return _merge_consecutive(picked)


def build_messages(
    user_text: str,
    system_prompt: str,
    history: Optional[Iterable[Any]] = None,
    *,
    char_budget: int = DEFAULT_CHAR_BUDGET,
    turns: int = DEFAULT_TURNS,
) -> List[Dict[str, str]]:
    """最终产物：system + 裁剪后的历史 + 本次提问。"""
    system_prompt = (system_prompt or "").strip()
    user_text = (user_text or "").strip()
    budget = max(400, int(char_budget))
    remain = max(200, budget - len(system_prompt) - len(user_text))
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(pick_history(history, turns=turns, char_budget=remain))
    if user_text:
        messages.append({"role": "user", "content": user_text})
    return messages


def digest_workspace(store: Any = None, today: Optional[str] = None) -> str:
    """把今日工作台进展压成一句话，让宠物「知道你在忙什么」。

    读盘失败、模块缺失都返回空串——上下文增强永远不能拖垮一次对话。
    """
    try:
        if store is None:
            from .plans_store import PlansStore

            store = PlansStore()
        day = today
        if day is None:
            from .plans_store import today_str

            day = today_str()
        parts: List[str] = []

        todos = [t for t in (store.todos() or []) if t.get("status") == "pending"]
        if todos:
            names = "、".join(str(t.get("title") or "") for t in todos[:3] if t.get("title"))
            more = "等 %d 项" % len(todos) if len(todos) > 3 else ""
            parts.append("待办还剩 %d 项（%s%s）" % (len(todos), names, more))

        minutes = sum(int(f.get("minutes") or 0) for f in (store.focus_log() or []) if f.get("date") == day)
        if minutes > 0:
            parts.append("已专注 %d 分钟" % minutes)

        ledger = [e for e in (store.ledger() or []) if e.get("date") == day]
        if ledger:
            expense = sum(float(e.get("amount") or 0) for e in ledger if e.get("kind") == "expense")
            income = sum(float(e.get("amount") or 0) for e in ledger if e.get("kind") == "income")
            money = "今天支出 %.0f 元" % expense
            if income > 0:
                money += "、收入 %.0f 元" % income
            parts.append(money)

        habits = store.habits() or []
        if habits:
            done = sum(1 for h in habits if (h.get("records") or {}).get(day))
            parts.append("习惯打卡 %d/%d" % (done, len(habits)))

        return "，".join(parts)
    except Exception:
        return ""
