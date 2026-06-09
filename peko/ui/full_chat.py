"""
完整聊天窗口：左侧对话列表 + 右侧聊天记录，支持多轮对话记忆和持久化。
UI 风格：动物森友会 (Animal Island) — 温暖奶油色调、圆润、自然感。
"""
from __future__ import annotations
import base64
import json
import os
import uuid
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from PyQt5.QtCore import Qt, pyqtSignal, QObject, QUrl, QBuffer, QIODevice, QRectF, QSize
from PyQt5.QtGui import QFont, QColor, QIcon, QImage, QPixmap, QPainter, QPen, QPainterPath, QFontMetrics, QTextCursor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QSplitter, QFrame, QMenu, QAction,
    QSizePolicy, QDialog,
)

if TYPE_CHECKING:
    from ..ai.agent import AgentLoop


# ─── 头像与 HTML 工具 ───────────────────────────────────────────

def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )


AVATAR_SIZE = 48
AVATAR_FRAME_SIZE = 52


def _png_avatar_uri(name: str, bg: str, size: int = AVATAR_SIZE) -> str:
    """用 QPainter 画方形圆角头像 PNG → data URI（QTextBrowser 兼容性好）。"""
    letter = (name or "?")[0]
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    # 方形圆角背景
    r = int(size * 0.22)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), r, r)
    p.fillPath(path, QColor(bg))
    # 居中字母
    p.setPen(QPen(QColor("#ffffff")))
    font = QFont("Microsoft YaHei", max(9, size // 4), QFont.Bold)
    p.setFont(font)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, letter)
    p.end()
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(buf.data())).decode("ascii")


def _resolve_ai_avatar_path(icon_path: str) -> str:
    if not icon_path:
        return ""
    if os.path.isabs(icon_path):
        return icon_path
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, icon_path)


def _image_uri(path: str, fallback_name: str, fallback_bg: str, size: int, rounded_rect: bool = False) -> str:
    if not path or not os.path.exists(path):
        return _png_avatar_uri(fallback_name, fallback_bg, size)
    try:
        pil = _pil_load_and_fit(path, size, rounded_rect)
        if pil is not None:
            return _pil_data_uri(pil)
    except Exception:
        pass
    return _pilqt_data_uri(path, size, rounded_rect)


def _pil_load_and_fit(path: str, size: int, rounded_rect: bool):
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        return None
    img = Image.open(path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x, y = (size - img.width) // 2, (size - img.height) // 2
    canvas.paste(img, (x, y), img if img.mode == "RGBA" else None)
    if rounded_rect:
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        r = int(size * 0.22)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=255)
        bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        bg.paste(canvas, mask=mask)
        canvas = bg
    return canvas


def _pil_data_uri(pil_image) -> str:
    from io import BytesIO
    buf = BytesIO()
    pil_image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _pilqt_data_uri(path: str, size: int, rounded_rect: bool = False) -> str:
    img = QImage(path)
    if img.isNull():
        return _png_avatar_uri("?", "#FFB74D", size)
    img = img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    canvas = QImage(size, size, QImage.Format_ARGB32)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing)
    cx, cy = (size - img.width()) // 2, (size - img.height()) // 2
    if rounded_rect:
        r = int(size * 0.22)
        path_clip = QPainterPath()
        path_clip.addRoundedRect(QRectF(0, 0, size, size), r, r)
        p.setClipPath(path_clip)
    p.drawImage(cx, cy, img)
    p.end()
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    canvas.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(buf.data())).decode("ascii")


def _avatar_raster_size(dpr: float) -> int:
    return max(64, int(AVATAR_SIZE * max(1.0, dpr)))


# ─── 圆角气泡图片 ─────────────────────────────────────────────

_BUBBLE_FONT_FAMILY = "Microsoft YaHei"


def _make_bubble_image(
    text: str,
    max_width: int,
    bg_color: str,
    text_color: str = "#ffffff",
    border_color: str = "",
    font_size: int = 13,
    hpad: int = 16,
    vpad: int = 12,
    radius: int = 16,
    name: str = "",
    name_color: str = "",
) -> str:
    """用 QPainter 绘制圆角气泡 PNG → data:image base64 URI。"""
    font = QFont(_BUBBLE_FONT_FAMILY, font_size)
    fm = QFontMetrics(font)

    # 计算文字换行
    usable = max_width - hpad * 2
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            test = cur + ch
            if fm.horizontalAdvance(test) > usable:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)

    text_h = fm.lineSpacing() * len(lines)

    # 名字标签
    name_h = 0
    name_fm = None
    if name:
        name_font = QFont(_BUBBLE_FONT_FAMILY, 11)
        name_fm = QFontMetrics(name_font)
        name_h = name_fm.height() + 4

    total_h = vpad * 2 + text_h + name_h
    bubble_w = min(max_width, max((fm.horizontalAdvance(l) + hpad * 2 for l in lines), default=60))
    bubble_w = max(bubble_w, 60)

    img = QImage(QSize(bubble_w, total_h), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # 圆角背景
    path = QPainterPath()
    path.addRoundedRect(QRectF(0.5, 0.5, bubble_w - 1, total_h - 1), radius, radius)
    p.fillPath(path, QColor(bg_color))
    if border_color:
        p.setPen(QPen(QColor(border_color), 1.2))
        p.drawPath(path)

    # 名字
    y = vpad
    if name and name_fm:
        p.setFont(QFont(_BUBBLE_FONT_FAMILY, 11))
        p.setPen(QColor(name_color or "#A89880"))
        p.drawText(QRectF(hpad, y, bubble_w - hpad * 2, name_fm.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, name)
        y += name_h

    # 文字 — 左对齐（每行起始位置一致）
    p.setFont(font)
    p.setPen(QColor(text_color))
    for line in lines:
        p.drawText(QRectF(hpad, y, bubble_w - hpad * 2, fm.lineSpacing()),
                   Qt.AlignLeft | Qt.AlignVCenter, line)
        y += fm.lineSpacing()

    p.end()
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(buf.data())).decode("ascii")


# ─── Animal Island UI 样式 ──────────────────────────────────────

from .theme import (
    BG_CREAM, BG_CONTENT, BG_SIDEBAR, BG_HOVER, BG_SELECTED, BG_INPUT,
    TEXT_PRIMARY, TEXT_BODY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER_LIGHT, BORDER_WARM, ACCENT, ACCENT_HOVER,
    BTN_GREEN, BTN_GREEN_HOVER, BTN_GREEN_PRESS, BTN_DISABLED,
    RADIUS_SM, RADIUS_BASE, RADIUS_LG, RADIUS_PILL,
    FONT_FAMILY, FONT_SIZE_SM, FONT_SIZE_BASE, FONT_SIZE_LG, FONT_SIZE_TITLE,
    LIST_ITEM_QSS,
)
from .round_button import RoundButton

_WINDOW_STYLE = f"""
QWidget#fullChatWindow {{
    background: {BG_CREAM};
    font-family: {FONT_FAMILY};
}}

/* ── 侧边栏 ── */
QFrame#sidebar {{
    background: {BG_SIDEBAR};
    border: none;
}}

/* ── 通用按钮 ── */
QPushButton {{
    font-size: {FONT_SIZE_BASE}px;
    border-radius: {RADIUS_PILL}px;
    padding: 8px 18px;
    border: none;
    font-family: {FONT_FAMILY};
}}

/* ── 新对话按钮 ── */
QPushButton#newChatBtn {{
    background: {BTN_GREEN};
    color: {TEXT_PRIMARY};
    font-weight: bold;
    font-size: {FONT_SIZE_BASE}px;
    padding: 10px 18px;
    border-radius: {RADIUS_PILL}px;
    border: 2px solid {BTN_GREEN};
}}
QPushButton#newChatBtn:hover {{
    background: {BTN_GREEN_HOVER};
    border-color: {BTN_GREEN_HOVER};
}}
QPushButton#newChatBtn:pressed {{
    background: {BTN_GREEN_PRESS};
    border-color: {BTN_GREEN_PRESS};
}}

/* ── 发送按钮 ── */
QPushButton#sendBtn {{
    background: {BTN_GREEN};
    color: {TEXT_PRIMARY};
    font-weight: bold;
    font-size: {FONT_SIZE_BASE}px;
    padding: 10px 24px;
    border-radius: {RADIUS_PILL}px;
    border: 2px solid {BTN_GREEN};
}}
QPushButton#sendBtn:hover {{
    background: {BTN_GREEN_HOVER};
    border-color: {BTN_GREEN_HOVER};
}}
QPushButton#sendBtn:pressed {{
    background: {BTN_GREEN_PRESS};
    border-color: {BTN_GREEN_PRESS};
}}
QPushButton#sendBtn:disabled {{
    background: {BTN_DISABLED};
    color: {TEXT_MUTED};
    border-color: {BTN_DISABLED};
}}

/* ── 输入框 ── */
QLineEdit#chatInput {{
    font-size: {FONT_SIZE_BASE}px;
    border: 2px solid {BORDER_LIGHT};
    border-radius: {RADIUS_PILL}px;
    padding: 10px 18px;
    background: {BG_INPUT};
    font-family: {FONT_FAMILY};
    color: {TEXT_BODY};
}}
QLineEdit#chatInput:hover {{
    border-color: {TEXT_SECONDARY};
}}
QLineEdit#chatInput:focus {{
    border-color: {ACCENT};
    background: #ffffff;
}}

/* ── 聊天显示区 ── */
QTextBrowser#chatDisplay {{
    background: {BG_CREAM};
    border: none;
    font-size: {FONT_SIZE_BASE}px;
    padding: 12px 16px;
    font-family: {FONT_FAMILY};
}}

/* ── 对话列表 ── */
{LIST_ITEM_QSS}

/* ── 标题标签 ── */
QLabel#titleLabel {{
    font-size: {FONT_SIZE_TITLE}px;
    font-weight: bold;
    color: {TEXT_PRIMARY};
    padding: 12px 0;
}}
QLabel#emptyHint {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_BASE}px;
}}
QLabel#chatHeader {{
    font-size: {FONT_SIZE_TITLE}px;
    font-weight: bold;
    color: {TEXT_PRIMARY};
    padding: 8px 4px;
    border-bottom: 2px solid {BG_HOVER};
}}
"""


# ─── 信号桥 ──────────────────────────────────────────────────────

class _SignalBridge(QObject):
    """跨线程信号桥。"""
    token_received = pyqtSignal(str)
    status_update = pyqtSignal(str)
    reply_finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)


# ─── 主窗口 ──────────────────────────────────────────────────────

class FullChatWindow(QWidget):
    """
    完整聊天窗口 (Animal Island 风格)。
    左侧：对话列表（右键重命名/删除）
    右侧：气泡聊天记录 + 输入框
    """
    closed = pyqtSignal()

    def __init__(
        self,
        parent=None,
        agent_loop: Optional["AgentLoop"] = None,
        system_prompt: str = "",
        pet_name: str = "Peko",
        pet_icon_path: str = "",
    ):
        super().__init__(parent)
        self._agent = agent_loop
        self._system_prompt = system_prompt
        self._pet_name = pet_name or "Peko"
        dpr = (
            float(self.devicePixelRatioF())
            if hasattr(self, "devicePixelRatioF")
            else float(self.devicePixelRatio())
        )
        raster_size = _avatar_raster_size(dpr)
        self._pet_avatar_uri = _image_uri(
            _resolve_ai_avatar_path("peko/resource/ai_chat_avatar.png"),
            self._pet_name,
            "#FFB74D",
            raster_size,
            rounded_rect=True,
        )
        self._user_avatar_uri = _png_avatar_uri("我", "#66BB6A", size=AVATAR_SIZE)
        self._current_conv: Optional[Dict[str, Any]] = None
        self._is_streaming = False
        self._streaming_row: Optional[str] = None
        self._suppress_item_changed = False

        self._signals = _SignalBridge()
        self._signals.token_received.connect(self._on_token)
        self._signals.status_update.connect(self._on_status)
        self._signals.reply_finished.connect(self._on_reply_done)
        self._signals.error_occurred.connect(self._on_error)

        self._init_ui()
        self._load_conv_list()
        self.setStyleSheet(_WINDOW_STYLE)

    def _init_ui(self):
        self.setObjectName("fullChatWindow")
        self.setWindowTitle("🐹 Peko 聊天助手")
        self.setMinimumSize(720, 480)
        self.resize(860, 580)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── 顶部标题栏 ──
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setStyleSheet(f"""
            QFrame#topBar {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {BG_SIDEBAR}, stop:0.5 {BG_CREAM}, stop:1 {BG_CONTENT});
                border-bottom: 2px solid {BORDER_LIGHT};
                padding: 0px;
            }}
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 10, 20, 10)
        top_layout.setSpacing(10)

        app_icon = QLabel("🐹")
        app_icon.setStyleSheet("font-size: 22px;")
        top_layout.addWidget(app_icon)

        app_title = QLabel("Peko 聊天助手")
        app_title.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_TITLE}px;
            font-weight: 700;
            font-family: {FONT_FAMILY};
        """)
        top_layout.addWidget(app_title)
        top_layout.addStretch()

        # 右侧可放状态指示等
        self._top_status = QLabel("🟢 已连接")
        self._top_status.setStyleSheet(f"""
            color: {TEXT_MUTED};
            font-size: {FONT_SIZE_SM}px;
            font-family: {FONT_FAMILY};
        """)
        top_layout.addWidget(self._top_status)

        root_layout.addWidget(top_bar)

        # ── 主体区域（左右分栏）──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(0)
        body.addWidget(splitter)

        # ── 左侧栏 ──
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(280)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)
        sb_layout.setSpacing(12)

        title = QLabel("🍃 对话列表")
        title.setObjectName("titleLabel")
        sb_layout.addWidget(title)

        self._new_btn = RoundButton("＋ 新对话", radius=12)
        self._new_btn.clicked.connect(self._new_conversation)
        sb_layout.addWidget(self._new_btn)

        self._conv_list = QListWidget()
        self._conv_list.setObjectName("convList")
        self._conv_list.currentRowChanged.connect(self._on_conv_selected)
        self._conv_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._conv_list.customContextMenuRequested.connect(self._show_context_menu)
        self._conv_list.itemChanged.connect(self._on_item_changed)
        self._conv_list.setSpacing(0)
        self._conv_list.setUniformItemSizes(True)
        sb_layout.addWidget(self._conv_list, 1)

        hint = QLabel("右键可重命名 / 删除")
        hint.setObjectName("emptyHint")
        hint.setAlignment(Qt.AlignCenter)
        sb_layout.addWidget(hint)

        splitter.addWidget(sidebar)

        # ── 右侧聊天区 ──
        chat_area = QWidget()
        ca_layout = QVBoxLayout(chat_area)
        ca_layout.setContentsMargins(16, 14, 16, 14)
        ca_layout.setSpacing(10)

        self._chat_header = QLabel("选择或新建一个对话")
        self._chat_header.setObjectName("chatHeader")
        ca_layout.addWidget(self._chat_header)

        self._display = QTextBrowser()
        self._display.setObjectName("chatDisplay")
        self._display.setOpenExternalLinks(True)
        ca_layout.addWidget(self._display, 1)

        self._empty_hint = QLabel("点击左侧「＋ 新对话」开始聊天 🐹")
        self._empty_hint.setObjectName("emptyHint")
        self._empty_hint.setAlignment(Qt.AlignCenter)
        ca_layout.addWidget(self._empty_hint)

        # 输入栏
        input_bar = QHBoxLayout()
        input_bar.setSpacing(10)

        self._input = QLineEdit()
        self._input.setObjectName("chatInput")
        self._input.setPlaceholderText("输入消息...")
        self._input.returnPressed.connect(self._on_send)
        input_bar.addWidget(self._input, 1)

        self._send_btn = RoundButton("发送", radius=12)
        self._send_btn.clicked.connect(self._on_send)
        input_bar.addWidget(self._send_btn)

        ca_layout.addLayout(input_bar)

        splitter.addWidget(chat_area)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root_layout.addLayout(body, 1)

    # ─── 对话列表 ────────────────────────────────────────────────

    def _load_conv_list(self):
        self._suppress_item_changed = True
        self._conv_list.clear()
        convs = _load_conversations()
        for c in convs:
            item = QListWidgetItem(c["title"])
            item.setData(Qt.UserRole, c["id"])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            self._conv_list.addItem(item)
        self._suppress_item_changed = False

    def _on_conv_selected(self, row: int):
        if self._suppress_item_changed:
            return
        if row < 0:
            return
        item = self._conv_list.item(row)
        if not item:
            return
        conv_id = item.data(Qt.UserRole)
        if self._current_conv and self._current_conv.get("id") == conv_id:
            return
        self._current_conv = _load_conversation(conv_id)
        self._render_messages()
        self._chat_header.setText(self._current_conv.get("title", "对话"))
        self._empty_hint.hide()

    def _new_conversation(self):
        conv_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        conv = {
            "id": conv_id,
            "title": "新对话",
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        _save_conversation(conv)
        self._current_conv = conv
        self._suppress_item_changed = True
        self._load_conv_list()
        self._suppress_item_changed = True  # keep suppressed through setCurrentRow
        if self._conv_list.count() > 0:
            self._conv_list.setCurrentRow(0)
        self._suppress_item_changed = False
        self._render_messages()
        self._input.setFocus()
        if self._agent:
            self._agent.clear()

    # ─── 右键菜单：重命名 / 删除 ─────────────────────────────────

    def _show_context_menu(self, pos):
        item = self._conv_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {BG_INPUT};
                border: 2px solid {BG_HOVER};
                border-radius: {RADIUS_BASE}px;
                padding: 6px 0px;
                font-size: {FONT_SIZE_BASE}px;
            }}
            QMenu::item {{
                padding: 10px 28px;
                color: {TEXT_PRIMARY};
                border-radius: {RADIUS_SM}px;
                margin: 2px 6px;
            }}
            QMenu::item:selected {{
                background: {BG_SELECTED};
                color: {TEXT_PRIMARY};
            }}
        """)

        rename_action = QAction("✏️ 重命名", self)
        rename_action.triggered.connect(lambda: self._rename_selected(item))
        menu.addAction(rename_action)

        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(lambda: self._delete_selected(item))
        menu.addAction(delete_action)

        menu.exec_(self._conv_list.viewport().mapToGlobal(pos))

    def _rename_selected(self, item: QListWidgetItem):
        self._conv_list.editItem(item)

    def _on_item_changed(self, item: QListWidgetItem):
        if self._suppress_item_changed:
            return
        conv_id = item.data(Qt.UserRole)
        new_title = item.text().strip()
        if not new_title:
            return
        _rename_conversation(conv_id, new_title)
        if self._current_conv and self._current_conv["id"] == conv_id:
            self._current_conv["title"] = new_title
            self._chat_header.setText(new_title)

    def _delete_selected(self, item: QListWidgetItem):
        conv_id = item.data(Qt.UserRole)
        title = item.text()
        dlg = QDialog(self)
        dlg.setWindowTitle("删除对话")
        dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        dlg.setAttribute(Qt.WA_TranslucentBackground)
        dlg.setFixedSize(360, 210)

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame(dlg)
        container.setObjectName("dialogContainer")
        container.setStyleSheet(f"""
            QFrame#dialogContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_CREAM}, stop:1 {BG_CONTENT});
                border: 2px solid {BORDER_WARM};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(24, 20, 24, 18)
        c_layout.setSpacing(14)

        # 标题
        title_lbl = QLabel("⚠ 确认删除")
        title_lbl.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_LG}px;
            font-weight: 700;
            font-family: {FONT_FAMILY};
        """)
        c_layout.addWidget(title_lbl)

        # 内容
        safe_title = title[:18] + "…" if len(title) > 18 else title
        msg = QLabel(f"确定删除「{safe_title}」？此操作不可撤销。")
        msg.setStyleSheet(f"color: {TEXT_BODY}; font-size: {FONT_SIZE_BASE}px; font-family: {FONT_FAMILY};")
        msg.setWordWrap(True)
        c_layout.addWidget(msg)

        c_layout.addStretch()

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        cancel_btn = QPushButton("取消", dlg)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INPUT};
                color: {TEXT_BODY};
                font-size: {FONT_SIZE_BASE}px;
                font-weight: 500;
                border: 2px solid {BORDER_LIGHT};
                border-radius: {RADIUS_PILL}px;
                padding: 8px 24px;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                color: {ACCENT};
                border-color: {ACCENT};
            }}
        """)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        delete_btn = QPushButton("删除", dlg)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: #d9534f;
                color: #ffffff;
                font-size: {FONT_SIZE_BASE}px;
                font-weight: 700;
                border: 2px solid #d9534f;
                border-radius: {RADIUS_PILL}px;
                padding: 8px 24px;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                background: #c9302c;
                border-color: #c9302c;
            }}
        """)
        delete_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(delete_btn)

        c_layout.addLayout(btn_row)
        outer.addWidget(container)

        if dlg.exec_() != QDialog.Accepted:
            return

        _delete_conversation(conv_id)

        if self._current_conv and self._current_conv["id"] == conv_id:
            self._current_conv = None
            self._display.clear()
            self._chat_header.setText("选择或新建一个对话")
            self._empty_hint.show()

        self._load_conv_list()

        if self._conv_list.count() > 0:
            self._conv_list.setCurrentRow(0)
        if self._agent:
            self._agent.clear()

    # ─── 消息渲染 ────────────────────────────────────────────────

    def _render_messages(self):
        self._display.clear()
        self._display.setHtml(self._build_welcome_html())
        if not self._current_conv:
            return
        for msg in self._current_conv.get("messages", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                self._append_bubble(content, is_user=True)
            elif role == "assistant":
                self._append_bubble(content, is_user=False)
            elif role == "tool_status":
                self._append_tool_status(content)

    def _build_welcome_html(self) -> str:
        return f"""
        <body style="margin:0; padding:4px 0; font-family:{FONT_FAMILY};">
        </body>
        """

    def _append_bubble(self, text: str, is_user: bool, ts: str = ""):
        # 计算气泡最大宽度：聊天区宽度的 65%（留出头像空间）
        disp_w = self._display.viewport().width() if self._display.viewport().width() > 100 else 500
        max_bubble_w = int(disp_w * 0.65)

        avatar_td = (
            f'<td valign="top" width="{AVATAR_FRAME_SIZE}">'
            f'<img src="{self._user_avatar_uri}" width="{AVATAR_SIZE}" height="{AVATAR_SIZE}"/>'
            f'</td>'
            if is_user else
            f'<td valign="top" width="{AVATAR_FRAME_SIZE}">'
            f'<img src="{self._pet_avatar_uri}" width="{AVATAR_SIZE}" height="{AVATAR_SIZE}"/>'
            f'</td>'
        )

        # 时间戳 HTML
        ts_html = ""
        if ts:
            ts_html = (
                f'<div style="font-size:10px; color:{TEXT_MUTED}; margin:2px 0; font-family:{FONT_FAMILY};">{ts}</div>'
            )

        if is_user:
            uri = _make_bubble_image(
                text, max_bubble_w,
                bg_color="#8FBC8F",   # 鼠尾草绿
                text_color="#ffffff",
                font_size=13, radius=16,
            )
            html = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0;">
              <tr>
                <td width="10%"></td>
                <td align="right" valign="top" style="padding-right:8px;">
                  {ts_html}
                  <img src="{uri}"/>
                </td>
                {avatar_td}
              </tr>
            </table>
            """
        else:
            safe_name = _escape_html(self._pet_name)
            uri = _make_bubble_image(
                text, max_bubble_w,
                bg_color=BG_INPUT,
                text_color=TEXT_PRIMARY,
                border_color=BORDER_LIGHT,
                font_size=13, radius=16,
                name=safe_name, name_color=TEXT_MUTED,
            )
            html = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0;">
              <tr>
                {avatar_td}
                <td align="left" valign="top" style="padding-left:8px;">
                  {ts_html}
                  <img src="{uri}"/>
                </td>
                <td width="10%"></td>
              </tr>
            </table>
            """
        self._display.append(html)
        self._scroll_to_bottom()

    def _append_tool_status(self, text: str):
        safe_text = _escape_html(text)
        html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 10px 0;">
          <tr>
            <td align="center">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td bgcolor="{BG_HOVER}" style="color:{TEXT_MUTED}; font-size:13px;
                      padding:6px 16px; font-style:italic; border-radius:8px;">
                    {safe_text}
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
        """
        self._display.append(html)
        self._scroll_to_bottom()

    def _remove_last_block(self):
        """移除 QTextBrowser 最后一个 block（用于清除"思考中"状态）。"""
        doc = self._display.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)
        cursor.movePosition(QTextCursor.PreviousBlock, QTextCursor.MoveAnchor)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()

    def _scroll_to_bottom(self):
        sb = self._display.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ─── 发送消息 ────────────────────────────────────────────────

    def _on_send(self):
        if self._is_streaming:
            return
        text = self._input.text().strip()
        if not text:
            return
        if not self._current_conv:
            self._new_conversation()

        _now = datetime.now().strftime("%H:%M")
        self._append_bubble(text, is_user=True, ts=_now)
        self._current_conv["messages"].append({"role": "user", "content": text})

        user_msgs = [m for m in self._current_conv["messages"] if m.get("role") == "user"]
        if len(user_msgs) == 1:
            self._current_conv["title"] = text[:15] + ("..." if len(text) > 15 else "")
            _save_conversation(self._current_conv)
            self._suppress_item_changed = True
            self._load_conv_list()
            self._suppress_item_changed = True  # keep suppressed through setCurrentRow
            for i in range(self._conv_list.count()):
                if self._conv_list.item(i).data(Qt.UserRole) == self._current_conv["id"]:
                    self._conv_list.setCurrentRow(i)
                    break
            self._suppress_item_changed = False

        self._input.clear()
        self._is_streaming = True
        self._send_btn.setEnabled(False)
        self._append_tool_status("💭 思考中...")

        threading.Thread(target=self._run_agent, args=(text,), daemon=True).start()

    def _run_agent(self, user_input: str):
        if not self._agent:
            self._signals.error_occurred.emit("AI 未配置")
            return
        try:
            accumulated = []
            has_streamed = [False]

            def on_token(token):
                accumulated.append(token)
                has_streamed[0] = True
                self._signals.token_received.emit(token)

            def on_status(status):
                self._signals.status_update.emit(status)

            self._agent._on_token = on_token
            self._agent._on_status = on_status
            result = self._agent.chat(user_input)
            final = "".join(accumulated) if has_streamed[0] else result
            self._signals.reply_finished.emit(final)
        except Exception as e:
            self._signals.error_occurred.emit(str(e))

    # ─── 信号槽 ──────────────────────────────────────────────────

    def _on_token(self, token: str):
        if not self._current_conv:
            return
        # 首个 token：移除"思考中"状态，插入轻量流式占位块
        if not self._streaming_row:
            self._remove_last_block()
            self._append_streaming_block("...")

        self._streaming_row = self._streaming_row or ""
        self._streaming_row += token
        # 更新当前对话的消息列表
        msgs = self._current_conv["messages"]
        if msgs and msgs[-1].get("role") == "assistant":
            msgs[-1]["content"] = self._streaming_row
        else:
            msgs.append({"role": "assistant", "content": self._streaming_row})
        # 更新文档中的流式块（轻量，无 PNG 生成）
        safe_text = _escape_html(self._streaming_row).replace("\n", "<br/>")
        self._update_streaming_block(safe_text)

    def _on_status(self, status: str):
        self._append_tool_status(status)

    def _on_reply_done(self, full_text: str):
        self._is_streaming = False
        self._send_btn.setEnabled(True)
        # 移除流式占位块，插入最终气泡
        self._remove_streaming_block()
        self._streaming_row = None

        if not self._current_conv:
            return

        _now = datetime.now().strftime("%H:%M")
        self._append_bubble(full_text, is_user=False, ts=_now)
        self._current_conv["messages"][-1]["content"] = full_text
        _save_conversation(self._current_conv)

    def _on_error(self, error: str):
        self._is_streaming = False
        self._send_btn.setEnabled(True)
        self._remove_streaming_block()
        self._streaming_row = None
        _now = datetime.now().strftime("%H:%M")
        self._append_bubble(f"⚠️ 出错了: {error}", is_user=False, ts=_now)

    # ─── 流式占位块操作 ──────────────────────────────────────────

    def _append_streaming_block(self, text: str):
        """在 QTextBrowser 末尾追加一个轻量流式占位块（带头像）。"""
        vw = self._display.viewport().width() if self._display.viewport().width() > 100 else 500
        max_bubble_w = int(vw * 0.65)
        safe_text = _escape_html(text).replace("\n", "<br/>")
        uri = self._pet_avatar_uri
        html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0;">
          <tr>
            <td valign="top" width="{AVATAR_FRAME_SIZE}">
              <img src="{uri}" width="{AVATAR_SIZE}" height="{AVATAR_SIZE}"/>
            </td>
            <td align="left" valign="top" style="padding-left:8px;">
              <div id="streaming-block" style="background:{BG_INPUT}; border:2px solid {BORDER_LIGHT}; border-radius:16px; padding:12px 14px; font-size:13px; color:{TEXT_PRIMARY}; font-family:{FONT_FAMILY}; max-width:{max_bubble_w}px;">
                {safe_text}
              </div>
            </td>
            <td width="10%"></td>
          </tr>
        </table>
        """
        self._display.append(html)
        self._scroll_to_bottom()

    def _update_streaming_block(self, safe_text: str):
        """更新文档中最后一个流式块的文本内容。"""
        doc = self._display.document()
        # 从末尾向前搜索包含 id="streaming-block" 的 block
        block = doc.lastBlock()
        while block.isValid():
            if "streaming-block" in block.text():
                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                # 获取当前 block 的 HTML 并替换文本部分
                # 由于 QTextBrowser 的 block 结构较复杂，直接整体替换
                vw = self._display.viewport().width() if self._display.viewport().width() > 100 else 500
                max_bubble_w = int(vw * 0.65)
                new_html = (
                    f'<div id="streaming-block" style="background:{BG_INPUT}; border:2px solid {BORDER_LIGHT}; '
                    f'border-radius:16px; padding:12px 14px; font-size:13px; color:{TEXT_PRIMARY}; '
                    f'font-family:{FONT_FAMILY}; max-width:{max_bubble_w}px;">'
                    f'{safe_text}</div>'
                )
                cursor.insertHtml(new_html)
                break
            block = block.previous()
        self._scroll_to_bottom()

    def _remove_streaming_block(self):
        """移除文档中最后一个流式占位块所在的整个 table。"""
        doc = self._display.document()
        block = doc.lastBlock()
        while block.isValid():
            if "streaming-block" in block.text():
                cursor = QTextCursor(block)
                # 选中整个 block（包括前面的 table 行）
                cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.MoveAnchor)
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
                # 也移除空行
                cursor.deletePreviousChar()
                break
            block = block.previous()

    # ─── 窗口事件 ────────────────────────────────────────────────

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


# ─── 聊天历史存储 ───────────────────────────────────────────────

def _get_history_dir() -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "data", "chat_history")
    os.makedirs(path, exist_ok=True)
    return path


def _load_conversations() -> List[Dict[str, Any]]:
    idx_path = os.path.join(_get_history_dir(), "index.json")
    if os.path.exists(idx_path):
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return sorted(data, key=lambda c: c.get("updated_at", ""), reverse=True)
        except Exception:
            pass
    return []


def _save_conversations_index(convs: List[Dict[str, Any]]) -> None:
    idx_path = os.path.join(_get_history_dir(), "index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(convs, f, ensure_ascii=False, indent=2)


def _load_conversation(conv_id: str) -> Dict[str, Any]:
    path = os.path.join(_get_history_dir(), f"{conv_id}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "id": conv_id,
        "title": "新对话",
        "messages": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


def _save_conversation(conv: Dict[str, Any]) -> None:
    conv["updated_at"] = datetime.now().isoformat()
    path = os.path.join(_get_history_dir(), f"{conv['id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conv, f, ensure_ascii=False, indent=2)
    convs = _load_conversations()
    found = False
    for c in convs:
        if c["id"] == conv["id"]:
            c["title"] = conv["title"]
            c["updated_at"] = conv["updated_at"]
            found = True
            break
    if not found:
        convs.insert(0, {
            "id": conv["id"],
            "title": conv["title"],
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
        })
    _save_conversations_index(convs)


def _delete_conversation(conv_id: str) -> None:
    path = os.path.join(_get_history_dir(), f"{conv_id}.json")
    if os.path.exists(path):
        os.remove(path)
    convs = _load_conversations()
    convs = [c for c in convs if c["id"] != conv_id]
    _save_conversations_index(convs)


def _rename_conversation(conv_id: str, new_title: str) -> None:
    convs = _load_conversations()
    for c in convs:
        if c["id"] == conv_id:
            c["title"] = new_title
            break
    _save_conversations_index(convs)
    path = os.path.join(_get_history_dir(), f"{conv_id}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                conv = json.load(f)
            conv["title"] = new_title
            with open(path, "w", encoding="utf-8") as f:
                json.dump(conv, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
