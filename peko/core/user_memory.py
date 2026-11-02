"""
轻量长期记忆：从用户原话里抽取**稳定事实**（称呼、喜好、作息），注入 system，
让宠物「记得你」。不额外调用 LLM，纯本地正则，零成本零延迟。

刻意保守：只认显式表达（「以后叫我…」「我喜欢…」），不做模糊推断——
记错比不记更伤害体验，所以宁可漏，不要错。

存储：data/chat_history/memory.json
    {"version": 1, "facts": [{"key": "称呼", "value": "老板", "ts": "..."}]}

纯 Python、不依赖 Qt，可直接单测。
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Dict, List, Optional

from . import config_store

MEMORY_FILE = "data/chat_history/memory.json"
MAX_FACTS = 20  # 超过就淘汰最旧的
_LOCK = threading.RLock()

# key -> 注入 system 时的说法
_KEY_LABELS = {
    "称呼": "用户希望被称呼为",
    "喜好": "用户喜欢",
    "厌恶": "用户不喜欢",
    "习惯": "用户的习惯",
}

_STOP_CHARS = "，。！？；：、,.!?;: \t\r\n～~（）()\"'“”‘’"

# 顺序有意义：「以后叫我」优先于泛化的「我叫」，避免把昵称当本名
_RULES = (
    ("称呼", re.compile(r"以后(?:就)?叫我(.{1,10})")),
    ("称呼", re.compile(r"记住[，,、 ]*我(?:叫|是)(.{1,10})")),
    ("称呼", re.compile(r"我的名字(?:叫|是)(.{1,10})")),
    ("喜爱", re.compile(r"我(?:很|最|超|特别)?(?:喜欢|爱)(.{1,14})")),
    ("厌恶", re.compile(r"我(?:很|最|特别)?(?:不喜欢|讨厌|受不了)(.{1,14})")),
    ("习惯", re.compile(r"我(?:通常|一般|习惯|每天)(.{1,18})")),
)
# 内部 key 别名：喜爱 → 喜好（对外统一）
_KEY_ALIAS = {"喜爱": "喜好"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _clean_value(raw: str) -> str:
    """截到第一个标点/空格，再去掉结尾语气词（「以后叫我老板吧」→「老板」）。"""
    value = (raw or "").strip()
    for idx, ch in enumerate(value):
        if ch in _STOP_CHARS:
            value = value[:idx]
            break
    value = value.strip()
    for suffix in ("吧", "呀", "啊", "哦", "呢", "啦", "嘛"):
        if len(value) > 2 and value.endswith(suffix):
            value = value[:-1]
    return value.strip()


def _is_meaningful(key: str, value: str) -> bool:
    if not value or len(value) > 20:
        return False
    # 「我喜欢你」这种是撒娇，不是事实
    if value in ("你", "您", "你们", "它", "他", "她"):
        return False
    if key == "称呼" and value.startswith(("你", "您")):
        return False
    return True


def extract_facts(text: str) -> List[Dict[str, str]]:
    """从一句话里抽事实；抽不到返回空列表。"""
    text = (text or "").strip()
    if not text:
        return []
    facts: List[Dict[str, str]] = []
    seen = set()
    for key, pattern in _RULES:
        match = pattern.search(text)
        if not match:
            continue
        real_key = _KEY_ALIAS.get(key, key)
        value = _clean_value(match.group(1))
        if real_key in seen or not _is_meaningful(real_key, value):
            continue
        seen.add(real_key)
        facts.append({"key": real_key, "value": value})
    return facts


def load_facts(base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    raw = config_store.read_json(MEMORY_FILE, default=None, base_dir=base_dir)
    if not isinstance(raw, dict):
        return []
    facts = []
    for item in raw.get("facts") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if key and value:
            facts.append({"key": key, "value": value, "ts": str(item.get("ts") or "")})
    return facts[:MAX_FACTS]


def remember_from(text: str, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """抽取并落盘，返回本次真正新增/更新的事实。"""
    new_facts = extract_facts(text)
    if not new_facts:
        return []
    with _LOCK:
        facts = load_facts(base_dir)
        changed = []
        for item in new_facts:
            ts = _now()
            existing = next((f for f in facts if f["key"] == item["key"]), None)
            if existing:
                if existing["value"] == item["value"]:
                    continue  # 没变，别刷新时间戳
                existing["value"] = item["value"]
                existing["ts"] = ts
            else:
                facts.append({"key": item["key"], "value": item["value"], "ts": ts})
            changed.append({"key": item["key"], "value": item["value"]})
        if not changed:
            return []
        facts.sort(key=lambda f: f.get("ts") or "")
        facts = facts[-MAX_FACTS:]
        config_store.write_json(MEMORY_FILE, {"version": 1, "facts": facts}, base_dir=base_dir)
        return changed


def clear(base_dir: Optional[str] = None) -> bool:
    with _LOCK:
        return config_store.write_json(MEMORY_FILE, {"version": 1, "facts": []}, base_dir=base_dir)


def format_for_prompt(facts: Optional[List[Dict[str, Any]]] = None, base_dir: Optional[str] = None) -> str:
    """转成 system 里「关于用户」的短段落；没有事实时返回空串。"""
    facts = load_facts(base_dir) if facts is None else facts
    if not facts:
        return ""
    lines = []
    for item in facts:
        label = _KEY_LABELS.get(item.get("key"), item.get("key"))
        value = item.get("value")
        if label and value:
            lines.append("- %s「%s」" % (label, value))
    return "\n".join(lines)
