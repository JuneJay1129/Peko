"""
计划数据层：日 / 月 / 年周期计划 + 待办清单，单一真相源为 data/plans.json 与 data/todos.json。

设计要点
--------
- Web 工作台宿主窗 (plans_web_dialog.py) 通过本模块读写同一份 plans.json / todos.json。
- 桌面内嵌窗（托盘「计划台」）与系统浏览器打开的纯网页版（托盘「工作台」）
  共用本模块：内嵌窗经 WebChannel 实时桥接（计划与待办都落盘），浏览器版无桥接时回退 localStorage
  （可导入/导出 JSON 与桌面数据互换）。
- 每次读写都从磁盘重新加载（个人数据量极小），保证两个界面实时一致。
- 写文件使用「临时文件 + 原子 rename」，避免半截写入损坏。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .runtime_paths import get_writable_root

# 固定 5 类 + 自定义；自定义只是归类用的一个兜底桶，颜色统一。
CATEGORIES: Dict[str, Dict[str, str]] = {
    "work": {"label": "工作", "color": "#4a7fb5"},
    "study": {"label": "学习", "color": "#7b6cc2"},
    "life": {"label": "生活", "color": "#e09a5e"},
    "exercise": {"label": "运动", "color": "#4caf7d"},
    "diet": {"label": "饮食", "color": "#d9869b"},
    "custom": {"label": "自定义", "color": "#8a715c"},
}
DEFAULT_CATS = ["work", "study", "life", "exercise", "diet"]

CYCLES = ["daily", "monthly", "yearly"]
PRIORITIES = ["P0", "P1", "P2"]

_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def month_str() -> str:
    return date.today().strftime("%Y-%m")


def year_str() -> str:
    return str(date.today().year)


def _new_id() -> str:
    import uuid

    return "p" + uuid.uuid4().hex[:10]


def _normalize(plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把任意来源（JSON / 网页 / 桥接）的记录规范化为合法 Plan；非法则返回 None。"""
    if not isinstance(plan, dict):
        return None
    title = (plan.get("title") or "").strip()
    if not title:
        return None
    cycle = plan.get("cycle")
    if cycle not in CYCLES:
        cycle = "daily"
    cat = plan.get("cat")
    if cat not in CATEGORIES:
        cat = "custom"
    pri = plan.get("pri")
    if pri not in PRIORITIES:
        pri = "P1"
    status = plan.get("status")
    if status not in ("pending", "done", "cancelled"):
        status = "pending"
    try:
        progress = int(plan.get("progress") or 0)
    except (TypeError, ValueError):
        progress = 0
    progress = max(0, min(100, progress))
    if status == "done":
        progress = 100
    period = (plan.get("period") or "").strip()
    if not period:
        period = today_str() if cycle == "daily" else month_str() if cycle == "monthly" else year_str()
    return {
        "id": plan.get("id") or _new_id(),
        "title": title,
        "cat": cat,
        "cycle": cycle,
        "period": period,
        "pri": pri,
        "status": status,
        "progress": progress,
        "note": (plan.get("note") or "").strip(),
        "created_at": plan.get("created_at") or _now(),
        "updated_at": plan.get("updated_at") or _now(),
        "done_at": plan.get("done_at") or ("" if status != "done" else _now()),
    }


def _normalize_todo(todo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把任意来源的待办记录规范化为合法 Todo；非法则返回 None。"""
    if not isinstance(todo, dict):
        return None
    title = (todo.get("title") or "").strip()
    if not title:
        return None
    cat = todo.get("cat")
    if cat not in CATEGORIES:
        cat = "custom"
    pri = todo.get("pri")
    if pri not in PRIORITIES:
        pri = "P1"
    status = todo.get("status")
    if status not in ("pending", "done", "cancelled"):
        status = "pending"
    due = (todo.get("due") or "").strip()
    return {
        "id": todo.get("id") or _new_id(),
        "title": title,
        "cat": cat,
        "pri": pri,
        "status": status,
        "due": due,
        "note": (todo.get("note") or "").strip(),
        "created_at": todo.get("created_at") or _now(),
        "done_at": todo.get("done_at") or ("" if status != "done" else _now()),
    }


class PlansStore:
    """plans.json 的读写与查询。线程安全（单进程内多界面共用）。"""

    def __init__(self, module_file: Optional[str] = None):
        root = get_writable_root(module_file or __file__)
        self.path = Path(root) / "data" / "plans.json"
        self.todos_path = Path(root) / "data" / "todos.json"
        self._lock = threading.Lock()

    # ----- 底层 IO -----
    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return []
        if isinstance(data, dict) and isinstance(data.get("plans"), list):
            plans = data["plans"]
        elif isinstance(data, list):
            plans = data
        else:
            return []
        return [p for p in (_normalize(p) for p in plans) if p is not None]

    def _persist(self, plans: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _SCHEMA_VERSION, "plans": plans}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)  # 原子替换，避免半截写入

    # ----- 对外查询（每次从磁盘取最新，保证多界面一致）-----
    def all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load()

    def by_cycle(self, cycle: str, cat: str = "all") -> List[Dict[str, Any]]:
        plans = [p for p in self.all() if p["cycle"] == cycle]
        if cat != "all":
            plans = [p for p in plans if p["cat"] == cat]
        return plans

    def is_overdue(self, plan: Dict[str, Any]) -> bool:
        if plan["status"] != "pending":
            return False
        ref = today_str() if plan["cycle"] == "daily" else month_str() if plan["cycle"] == "monthly" else year_str()
        return plan["period"] < ref

    def today_focus(self) -> List[Dict[str, Any]]:
        """今天要处理：日计划(今天或逾期) + 当月月计划 + 当年年计划，未完成项。"""
        out = []
        for p in self.all():
            if p["status"] == "done":
                continue
            if p["cycle"] == "daily":
                if p["period"] == today_str() or self.is_overdue(p):
                    out.append(p)
            elif p["cycle"] == "monthly":
                if p["period"] == month_str():
                    out.append(p)
            elif p["cycle"] == "yearly":
                if p["period"] == year_str():
                    out.append(p)
        out.sort(key=lambda p: ({"P0": 0, "P1": 1, "P2": 2}.get(p["pri"], 3), p["period"]))
        return out

    def stats(self, cycle: str, cat: str = "all") -> Dict[str, Any]:
        plans = self.by_cycle(cycle, cat)
        total = len(plans)
        done = sum(1 for p in plans if p["status"] == "done")
        avg = round(sum(p["progress"] for p in plans) / total) if total else 0
        overdue = sum(1 for p in plans if self.is_overdue(p))
        return {"total": total, "done": done, "avg": avg, "overdue": overdue}

    # ----- 对外变更 -----
    def add(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        plan = _normalize(fields)
        if plan is None:
            return None
        if not plan.get("created_at"):
            plan["created_at"] = _now()
        plan["updated_at"] = _now()
        with self._lock:
            plans = self._load()
            plans.insert(0, plan)
            self._persist(plans)
        return plan

    def update(self, pid: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            plans = self._load()
            for i, p in enumerate(plans):
                if p["id"] == pid:
                    merged = dict(p, **fields)
                    merged["id"] = pid
                    merged["updated_at"] = _now()
                    norm = _normalize(merged)
                    if norm is None:
                        return None
                    plans[i] = norm
                    self._persist(plans)
                    return norm
        return None

    def replace_all(self, plans: List[Dict[str, Any]]) -> None:
        """整体替换计划列表（Web 桥接一次性保存整份数据时使用）。"""
        if not isinstance(plans, list):
            return
        with self._lock:
            self._persist([p for p in (_normalize(p) for p in plans) if p is not None])

    def remove(self, pid: str) -> bool:
        with self._lock:
            plans = self._load()
            new = [p for p in plans if p["id"] != pid]
            if len(new) == len(plans):
                return False
            self._persist(new)
            return True

    def toggle(self, pid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            plans = self._load()
            for i, p in enumerate(plans):
                if p["id"] == pid:
                    if p["status"] == "done":
                        p = dict(p, status="pending", progress=p["progress"], done_at="", updated_at=_now())
                    else:
                        p = dict(p, status="done", progress=100, done_at=_now(), updated_at=_now())
                    plans[i] = p
                    self._persist(plans)
                    return p
        return None

    # ----- 待办（Todo）：独立文件 data/todos.json，结构与计划对称 -----
    def _load_todos(self) -> List[Dict[str, Any]]:
        if not self.todos_path.exists():
            return []
        try:
            raw = self.todos_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return []
        if isinstance(data, dict) and isinstance(data.get("todos"), list):
            todos = data["todos"]
        elif isinstance(data, list):
            todos = data
        else:
            return []
        return [t for t in (_normalize_todo(t) for t in todos) if t is not None]

    def _persist_todos(self, todos: List[Dict[str, Any]]) -> None:
        self.todos_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _SCHEMA_VERSION, "todos": todos}
        tmp = self.todos_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.todos_path)

    def todos(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load_todos()

    def add_todo(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        todo = _normalize_todo(fields)
        if todo is None:
            return None
        if not todo.get("created_at"):
            todo["created_at"] = _now()
        with self._lock:
            todos = self._load_todos()
            todos.insert(0, todo)
            self._persist_todos(todos)
        return todo

    def update_todo(self, tid: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            todos = self._load_todos()
            for i, t in enumerate(todos):
                if t["id"] == tid:
                    merged = dict(t, **fields)
                    merged["id"] = tid
                    norm = _normalize_todo(merged)
                    if norm is None:
                        return None
                    todos[i] = norm
                    self._persist_todos(todos)
                    return norm
        return None

    def remove_todo(self, tid: str) -> bool:
        with self._lock:
            todos = self._load_todos()
            new = [t for t in todos if t["id"] != tid]
            if len(new) == len(todos):
                return False
            self._persist_todos(new)
            return True

    def toggle_todo(self, tid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            todos = self._load_todos()
            for i, t in enumerate(todos):
                if t["id"] == tid:
                    if t["status"] == "done":
                        t = dict(t, status="pending", done_at="", updated_at=_now())
                    else:
                        t = dict(t, status="done", done_at=_now())
                    todos[i] = t
                    self._persist_todos(todos)
                    return t
        return None

    def replace_todos(self, todos: List[Dict[str, Any]]) -> None:
        """整体替换待办列表（Web 桥接一次性保存整份数据时使用）。"""
        if not isinstance(todos, list):
            return
        with self._lock:
            self._persist_todos([t for t in (_normalize_todo(t) for t in todos) if t is not None])

    # ----- 序列化给 Web 桥接 -----
    def to_json(self) -> str:
        return json.dumps(self.all(), ensure_ascii=False)

    def to_json_todos(self) -> str:
        return json.dumps(self.todos(), ensure_ascii=False)

    # ----- 工作台扩展模块：习惯打卡 / 记账 / 复盘 / 专注 -----
    def _named_path(self, fname: str) -> Path:
        return self.path.parent / fname

    def _load_named(self, fname: str, norm) -> List[Dict[str, Any]]:
        p = self._named_path(fname)
        if not p.exists():
            return []
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return []
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            arr = data["items"]
        elif isinstance(data, list):
            arr = data
        else:
            return []
        return [x for x in (norm(i) for i in arr) if x is not None]

    def _persist_named(self, fname: str, arr: List[Dict[str, Any]]) -> None:
        p = self._named_path(fname)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _SCHEMA_VERSION, "items": arr}
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)

    # ----- 习惯打卡 -----
    def habits(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load_named("habits.json", _normalize_habit)

    def replace_habits(self, arr: List[Dict[str, Any]]) -> None:
        if not isinstance(arr, list):
            return
        with self._lock:
            self._persist_named("habits.json", [x for x in (_normalize_habit(i) for i in arr) if x])

    # ----- 记账 -----
    def ledger(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load_named("ledger.json", _normalize_ledger)

    def replace_ledger(self, arr: List[Dict[str, Any]]) -> None:
        if not isinstance(arr, list):
            return
        with self._lock:
            self._persist_named("ledger.json", [x for x in (_normalize_ledger(i) for i in arr) if x])

    # ----- 复盘 -----
    def review(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load_named("review.json", _normalize_review)

    def replace_review(self, arr: List[Dict[str, Any]]) -> None:
        if not isinstance(arr, list):
            return
        with self._lock:
            self._persist_named("review.json", [x for x in (_normalize_review(i) for i in arr) if x])

    # ----- 专注 -----
    def focus_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load_named("focus.json", _normalize_focus)

    def replace_focus(self, arr: List[Dict[str, Any]]) -> None:
        if not isinstance(arr, list):
            return
        with self._lock:
            self._persist_named("focus.json", [x for x in (_normalize_focus(i) for i in arr) if x])


# =====================================================================
# 工作台扩展模块：习惯打卡 / 记账 / 复盘 / 专注
# 每个模块独立文件（data/habits.json 等），与 plans/todos 对称、共用原子写。
# =====================================================================
def _normalize_habit(h: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(h, dict):
        return None
    title = (h.get("title") or "").strip()
    if not title:
        return None
    cat = h.get("cat")
    if cat not in CATEGORIES:
        cat = "custom"
    rec = h.get("records")
    if not isinstance(rec, dict):
        rec = {}
    return {
        "id": h.get("id") or _new_id(),
        "title": title,
        "cat": cat,
        "records": {str(k): (1 if v else 0) for k, v in rec.items()},
        "created_at": h.get("created_at") or _now(),
    }


def _normalize_ledger(e: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(e, dict):
        return None
    title = (e.get("title") or "").strip()
    if not title:
        return None
    cat = e.get("cat")
    if cat not in CATEGORIES:
        cat = "custom"
    kind = e.get("kind")
    if kind not in ("income", "expense"):
        kind = "expense"
    try:
        amount = float(e.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    date = (e.get("date") or "").strip() or today_str()
    return {
        "id": e.get("id") or _new_id(),
        "title": title,
        "cat": cat,
        "kind": kind,
        "amount": round(amount, 2),
        "date": date,
        "note": (e.get("note") or "").strip(),
        "created_at": e.get("created_at") or _now(),
    }


def _normalize_review(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(r, dict):
        return None
    period_type = r.get("periodType")
    if period_type not in ("month", "year"):
        period_type = "month"
    period = (r.get("period") or "").strip() or (month_str() if period_type == "month" else year_str())
    text = (r.get("text") or "").strip()
    if not text:
        return None  # 空复盘不落盘
    return {
        "id": r.get("id") or _new_id(),
        "periodType": period_type,
        "period": period,
        "text": text,
        "created_at": r.get("created_at") or _now(),
        "updated_at": r.get("updated_at") or _now(),
    }


def _normalize_focus(f: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(f, dict):
        return None
    try:
        minutes = int(f.get("minutes") or 0)
    except (TypeError, ValueError):
        minutes = 0
    if minutes <= 0:
        return None
    date = (f.get("date") or "").strip() or today_str()
    return {
        "id": f.get("id") or _new_id(),
        "minutes": minutes,
        "label": (f.get("label") or "").strip(),
        "date": date,
        "created_at": f.get("created_at") or _now(),
    }

