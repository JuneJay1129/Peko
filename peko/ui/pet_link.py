"""
桌宠×工作台联动通道（B3）：工作台「完成事件」→ 桌宠即时反馈。

- 进程内单例 notifier（QObject + pyqtSignal），由桌宠在主线程 connect；
  工作台侧（本地 HTTP 服务线程 / 内嵌 WebChannel 桥）调用 notify_completion 触发。
- 跨线程：服务线程 emit → 桌宠槽函数经 Qt 队列连接在主线程执行，安全操作 UI。
- Qt 不可用时优雅降级：仅记录靠谱值，不发射信号（不报错）。
"""
from __future__ import annotations

from typing import Optional

from ..core import pet_bond

_notifier = None      # 单例 QObject
_qt_unavailable = False  # 标记 PyQt5 不可用，避免重复尝试


def _ensure_notifier():
    """惰性创建单例 notifier。PyQt5 缺失时返回 None。"""
    global _notifier, _qt_unavailable
    if _notifier is not None or _qt_unavailable:
        return _notifier
    try:
        from PyQt5.QtCore import QObject, pyqtSignal

        class _Notifier(QObject):
            # kind(类型) / label(条目名) / total(最新靠谱值)
            workspace_completed = pyqtSignal(str, str, int)

        _notifier = _Notifier()
    except Exception:
        _notifier = None
        _qt_unavailable = True
    return _notifier


def get_notifier():
    """返回单例 notifier（可能为 None）。桌宠用它 connect 完成事件。"""
    return _ensure_notifier()


def notify_completion(kind: str, label: str = "", bond_path: Optional[str] = None) -> int:
    """记录靠谱值并广播完成事件，返回最新靠谱值。Qt 不可用时仅记录。"""
    total = pet_bond.record_completion(kind, path=bond_path)
    n = _ensure_notifier()
    if n is not None:
        try:
            n.workspace_completed.emit(kind or "task", label or "", total)
        except Exception:
            pass
    return total
