"""
对话记忆存储：把每次「用户提问 + 模型回复」落在 data/chat_history/ 下。

为什么需要：此前 `ui/chat.py` 每次只发 `[system, user]`，关掉对话框就失忆，
宠物永远接不上上一句。这里提供落盘与读取，供 `context_builder` 组装上下文。

约定：
- `index.json` 记会话清单与当前会话；`conv_<id>.json` 记消息。
- 只落**成对**的用户提问 + 模型回复：流式失败、被取消、空回复都不写盘，
  避免半截内容污染后续上下文。
- 写入走 `config_store.write_json`（临时文件 + `os.replace` 原子替换）。
- 读取失败一律降级为「没有历史」，绝不让聊天因为历史文件损坏而不可用。
- 超出 `MAX_MESSAGES` 时从最旧的整轮丢起，保证 user / assistant 不被拆开。

纯 Python、不依赖 Qt，可直接单测。
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from . import config_store

HISTORY_DIR = "data/chat_history"
INDEX_FILE = HISTORY_DIR + "/index.json"
MAX_MESSAGES = 200  # 落盘上限（约 100 轮）；上下文再用 context_builder 二次裁剪
TITLE_MAX_CHARS = 16
DEFAULT_TITLE = "新对话"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _new_id() -> str:
    return "conv_%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:6])


def _conv_file(conv_id: str) -> str:
    return "%s/%s.json" % (HISTORY_DIR, conv_id)


def _clean_messages(messages: Any) -> List[Dict[str, str]]:
    """只保留 role/content 都合法的消息，其他脏数据一律丢弃。"""
    cleaned: List[Dict[str, str]] = []
    if not isinstance(messages, list):
        return cleaned
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    return cleaned


def _trim(messages: List[Dict[str, str]], limit: int = MAX_MESSAGES) -> List[Dict[str, str]]:
    """按条数裁剪；裁完若以 assistant 开头（缺了对应提问）再丢一条。"""
    if len(messages) <= limit:
        return messages
    trimmed = list(messages[-limit:])
    while trimmed and trimmed[0]["role"] != "user":
        trimmed.pop(0)
    return trimmed


def _derive_title(text: str) -> str:
    """用首条提问生成会话标题，太长的截断加省略号。"""
    title = " ".join((text or "").split())
    if not title:
        return DEFAULT_TITLE
    return title[:TITLE_MAX_CHARS] + ("…" if len(title) > TITLE_MAX_CHARS else "")


class ChatStore:
    """对话历史读写。线程安全：AI 请求在子线程落盘，界面线程同时可能读取。"""

    def __init__(self, base_dir: Optional[str] = None):
        self._base_dir = base_dir
        self._lock = threading.RLock()

    # ---------- 索引 ----------
    def _read_index(self) -> Dict[str, Any]:
        raw = config_store.read_json(INDEX_FILE, default=None, base_dir=self._base_dir)
        if isinstance(raw, list):  # 旧格式：裸会话数组
            convs = [c for c in raw if isinstance(c, dict) and c.get("id")]
            return {"version": 1, "active": convs[0]["id"] if convs else "", "conversations": convs}
        if isinstance(raw, dict):
            convs = [c for c in (raw.get("conversations") or []) if isinstance(c, dict) and c.get("id")]
            active = raw.get("active") or ""
            return {"version": 1, "active": active if active else "", "conversations": convs}
        return {"version": 1, "active": "", "conversations": []}

    def _write_index(self, index: Dict[str, Any]) -> bool:
        return config_store.write_json(INDEX_FILE, index, base_dir=self._base_dir)

    @staticmethod
    def _find(index: Dict[str, Any], conv_id: str) -> Optional[Dict[str, Any]]:
        for conv in index.get("conversations") or []:
            if conv.get("id") == conv_id:
                return conv
        return None

    def _read_conv(self, conv_id: str) -> Dict[str, Any]:
        raw = config_store.read_json(_conv_file(conv_id), default=None, base_dir=self._base_dir)
        if not isinstance(raw, dict):
            return {"id": conv_id, "title": DEFAULT_TITLE, "messages": [], "created_at": _now(), "updated_at": _now()}
        return {
            "id": conv_id,
            "title": str(raw.get("title") or DEFAULT_TITLE),
            "messages": _clean_messages(raw.get("messages")),
            "created_at": str(raw.get("created_at") or _now()),
            "updated_at": str(raw.get("updated_at") or _now()),
        }

    # ---------- 对外 ----------
    def list_conversations(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._read_index().get("conversations") or [])

    def active_id(self) -> str:
        """当前会话 id；没有则创建一条，保证调用方总能拿到可写目标。"""
        with self._lock:
            index = self._read_index()
            active = index.get("active") or ""
            if active and self._find(index, active):
                return active
            conv = self._create_locked(index, DEFAULT_TITLE)
            return conv["id"]

    def new_conversation(self, title: str = DEFAULT_TITLE) -> str:
        with self._lock:
            index = self._read_index()
            return self._create_locked(index, (title or DEFAULT_TITLE).strip() or DEFAULT_TITLE)["id"]

    def _create_locked(self, index: Dict[str, Any], title: str) -> Dict[str, Any]:
        conv_id = _new_id()
        now = _now()
        conv = {
            "id": conv_id,
            "title": title,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        config_store.write_json(_conv_file(conv_id), conv, base_dir=self._base_dir)
        index.setdefault("conversations", []).append(
            {"id": conv_id, "title": title, "created_at": now, "updated_at": now, "message_count": 0}
        )
        index["active"] = conv_id
        self._write_index(index)
        return conv

    def load_messages(self, conv_id: Optional[str] = None) -> List[Dict[str, str]]:
        """读最近的历史消息（时间正序）；读不到就是空列表，绝不抛异常。"""
        with self._lock:
            try:
                target = conv_id or self._read_index().get("active") or ""
                if not target:
                    return []
                return self._read_conv(target)["messages"]
            except Exception:
                return []

    def append_turn(self, user_text: str, reply: str, conv_id: Optional[str] = None) -> bool:
        """落一整轮问答。任一侧为空（失败/取消）就不写，避免污染上下文。"""
        user_text = (user_text or "").strip()
        reply = (reply or "").strip()
        if not user_text or not reply:
            return False
        with self._lock:
            try:
                index = self._read_index()
                target = conv_id or index.get("active") or ""
                meta = self._find(index, target) if target else None
                if meta is None:
                    meta = self._create_locked(index, _derive_title(user_text))
                    index = self._read_index()  # 重建后的索引
                    target = meta["id"]
                data = self._read_conv(target)
                messages = list(data["messages"])
                messages.append({"role": "user", "content": user_text})
                messages.append({"role": "assistant", "content": reply})
                messages = _trim(messages)
                now = _now()
                data.update({"id": target, "messages": messages, "updated_at": now})
                if data["title"] in ("", DEFAULT_TITLE):
                    data["title"] = _derive_title(user_text)
                if not config_store.write_json(_conv_file(target), data, base_dir=self._base_dir):
                    return False
                # 同步索引里的标题与轮数，供未来的会话列表使用
                for conv in index.get("conversations") or []:
                    if conv.get("id") == target:
                        conv["title"] = data["title"]
                        conv["updated_at"] = now
                        conv["message_count"] = len(messages)
                        break
                index["active"] = target
                return self._write_index(index)
            except Exception:
                return False

    def clear(self, conv_id: Optional[str] = None) -> bool:
        """清空当前会话的消息（保留会话本身），用于「忘掉之前聊的」。"""
        with self._lock:
            try:
                index = self._read_index()
                target = conv_id or index.get("active") or ""
                if not target:
                    return True
                data = self._read_conv(target)
                now = _now()
                data.update({"messages": [], "title": DEFAULT_TITLE, "updated_at": now})
                ok = config_store.write_json(_conv_file(target), data, base_dir=self._base_dir)
                for conv in index.get("conversations") or []:
                    if conv.get("id") == target:
                        conv["title"] = DEFAULT_TITLE
                        conv["updated_at"] = now
                        conv["message_count"] = 0
                        break
                self._write_index(index)
                return ok
            except Exception:
                return False

    def delete(self, conv_id: str) -> bool:
        """删除整个会话文件并从索引移除。"""
        with self._lock:
            try:
                index = self._read_index()
                index["conversations"] = [c for c in (index.get("conversations") or []) if c.get("id") != conv_id]
                if index.get("active") == conv_id:
                    index["active"] = (index["conversations"][0]["id"] if index["conversations"] else "")
                self._write_index(index)
                return config_store.delete_file(_conv_file(conv_id), base_dir=self._base_dir)
            except Exception:
                return False
