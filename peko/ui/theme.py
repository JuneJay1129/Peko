"""
Animal Island UI — 统一设计令牌 & 可复用 QSS 片段。

所有 Peko UI 页面共享这套配色、圆角、阴影、按钮/输入框样式，
确保视觉语言一致：温暖奶油底 + 棕色文字 + 薄荷青绿强调色。
"""

# ── 配色 ──────────────────────────────────────────────────────

# 背景色
BG_CREAM       = "#f8f8f0"   # 主背景
BG_CONTENT     = "#f7f3df"   # 内容区
BG_SIDEBAR     = "#F5EDE3"   # 侧边栏 / 次级背景
BG_HOVER       = "#f5e6c8"   # 列表项 hover
BG_SELECTED    = "#F4E4D0"   # 列表项选中
BG_INPUT       = "#fffef8"   # 输入框背景
BG_OVERLAY     = "rgba(255, 255, 255, 0.88)"  # 半透明白

# 文字色
TEXT_PRIMARY    = "#794f27"   # 标题 / 强调
TEXT_BODY       = "#725d42"   # 正文
TEXT_SECONDARY  = "#a0936e"   # 次要文字
TEXT_MUTED      = "#c4b89e"   # placeholder
TEXT_ON_DARK    = "#fefcf8"   # 深色背景上的文字

# 强调色
ACCENT          = "#19c8b9"   # 薄荷青绿（主强调）
ACCENT_HOVER    = "#11a89b"   # 强调色 hover
ACCENT_BG       = "#e8f6f5"   # 强调色浅底

# 边框色
BORDER          = "#9f927d"   # 默认边框
BORDER_LIGHT    = "#c4b89e"   # 浅边框
BORDER_WARM     = "#e2c7a5"   # 暖色边框
BORDER_INPUT    = "#c4b89e"   # 输入框边框
BORDER_FOCUS    = "#ffcc00"   # 输入框 focus 黄色光晕

# 阴影色
SHADOW_BASE     = "rgba(61, 52, 40, 0.10)"
SHADOW_SM       = "rgba(61, 52, 40, 0.06)"
SHADOW_3D       = "#bdaea0"   # 3D 按钮阴影
SHADOW_3D_DANGER = "#c94444"  # 危险按钮阴影

# 按钮色
BTN_GREEN       = "#D4B97E"   # 暖沙金按钮（发送/确认）柔和版动森 primary
BTN_GREEN_HOVER = "#E0C990"
BTN_GREEN_PRESS = "#C4A86E"
BTN_DISABLED    = "#D5C9BA"

# 状态色
MOOD_GRADIENT   = "stop:0 #f0bf77, stop:1 #d28e51"
SATIETY_GRADIENT = "stop:0 #76c17a, stop:1 #4ea861"
ENERGY_GRADIENT = "stop:0 #74b6ff, stop:1 #4c86e6"

# ── 圆角 ──────────────────────────────────────────────────────

RADIUS_SM       = 12
RADIUS_BASE     = 18
RADIUS_LG       = 24
RADIUS_PILL     = 50

# ── 字体 ──────────────────────────────────────────────────────

FONT_FAMILY     = '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", "Nunito", sans-serif'
FONT_SIZE_SM    = 12
FONT_SIZE_BASE  = 14
FONT_SIZE_LG    = 16
FONT_SIZE_TITLE = 17

# ── 通用 QSS 组件 ────────────────────────────────────────────

# 对话框容器（圆角 + 渐变背景 + 边框）
DIALOG_CONTAINER_QSS = f"""
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {BG_CREAM}, stop:1 {BG_CONTENT});
    border: 2px solid {BORDER_LIGHT};
    border-radius: {RADIUS_LG}px;
"""

# 主按钮（3D 厚阴影 — 游戏按键感）
PRIMARY_BUTTON_QSS = f"""
    QPushButton {{
        background: {BG_CREAM};
        color: {TEXT_PRIMARY};
        font-size: {FONT_SIZE_BASE}px;
        font-weight: 600;
        border: 2px solid {BG_CREAM};
        border-radius: {RADIUS_PILL}px;
        padding: 8px 20px;
        letter-spacing: 0.02em;
    }}
    QPushButton:hover {{
        border-color: {BG_CREAM};
    }}
    QPushButton:pressed {{
    }}
    QPushButton:disabled {{
        opacity: 0.5;
        color: {TEXT_MUTED};
    }}
"""

# 次要按钮（柔和 elevation）
SECONDARY_BUTTON_QSS = f"""
    QPushButton {{
        background: {BG_INPUT};
        color: {TEXT_BODY};
        font-size: {FONT_SIZE_BASE}px;
        font-weight: 500;
        border: 2px solid {BORDER_LIGHT};
        border-radius: {RADIUS_PILL}px;
        padding: 8px 20px;
    }}
    QPushButton:hover {{
        color: {ACCENT};
        border-color: {ACCENT};
    }}
    QPushButton:pressed {{
        color: {ACCENT_HOVER};
        border-color: {ACCENT_HOVER};
    }}
"""

# 关闭按钮（圆形 ×）
CLOSE_BUTTON_QSS = f"""
    QPushButton {{
        background: {BG_INPUT};
        border: 2px solid {BORDER_WARM};
        border-radius: {RADIUS_BASE}px;
        color: {TEXT_SECONDARY};
        font-size: 15px;
        font-weight: 700;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
        padding: 0;
    }}
    QPushButton:hover {{
        background: {BG_CREAM};
        border-color: {ACCENT};
        color: {TEXT_PRIMARY};
    }}
"""

# 输入框
INPUT_QSS = f"""
    QLineEdit {{
        background: {BG_INPUT};
        border: 2.5px solid {BORDER_INPUT};
        border-radius: {RADIUS_PILL}px;
        padding: 10px 18px;
        font-size: {FONT_SIZE_BASE}px;
        color: {TEXT_BODY};
        font-family: {FONT_FAMILY};
        letter-spacing: 0.01em;
    }}
    QLineEdit:hover {{
        border-color: {BORDER};
    }}
    QLineEdit:focus {{
        border-color: {BORDER_FOCUS};
        background: #ffffff;
    }}
    QLineEdit::placeholder {{
        color: {TEXT_MUTED};
    }}
"""

# 文本输入框（多行）
TEXT_EDIT_QSS = f"""
    QTextEdit {{
        background: {BG_INPUT};
        border: 2.5px solid {BORDER_INPUT};
        border-radius: {RADIUS_BASE}px;
        padding: 10px 14px;
        font-size: {FONT_SIZE_BASE}px;
        color: {TEXT_BODY};
        font-family: {FONT_FAMILY};
    }}
    QTextEdit:hover {{
        border-color: {BORDER};
    }}
    QTextEdit:focus {{
        border-color: {BORDER_FOCUS};
        background: #ffffff;
    }}
"""

# 下拉框
COMBOBOX_QSS = f"""
    QComboBox {{
        background: {BG_INPUT};
        border: 2px solid {BORDER_LIGHT};
        border-radius: 10px;
        padding: 6px 14px;
        font-size: {FONT_SIZE_BASE}px;
        color: {TEXT_BODY};
        min-height: 24px;
    }}
    QComboBox:hover {{
        border-color: {BORDER};
    }}
    QComboBox:focus {{
        border-color: {BORDER_FOCUS};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 24px;
        border: none;
        background: transparent;
    }}
    QComboBox QAbstractItemView {{
        background: {BG_INPUT};
        border: 2px solid {BORDER_LIGHT};
        border-radius: 10px;
        selection-background-color: {BG_HOVER};
        selection-color: {TEXT_PRIMARY};
        padding: 4px;
    }}
"""

# 进度条基础
PROGRESS_BAR_QSS = f"""
    QProgressBar {{
        border: none;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.7);
        text-align: center;
        height: 16px;
        font-size: 11px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
    }}
"""

# 标签样式
LABEL_TITLE_QSS = f"""
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_TITLE}px;
    font-weight: 700;
"""

LABEL_BODY_QSS = f"""
    color: {TEXT_BODY};
    font-size: {FONT_SIZE_BASE}px;
"""

LABEL_SECONDARY_QSS = f"""
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_SM}px;
"""

LABEL_MUTED_QSS = f"""
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SM}px;
"""

# 徽章
BADGE_QSS = f"""
    color: {TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 700;
    background: rgba(255, 255, 255, 0.7);
    border-radius: 10px;
    padding: 5px 10px;
"""

# 滑动条
SLIDER_QSS = f"""
    QSlider::groove:horizontal {{
        height: 8px;
        background: {BG_CONTENT};
        border-radius: 4px;
    }}
    QSlider::handle:horizontal {{
        width: 18px;
        height: 18px;
        margin: -5px 0;
        background: {BORDER_WARM};
        border-radius: 9px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {BORDER};
    }}
"""

# 列表项（卡片风格）
LIST_ITEM_QSS = f"""
    QListWidget {{
        background: transparent;
        border: none;
        outline: none;
        padding: 0px;
        spacing: 0px;
    }}
    QListWidget::item {{
        padding: 10px 18px;
        border: 2px solid {BORDER_LIGHT};
        border-radius: 20px;
        margin: 3px 0px;
        color: {TEXT_BODY};
        background: {BG_INPUT};
        min-height: 20px;
    }}
    QListWidget::item:selected {{
        background: {BG_SELECTED};
        border-color: {BORDER_WARM};
        color: {TEXT_PRIMARY};
        font-weight: bold;
    }}
    QListWidget::item:hover:!selected {{
        background: {BG_HOVER};
        border-color: {BORDER_WARM};
    }}
"""


def dialog_window_qss(object_name: str = "dialogContainer") -> str:
    """生成对话框窗口级 QSS（背景 + 字体）。"""
    return f"""
        QWidget#{object_name} {{
            background: {BG_CREAM};
            font-family: {FONT_FAMILY};
        }}
    """


def action_button_qss(object_name: str = "actionBtn") -> str:
    """交互面板动作按钮样式。"""
    return f"""
        QPushButton#{object_name} {{
            background: {BG_OVERLAY};
            border: 2px solid {BORDER_WARM};
            border-radius: {RADIUS_SM}px;
            padding: 10px 12px;
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-weight: 700;
            min-height: 38px;
        }}
        QPushButton#{object_name}:hover {{
            background: {BG_CREAM};
            border-color: {ACCENT};
            color: {ACCENT_HOVER};
        }}
    """
