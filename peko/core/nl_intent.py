"""
C5 自然语言入口：把桌宠聊天框里的一句话识别为「工作台写入」意图并落盘。

设计要点
--------
- 只在「明确的命令句式」下触发（记一笔 / 记账 / 提醒我 / 待办 / 开始专注 / 番茄钟），
  普通闲聊一律返回 None，交由聊天走 AI，避免劫持对话。
- 解析与落盘均为纯 Python（不依赖 Qt），便于单元测试。
- 记账 / 待办 直接写入 data/*.json（经 PlansStore，原子写）；
  「开始专注」不落盘，由调用方（聊天侧）用 QTimer 做提醒，避免虚增专注统计。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .plans_store import PlansStore, today_str

# 类别关键字 → plans_store.CATEGORIES 里的 cat 值
_CAT_KEYWORDS = {
    "diet": ("早饭", "午饭", "晚饭", "宵夜", "早餐", "午餐", "晚餐", "饭", "餐", "吃", "咖啡", "奶茶", "饮料", "水果", "零食", "外卖"),
    "exercise": ("健身", "运动", "跑步", "游泳", "瑜伽", "锻炼", "篮球", "足球", "羽毛球", " gym"),
    "study": ("书", "课", "学习", "考试", "阅读", "培训", "复盘", "单词"),
    "work": ("工作", "加班", "办公", "会议", "周报", "报销", "工资", "出差", "邮件", "客户"),
}

_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)")
_TIME_RE = re.compile(r"(上午|下午|晚上|中午|早上|今晚|明早)?\s*(\d{1,2})\s*[:：点]\s*(\d{1,2})?\s*分?")

# 记账显式触发动词
_LEDGER_VERBS = ("记一笔账", "记一笔", "记个账", "记账", "记帐", "记一下账")
# 收支流向词（无显式动词时，需配合金额 + 简短陈述才算记账）
_LEDGER_FLOW = ("花了", "支出", "花费", "花掉", "收入", "赚了", "进账", "进帐")
_INCOME_WORDS = ("收入", "赚了", "进账", "进帐")
# 待办触发词
_TODO_VERBS = ("加一个待办", "加个待办", "添加待办", "新增待办", "记个待办", "提醒我", "待办")
# 天气查询触发词（只读查询，不落盘）
_WEATHER_WORDS = ("天气", "气温", "下雨", "下雪", "多少度", "冷不冷", "热不热", "带伞", "穿什么", "刮风")
# 城市纠错：明确动词（不校验城市表，用户意图明确）；口语词需命中城市表防误伤
_CITY_SET_VERB = ("城市改成", "城市改为", "城市设为", "城市设置成", "设置城市为", "设置城市",
                  "把城市改成", "把城市改为", "城市改", "定位到")
_CITY_SET_CASUAL = ("我住在", "我现在在", "我当前在", "我在", "搬到", "搬去", "现在在")

# 显式指定城市的天气查询（一次性查看，不改默认/IP 定位城市）：
# 「帮我查看宁波的天气」「查一下杭州天气」「看看北京天气」「宁波天气怎么样」
# 候选城市字符集排除天气动词碎片（看/查/询），否则「查看」会被拆成 查+看(城市) 误匹配。
_WEATHER_CITY_RE = re.compile(
    r"(?:帮我)?(?:查(?:看|一下|询)?|看看|看)\s*([^天气气温怎么样的看查阅]{1,8}?)\s*(?:的)?\s*天气"
)
_WEATHER_CITY_FIRST_RE = re.compile(
    r"([^天气气温怎么样的你看查阅]{1,8}?)\s*(?:的)?\s*天气(?:怎么样|如何|怎样)"
)
# 这些词不是城市，命中时退化为「查默认城市天气」（交给 _parse_weather）
_WEATHER_CITY_NON_CITY = ("今天", "明天", "后天", "现在", "这儿", "这里", "我们", "本地", "当地")


def _guess_cat(title: str) -> str:
    for cat, keywords in _CAT_KEYWORDS.items():
        if any(k in title for k in keywords):
            return cat
    return "custom"


def _clean_text(t: str, *remove: str) -> str:
    out = t
    for w in remove:
        if w:
            out = out.replace(w, " ")
    out = _AMOUNT_RE.sub(" ", out)
    out = re.sub(r"\s+", " ", out)
    return out.strip(" ，,。.!！?？~～")


def _looks_like_statement(t: str) -> bool:
    """无明显疑问/感叹语气、且较短，才允许无动词的「流向词 + 金额」触发记账，降低劫持闲聊的概率。"""
    if any(m in t for m in ("吗", "呢", "什么", "怎么", "为什么", "?", "？", "哪")):
        return False
    return len(t) <= 25


def _parse_focus(t: str) -> Optional[Dict[str, Any]]:
    if "番茄钟" in t or ("番茄" in t and "开始" in t):
        return {"action": "start_focus", "minutes": 25, "label": "番茄钟"}
    m = re.search(r"专注\D{0,4}(\d{1,3})\s*分钟", t)
    if m:
        return {"action": "start_focus", "minutes": int(m.group(1)), "label": "专注"}
    if t.startswith("开始专注") or t.startswith("开始个专注"):
        return {"action": "start_focus", "minutes": 25, "label": "专注"}
    return None


def _parse_ledger(t: str) -> Optional[Dict[str, Any]]:
    verb = next((w for w in _LEDGER_VERBS if w in t), None)
    m = _AMOUNT_RE.search(t)
    amount = float(m.group(1)) if m else None
    flow = any(w in t for w in _LEDGER_FLOW)

    if verb is None:
        # 无显式动词：必须是「流向词 + 金额 + 简短陈述」
        if not (flow and amount is not None and _looks_like_statement(t)):
            return None
    elif amount is None:
        # 说了要记账但没给金额，无法入账 → 交给聊天
        return None

    kind = "income" if any(w in t for w in _INCOME_WORDS) else "expense"
    title = _clean_text(t, verb or "", *_LEDGER_FLOW, "块钱", "块", "元", "钱", "了", "一下", "帮我", "元整")
    if not title:
        title = "收入" if kind == "income" else "支出"
    return {
        "action": "add_ledger",
        "title": title,
        "amount": round(amount or 0.0, 2),
        "kind": kind,
        "cat": _guess_cat(title),
    }


def _parse_todo(t: str) -> Optional[Dict[str, Any]]:
    verb = next((w for w in _TODO_VERBS if w in t), None)
    if verb is None:
        return None
    # 提取可选时间（如 17:00 / 下午3点），写进 note，due 仍为今天。
    # 先把时间整段从原文去掉，再清理，避免金额正则把「17:00」的数字抹掉后残留「:」。
    note = ""
    body = t
    mt = _TIME_RE.search(t)
    if mt:
        note = mt.group(0).strip()
        body = t.replace(mt.group(0), " ")
    title = _clean_text(body, verb, "记得", "一下", "帮我")
    if not title:
        return None
    return {
        "action": "add_todo",
        "title": title,
        "due": today_str(),
        "note": note,
        "cat": _guess_cat(title),
    }


def _parse_weather(t: str) -> Optional[Dict[str, Any]]:
    """天气查询：只读，不落盘。放在最后匹配，避免劫持「提醒我带伞」这类待办句。"""
    if any(w in t for w in _WEATHER_WORDS):
        return {"action": "ask_weather"}
    return None


def _parse_weather_city(t: str) -> Optional[Dict[str, Any]]:
    """显式指定城市的天气查询（如「帮我查看宁波的天气」）。

    与 ask_weather（用默认/IP 定位城市）的区别：这里一次性查「句子中指定的城市」，
    不改动默认城市配置。城市名从句子里抽取；若抽到的不是城市（如「今天」），
    则退化成默认城市查询（交给 _parse_weather）。
    """
    m = _WEATHER_CITY_RE.search(t) or _WEATHER_CITY_FIRST_RE.search(t)
    if not m:
        return None
    cand = (m.group(1) or "").strip().rstrip("的")
    if not cand or cand in _WEATHER_CITY_NON_CITY:
        return None
    try:
        from .weather import match_city, normalize_city
    except Exception:
        return None
    name = match_city(cand) or normalize_city(cand)
    if not name:
        return None
    return {"action": "ask_weather_city", "city": name}


def _parse_set_city(t: str) -> Optional[Dict[str, Any]]:
    """纠正城市（解决 IP 定位不准）。返回 {action:set_city, city}。

    - 明确动词（「城市改成 XX」）直接信任用户，不做城市表校验；
    - 口语（「我在 XX」）必须命中内置城市表，避免「我在上班」被误设成城市。
    - 含天气查询词时交给天气意图，不做设置（「我在宁波下雨吗」=查天气）。
    """
    if any(w in t for w in _WEATHER_WORDS):
        return None
    try:
        from .weather import match_city
    except Exception:
        return None

    for verb in _CITY_SET_VERB:
        if verb in t:
            rest = t[t.index(verb) + len(verb):]
            name = match_city(rest)
            if name:
                return {"action": "set_city", "city": name}
            return None

    for verb in _CITY_SET_CASUAL:
        if t.startswith(verb):
            rest = t[len(verb):]
            name = match_city(rest)
            if name:
                return {"action": "set_city", "city": name}
            # 命中口语动词但不是城市（如「我在吃饭」）→ 交给 AI，不误设
            return None
    return None


def parse(text: str) -> Optional[Dict[str, Any]]:
    """把一句话解析为工作台意图；非命令句式返回 None。"""
    t = (text or "").strip()
    if not t:
        return None
    return (
        _parse_focus(t)
        or _parse_ledger(t)
        or _parse_todo(t)
        or _parse_weather_city(t)
        or _parse_weather(t)
        or _parse_set_city(t)
    )


# 全部触发词并集：用于判断「像命令但没写全」
_ALL_TRIGGER_WORDS = (
    _LEDGER_VERBS + tuple(_LEDGER_FLOW) + _TODO_VERBS + ("专注", "番茄钟", "番茄")
)

_USAGE_HINT = (
    "可以这样跟我说：\n"
    "记支出：记一笔 支出 午饭 38\n"
    "记收入：记一笔 收入 兼职 500\n"
    "待办：提醒我 17:00 交周报\n"
    "专注：开始专注 25 分钟"
)


def suggest_usage(text: str) -> Optional[str]:
    """文本包含命令触发词但 parse 未命中（如缺金额/标题）时，返回用法提示；否则 None。

    用于「非 AI」兜底：用户显然想记点什么但格式不对时，给模板提示而不是落入 AI 聊天。
    """
    t = (text or "").strip()
    if not t:
        return None
    if parse(t) is not None:
        return None
    if any(w in t for w in _ALL_TRIGGER_WORDS):
        return _USAGE_HINT
    return None


def apply(intent: Dict[str, Any], store: Optional[PlansStore] = None) -> str:
    """执行意图并返回给用户的确认文案。记账 / 待办落盘；开始专注不落盘（由调用方提醒）。"""
    action = intent.get("action")
    store = store or PlansStore(__file__)

    if action == "add_ledger":
        entry = {
            "title": intent.get("title") or "支出",
            "cat": intent.get("cat") or "custom",
            "kind": intent.get("kind") or "expense",
            "amount": intent.get("amount") or 0.0,
            "date": today_str(),
            "note": intent.get("note") or "",
        }
        arr = store.ledger()
        arr.insert(0, entry)
        store.replace_ledger(arr)
        kind_label = "收入" if entry["kind"] == "income" else "支出"
        return f"已记一笔{kind_label}：{entry['title']} ¥{entry['amount']:g}，同步到「记账」了。"

    if action == "add_todo":
        todo = store.add_todo({
            "title": intent.get("title") or "",
            "cat": intent.get("cat") or "custom",
            "due": intent.get("due") or today_str(),
            "note": intent.get("note") or "",
        })
        if todo is None:
            return ""
        suffix = f"（{intent['note']}）" if intent.get("note") else ""
        return f"已加待办：{todo['title']}{suffix}，同步到「待办清单」了。"

    if action == "start_focus":
        minutes = int(intent.get("minutes") or 25)
        return f"好的，专注 {minutes} 分钟开始，结束我会提醒你。"

    if action == "ask_weather":
        # 天气需联网取数，属异步流程，由调用方（chat）直接走 weather_report，不走这里。
        return ""

    return ""
