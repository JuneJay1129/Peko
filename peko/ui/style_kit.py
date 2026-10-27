"""
通用 UI 样式组件（style kit）：主题色板、字体、通用 QSS 生成器。

背景：此前各弹窗/菜单文件各自维护「try: appearance.get_ui_style except: 兜底色板」
样板，兜底色值多份且互相漂移；字体判断也重复多处。这里统一收敛：

- palette():          当前主题 UI 色板（全项目唯一兜底，回退暖色 pet 主题）
- font_family():      跨平台字体名（Mac: PingFang SC；Windows: Microsoft YaHei UI）
- app_font():         QFont 快捷构造
- menu_qss():         托盘 / Dock 菜单样式
- input_dialog_qss(): QInputDialog 主题化样式（跟随明暗主题）

各弹窗的 objectName 级特化样式仍留在各自文件；pet.py 的气泡/侧栏与
bubble 配置强耦合，不在此收敛。纯字符串生成、不依赖 Qt（app_font 除外），
便于单元测试。
"""
from __future__ import annotations

import sys
from typing import Dict

# 全项目统一兜底色板 = appearance.THEMES["pet"]["ui"]（唯一一份，别处不许再写）
_FALLBACK_UI: Dict[str, str] = {
    "bg": "#faf3e0", "card": "#fffef9", "accent": "#c4a574", "accent_hover": "#b59668",
    "ink": "#4a3f35", "ink_soft": "#9a8f7f", "border": "#e8dcc4",
}


def palette() -> Dict[str, str]:
    """当前外观主题的 UI 色板；appearance 取不到时回退暖色（唯一兜底）。"""
    try:
        from ..core import appearance as ap
        return ap.get_ui_style(ap.get_theme())
    except Exception:
        return dict(_FALLBACK_UI)


def font_family() -> str:
    """跨平台 UI 字体名：Mac 无 Microsoft YaHei，用 PingFang SC。"""
    return "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"


def app_font(size: int = 14, bold: bool = False):
    """QFont 快捷构造（惰性导入 Qt，保持模块可脱离 Qt 测试）。"""
    from PyQt5.QtGui import QFont
    weight = QFont.Bold if bold else QFont.Normal
    return QFont(font_family(), size, weight)


def menu_qss() -> str:
    """托盘 / Dock 菜单样式：按当前外观主题的 UI 色板生成（暖色圆角）。"""
    ui = palette()
    return f"""
    QMenu {{
        background-color: {ui['bg']};
        border: 1px solid {ui['border']};
        border-radius: 10px;
        padding: 6px 0;
        min-width: 160px;
    }}
    QMenu::item {{
        padding: 8px 24px 8px 16px;
        font-size: 13px;
        color: {ui['ink']};
    }}
    QMenu::item:selected {{
        background-color: {ui['border']};
        color: {ui['ink']};
    }}
    QMenu::item:disabled {{
        color: {ui['ink_soft']};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {ui['border']};
        margin: 4px 12px;
    }}
    QMenu::indicator {{
        width: 14px;
        height: 14px;
        border-radius: 3px;
        border: 1px solid {ui['accent']};
        background-color: {ui['card']};
        margin-left: 8px;
    }}
    QMenu::indicator:checked {{
        background-color: {ui['accent']};
    }}
"""


def input_dialog_qss() -> str:
    """QInputDialog 主题化样式：跟随明暗主题（dark 下不再是系统默认白框）。

    OK 按钮用 :default 伪态命中（按钮文案随系统语言变化，不能按文字匹配）。
    """
    ui = palette()
    return f"""
    QInputDialog {{
        background-color: {ui['card']};
        font-family: '{font_family()}';
    }}
    QLabel {{
        color: {ui['ink']};
        font-size: 14px;
    }}
    QLineEdit {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 8px;
        padding: 8px 12px;
        color: {ui['ink']};
        font-size: 14px;
        selection-background-color: {ui['accent']};
    }}
    QLineEdit:focus {{ border-color: {ui['accent']}; }}
    QPushButton {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 8px;
        padding: 6px 18px;
        color: {ui['ink']};
        font-size: 13px;
    }}
    QPushButton:hover {{ background-color: {ui['bg']}; }}
    QPushButton:pressed {{ background-color: {ui['border']}; }}
    QPushButton:default {{
        background-color: {ui['accent']};
        color: {ui['card']};
        border: none;
        font-weight: 600;
    }}
    QPushButton:default:hover {{ background-color: {ui['accent_hover']}; }}
"""
