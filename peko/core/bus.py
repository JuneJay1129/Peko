"""
进程内事件总线（阶段 C 基建）：组件间解耦广播。

此前「主题切换」等跨组件刷新由 settings_dialog 手工逐个调用
（pet.refresh_theme / tray.refresh_theme），新增可刷新组件就要再改一处。
改为发布/订阅后：settings 只 emit("theme_changed", key)，各组件自行订阅。

用法：
    from ..core.bus import bus
    bus.subscribe("theme_changed", self._on_theme_changed)
    bus.unsubscribe("theme_changed", self._on_theme_changed)   # 组件关闭时退订，防泄漏
    bus.emit("theme_changed", "dark")

约定：
- 订阅回调在 emit 调用方线程同步执行；跨线程 UI 更新仍走 Qt 信号（bubble_stream_ready）。
- 单个回调异常不影响其他订阅者（吞异常打日志）。
- 目前仅单实例模块级 bus；纯 Python、不依赖 Qt，便于单元测试。
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, List

_event = str


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[_event, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event: _event, fn: Callable) -> None:
        with self._lock:
            self._subs.setdefault(event, [])
            if fn not in self._subs[event]:
                self._subs[event].append(fn)

    def unsubscribe(self, event: _event, fn: Callable) -> None:
        with self._lock:
            fns = self._subs.get(event)
            if fns and fn in fns:
                fns.remove(fn)

    def emit(self, event: _event, *args) -> None:
        with self._lock:
            fns = list(self._subs.get(event, []))
        for fn in fns:
            try:
                fn(*args)
            except Exception as e:  # 单个订阅者异常不拖垮其他订阅者
                print(f"[Bus] {event} 订阅回调异常: {e}")


# 模块级单例：全项目共享一条总线
bus = EventBus()
