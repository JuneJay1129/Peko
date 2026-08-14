"""
靠谱值：工作台「完成行为」累计的正向积分，持久化到 data/pet_bond.json。

B3 联动（完成 → 桌宠反馈）的数据底座。纯 Python、不依赖 Qt，便于单元测试。
写文件沿用「临时文件 + 原子 rename」，与 plans_store 一致。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .runtime_paths import get_writable_root

_lock = threading.Lock()
_FILE_VERSION = 1


def _default_path() -> Path:
    root = get_writable_root(__file__)
    return Path(root) / "data" / "pet_bond.json"


def _empty() -> Dict[str, Any]:
    return {"version": _FILE_VERSION, "total": 0, "by_kind": {}}


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("total", 0)
    if not isinstance(data.get("by_kind"), dict):
        data["by_kind"] = {}
    return data


def _persist(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def record_completion(kind: str, path: Optional[str] = None) -> int:
    """记录一次完成，靠谱值 +1（并按类型累计），返回最新总靠谱值。"""
    p = Path(path) if path else _default_path()
    kind = (kind or "task").strip() or "task"
    with _lock:
        data = _load(p)
        data["total"] = int(data.get("total", 0)) + 1
        by_kind = data.setdefault("by_kind", {})
        by_kind[kind] = int(by_kind.get(kind, 0)) + 1
        _persist(p, data)
        return int(data["total"])


def get_total(path: Optional[str] = None) -> int:
    p = Path(path) if path else _default_path()
    return int(_load(p).get("total", 0))


def get_by_kind(path: Optional[str] = None) -> Dict[str, int]:
    p = Path(path) if path else _default_path()
    return dict(_load(p).get("by_kind", {}))
