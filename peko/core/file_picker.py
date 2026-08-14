"""
狙击点选文件：红色准星点击桌面 / 资源管理器里的文件图标 → 解析出真实文件路径。

原理
----
- `uiautomation.ControlFromPoint` 取点击处控件（桌面 / 资源管理器的文件项是 ListItem），
  向上找最近的有名字的控件作为「显示名」；
- `WindowFromPoint` + `GetAncestor(GA_ROOT)` 找到点击所在的资源管理器顶层窗口，
  经 `Shell.Application` 取该窗口的文件夹路径；
- 若不在资源管理器窗口上（点在桌面），搜 用户 Desktop 与 公共 Desktop；
- 显示名可能不带扩展名（取决于资源管理器「隐藏扩展名」设置），匹配按「全名 → 去扩展名」两级。

仅 Windows。UIA / Shell 部分需真实桌面环境，单测只覆盖纯函数 `match_name_in_folder`。
"""
from __future__ import annotations

import ctypes
import os
from typing import List, Optional


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _desktop_dirs() -> List[str]:
    dirs = [
        os.path.expanduser(os.path.join("~", "Desktop")),
        r"C:\Users\Public\Desktop",
    ]
    return [d for d in dirs if os.path.isdir(d)]


def match_name_in_folder(folder: str, display_name: str) -> Optional[str]:
    """在文件夹里按显示名找文件：先全名精确（不区分大小写），再去扩展名匹配。"""
    if not folder or not display_name or not os.path.isdir(folder):
        return None
    want = display_name.strip().lower()
    want_stem = os.path.splitext(want)[0]
    if not want_stem:
        return None
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return None
    for e in entries:
        if e.name.lower() == want:
            return os.path.join(folder, e.name)
    for e in entries:
        if os.path.splitext(e.name.lower())[0] == want_stem:
            return os.path.join(folder, e.name)
    return None


def _root_hwnd_at(x: int, y: int) -> int:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.WindowFromPoint(_POINT(x, y))
        if not hwnd:
            return 0
        root = user32.GetAncestor(hwnd, 2)  # GA_ROOT
        return root or hwnd
    except Exception:
        return 0


def _explorer_folder_at(x: int, y: int) -> Optional[str]:
    """点击处所在资源管理器窗口的文件夹路径；不在资源管理器窗口上返回 None。"""
    root = _root_hwnd_at(x, y)
    if not root:
        return None
    try:
        import win32com.client
        shell = win32com.client.Dispatch("Shell.Application")
        for w in shell.Windows():
            try:
                if w.HWND == root:
                    folder = w.Document.Folder.Self.Path
                    if folder and os.path.isdir(folder):
                        return folder
            except Exception:
                continue
    except Exception:
        pass
    return None


def _display_name_at(x: int, y: int) -> str:
    """点击处的文件显示名：向上找最近的有名字的控件（优先 ListItem）。"""
    try:
        import uiautomation as auto
    except ImportError:
        return ""
    try:
        ctrl = auto.ControlFromPoint(x, y)
        name = ""
        cur = ctrl
        for _ in range(6):
            if cur is None:
                break
            try:
                n = (cur.Name or "").strip()
            except Exception:
                break
            if n:
                name = n
                try:
                    if cur.ControlType == auto.ControlType.ListItemControl:
                        break
                except Exception:
                    pass
            cur = cur.GetParentControl()
        return name
    except Exception:
        return ""


def resolve_file_at_point(x: int, y: int) -> Optional[str]:
    """点击坐标 → 真实文件路径；认不出返回 None。"""
    name = _display_name_at(x, y)
    if not name:
        return None
    folder = _explorer_folder_at(x, y)
    if folder:
        hit = match_name_in_folder(folder, name)
        if hit:
            return hit
    for d in _desktop_dirs():
        hit = match_name_in_folder(d, name)
        if hit:
            return hit
    return None
