"""气泡 / 侧栏样式函数（从 pet.py 拆出）：跟随主题 UI 色板的 QSS 生成。"""
from typing import Any, Dict

def _bubble_action_qss() -> str:
    """气泡内安慰对话的选项按钮 / 输入框样式（跟随主题 UI 色板）。"""
    try:
        from peko.core import appearance as appearance_mod
        ui = appearance_mod.get_ui_style(appearance_mod.get_theme())
    except Exception:
        ui = {"bg": "#faf3e0", "card": "#fffef9", "accent": "#c4a574", "accent_hover": "#b59668",
              "ink": "#4a3f35", "ink_soft": "#9a8f7f", "border": "#e8dcc4"}
    return f"""
    QPushButton {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 10px;
        padding: 11px 14px;
        color: {ui['ink']};
        font-size: 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background-color: {ui['bg']}; border-color: {ui['accent']}; }}
    QPushButton:pressed {{ background-color: {ui['border']}; }}
    QLineEdit {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 10px;
        padding: 9px 12px;
        color: {ui['ink']};
        font-size: 14px;
        selection-background-color: {ui['accent']};
    }}
    QLineEdit:focus {{ border-color: {ui['accent']}; }}
"""

def _side_panel_style() -> str:
    """安慰对话侧面操作面板样式：圆角容器 + 选项按钮 + 输入框（跟随主题）。"""
    try:
        from peko.core import appearance as appearance_mod
        ui = appearance_mod.get_ui_style(appearance_mod.get_theme())
    except Exception:
        ui = {"bg": "#faf3e0", "card": "#fffef9", "accent": "#c4a574", "accent_hover": "#b59668",
              "ink": "#4a3f35", "ink_soft": "#9a8f7f", "border": "#e8dcc4"}
    return f"""
    QFrame#sidePanel {{
        background-color: {ui['bg']};
        border: 1.5px solid {ui['border']};
        border-radius: 14px;
    }}
    QLabel#sideHint {{
        color: {ui['ink_soft']};
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton#sideClose {{
        background: transparent;
        border: none;
        color: {ui['ink_soft']};
        font-size: 16px;
        padding: 0 4px;
    }}
    QPushButton#sideClose:hover {{ color: #b0554c; }}
    QPushButton {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 10px;
        padding: 11px 14px;
        color: {ui['ink']};
        font-size: 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background-color: {ui['bg']}; border-color: {ui['accent']}; }}
    QPushButton:pressed {{ background-color: {ui['border']}; }}
    QLineEdit {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 10px;
        padding: 9px 12px;
        color: {ui['ink']};
        font-size: 14px;
        selection-background-color: {ui['accent']};
    }}
    QLineEdit:focus {{ border-color: {ui['accent']}; }}
"""

def _default_bubble_style() -> str:
    return """
        background-color: rgba(255, 255, 255, 0.72);
        border: 2px solid rgba(76, 175, 80, 0.85);
        border-radius: 15px;
        border-top-left-radius: 15px;
        border-top-right-radius: 15px;
        border-bottom-left-radius: 15px;
        border-bottom-right-radius: 15px;
        padding: 12px;
        font-size: 15px;
        color: black;
    """

def _bubble_style_from_config(bubble_style: Dict[str, Any]) -> str:
    """从宠物包的 bubbleStyle 生成 QSS（可扩展）。"""
    if not bubble_style:
        return _default_bubble_style()
    bg = bubble_style.get("backgroundColor", "rgba(255, 255, 255, 0.72)")
    border = bubble_style.get("border", "2px solid rgba(76, 175, 80, 0.85)")
    radius = bubble_style.get("borderRadius", "15px")
    padding = bubble_style.get("padding", "10px")
    font_size = bubble_style.get("fontSize", "15px")
    color = bubble_style.get("color", "black")
    return f"""
        background-color: {bg};
        border: {border};
        border-radius: {radius};
        border-top-left-radius: {radius};
        border-top-right-radius: {radius};
        border-bottom-left-radius: {radius};
        border-bottom-right-radius: {radius};
        padding: {padding};
        font-size: {font_size};
        color: {color};
    """
