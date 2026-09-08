"""
外观主题：全局 UI 主题的注册与持久化。

- 每个主题包含：
  - bubble：气泡样式键值（供 pet / 安慰浮层 / 输入框复用）
  - ui：全局 UI 色板（bg 窗口背景 / card 卡片与输入框 / accent 主色 / accent_hover /
    ink 主文字 / ink_soft 次级文字 / border 边框），供设置页、托盘菜单、输入对话框着色。
- 主题键：'pet' 跟随宠物（默认暖色）；其余为预置（warm 暖黄 / mint 薄荷 / pink 粉彩 / dark 深色护眼）。
- 持久化到 config/appearance.json，切换即保存，重启生效。
纯 Python、不依赖 Qt，便于单元测试。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .runtime_paths import get_writable_root

APPEARANCE_PATH = os.path.join(get_writable_root(module_file=__file__), "config", "appearance.json")

# ---- 全局主题注册表 ----
# ui 色板为各窗口 QSS 提供变量；dark 主题下 ink 用浅色以保证可读性。
THEMES: Dict[str, Dict[str, Any]] = {
    "pet": {
        "label": "跟随宠物",
        "bubble": None,  # 使用宠物自带 bubbleStyle
        "ui": {
            "bg": "#faf3e0", "card": "#fffef9", "accent": "#c4a574", "accent_hover": "#b59668",
            "ink": "#4a3f35", "ink_soft": "#9a8f7f", "border": "#e8dcc4",
        },
    },
    "warm": {
        "label": "暖黄",
        "bubble": {
            "backgroundColor": "rgba(255, 247, 230, 0.94)",
            "border": "2px solid #e8c07a",
            "borderRadius": "16px",
            "padding": "10px 14px",
            "fontSize": "14px",
            "color": "#5a4632",
        },
        "ui": {
            "bg": "#fbf3e2", "card": "#fffdf4", "accent": "#d9a05b", "accent_hover": "#c68d49",
            "ink": "#4f3d28", "ink_soft": "#a39074", "border": "#ead9b4",
        },
    },
    "mint": {
        "label": "薄荷",
        "bubble": {
            "backgroundColor": "rgba(232, 248, 241, 0.94)",
            "border": "2px solid #7ec8a3",
            "borderRadius": "16px",
            "padding": "10px 14px",
            "fontSize": "14px",
            "color": "#2f6b4f",
        },
        "ui": {
            "bg": "#eef7f0", "card": "#f8fdfa", "accent": "#6fae8c", "accent_hover": "#5c9a7a",
            "ink": "#2f4a3c", "ink_soft": "#8aa596", "border": "#cfe3d4",
        },
    },
    "pink": {
        "label": "粉彩",
        "bubble": {
            "backgroundColor": "rgba(253, 239, 246, 0.94)",
            "border": "2px solid #eba9c0",
            "borderRadius": "16px",
            "padding": "10px 14px",
            "fontSize": "14px",
            "color": "#8a4a62",
        },
        "ui": {
            "bg": "#fdf1f6", "card": "#fffafc", "accent": "#d98aa8", "accent_hover": "#c77696",
            "ink": "#5c3a4a", "ink_soft": "#ad8a99", "border": "#f0d3de",
        },
    },
    "dark": {
        "label": "深色护眼",
        "bubble": {
            "backgroundColor": "rgba(44, 44, 56, 0.94)",
            "border": "2px solid #6a6a7e",
            "borderRadius": "16px",
            "padding": "10px 14px",
            "fontSize": "14px",
            "color": "#f0f0f4",
        },
        "ui": {
            "bg": "#2b2b34", "card": "#373741", "accent": "#c4a574", "accent_hover": "#b59668",
            "ink": "#e8e8ec", "ink_soft": "#9b9ba6", "border": "#4a4a58",
        },
    },
}

DEFAULT_THEME = "pet"


def _default() -> Dict[str, Any]:
    return {"version": 2, "theme": DEFAULT_THEME}


def _load_raw() -> Dict[str, Any]:
    if not os.path.isfile(APPEARANCE_PATH):
        return {}
    try:
        with open(APPEARANCE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_appearance() -> Dict[str, Any]:
    """返回当前外观配置（含默认值）。兼容旧版 bubble_theme 键。"""
    raw = _load_raw()
    theme = raw.get("theme") or raw.get("bubble_theme") or DEFAULT_THEME
    theme = theme if theme in THEMES else DEFAULT_THEME
    return {"version": 2, "theme": theme}


def save_appearance(theme: Optional[str] = None) -> Dict[str, Any]:
    """保存外观主题（空值保留原值），返回合并后的完整配置。"""
    cfg = load_appearance()
    if theme is not None and theme in THEMES:
        cfg["theme"] = theme
    try:
        os.makedirs(os.path.dirname(APPEARANCE_PATH), exist_ok=True)
        with open(APPEARANCE_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return cfg


def get_theme() -> str:
    return load_appearance().get("theme", DEFAULT_THEME)


def get_bubble_style(name: str) -> Optional[Dict[str, Any]]:
    """按主题名取 bubble 样式；'pet' 或未知返回 None（表示跟随宠物）。"""
    entry = THEMES.get(name)
    return (entry or {}).get("bubble")


def get_ui_style(name: str) -> Dict[str, str]:
    """按主题名取 UI 色板（缺省回退暖色）。"""
    entry = THEMES.get(name)
    ui = (entry or {}).get("ui")
    if not ui:
        ui = THEMES["pet"]["ui"]
    return dict(ui)


def list_themes() -> List[Tuple[str, str]]:
    """返回 [(key, label)]，用于外观面板。"""
    return [(key, entry["label"]) for key, entry in THEMES.items()]


# ---- 兼容别名（旧调用）----
list_bubble_themes = list_themes
