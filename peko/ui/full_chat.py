"""
完整聊天窗口：左侧对话列表 + 右侧聊天记录，支持多轮对话记忆和持久化。
"""
from __future__ import annotations
import base64
import json
import os
import uuid
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from PyQt5.QtCore import Qt, pyqtSignal, QObject, QUrl, QBuffer, QIODevice, QRectF
from PyQt5.QtGui import QFont, QColor, QIcon, QImage, QPainter, QPen, QPainterPath
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QSplitter, QFrame, QMenu, QAction,
    QInputDialog, QMessageBox, QSizePolicy,
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


AVATAR_SIZE = 48          # HTML 显示尺寸（略放大，细节更易辨认）
AVATAR_FRAME_SIZE = 52    # 外框固定尺寸


def _svg_avatar_uri(
    label: str,
    bg_color: str,
    text_color: str = "#ffffff",
    size: int = AVATAR_SIZE,
) -> str:
    """生成圆形文字头像的 data URI（QTextBrowser 兼容）。"""
    char = (label or "?")[0]
    half = size / 2
    font_size = max(14, int(size * 0.42))
    text_y = half + font_size * 0.35
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">'
        f'<circle cx="{half}" cy="{half}" r="{half}" fill="{bg_color}"/>'
        f'<text x="{half}" y="{text_y}" text-anchor="middle" fill="{text_color}" '
        f'font-size="{font_size}" font-family="Microsoft YaHei, PingFang SC, sans-serif">'
        f"{char}</text>"
        f"</svg>"
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _pixel_visible(color: QColor) -> bool:
    if color.alpha() < 20:
        return False
    return color.red() + color.green() + color.blue() > 40


def _crop_to_content(img: QImage) -> QImage:
    """裁掉透明/纯黑留白，让主体尽量铺满头像区域。"""
    src = img.convertToFormat(QImage.Format_ARGB32)
    w, h = src.width(), src.height()
    min_x, min_y = w, h
    max_x, max_y = 0, 0
    for y in range(h):
        for x in range(w):
            if _pixel_visible(src.pixelColor(x, y)):
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x <= min_x or max_y <= min_y:
        return src
    pad = max(2, int(min(max_x - min_x, max_y - min_y) * 0.04))
    left = max(0, min_x - pad)
    top = max(0, min_y - pad)
    right = min(w - 1, max_x + pad)
    bottom = min(h - 1, max_y + pad)
    return src.copy(left, top, right - left + 1, bottom - top + 1)


def _scale_down_sharp(img: QImage, size: int) -> QImage:
    """分步缩小；中间步骤平滑，最后一步用快速算法保留卡通线条锐度。"""
    current = img
    while max(current.width(), current.height()) > size * 2:
        nw = max(size, int(current.width() * 0.5))
        nh = max(size, int(current.height() * 0.5))
        current = current.scaled(nw, nh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return current.scaled(size, size, Qt.KeepAspectRatio, Qt.FastTransformation)


def _raster_avatar_data_uri(path: str, raster_size: int, *, circular: bool = False) -> str:
    """预渲染为固定尺寸 PNG data URI，配合显示尺寸 1:1 或接近 1:1 使用。"""
    img = QImage(path)
    if img.isNull():
        return ""
    cropped = _crop_to_content(img)
    canvas = QImage(raster_size, raster_size, QImage.Format_ARGB32)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

    if circular:
        border = max(1, int(round(raster_size / 48)))
        outer_diameter = raster_size - border
        outer = QRectF(border / 2, border / 2, outer_diameter, outer_diameter)
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#E8E8E8"), border))
        painter.drawEllipse(outer)

        inset = border + max(1, int(round(raster_size / 64)))
        inner_diameter = raster_size - inset * 2
        fitted = _scale_down_sharp(cropped, inner_diameter)
        clip = QPainterPath()
        clip.addEllipse(QRectF(inset, inset, inner_diameter, inner_diameter))
        painter.setClipPath(clip)
        x = inset + (inner_diameter - fitted.width()) // 2
        y = inset + (inner_diameter - fitted.height()) // 2
        painter.drawImage(x, y, fitted)
    else:
        fitted = _scale_down_sharp(cropped, raster_size)
        painter.fillRect(0, 0, raster_size, raster_size, QColor("#FFFFFF"))
        x = (raster_size - fitted.width()) // 2
        y = (raster_size - fitted.height()) // 2
        painter.drawImage(x, y, fitted)

    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    canvas.save(buffer, "PNG")
    encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _avatar_raster_size(device_pixel_ratio: float) -> int:
    """按屏幕 DPI 生成栅格尺寸，减少 QTextBrowser 二次缩放。"""
    dpr = max(2.0, float(device_pixel_ratio or 1.0))
    return int(round(AVATAR_SIZE * dpr))


def _image_uri(
    path: str,
    fallback_label: str,
    fallback_color: str,
    raster_size: int,
    *,
    circular: bool = False,
) -> str:
    if path and os.path.isfile(path):
        data_uri = _raster_avatar_data_uri(path, raster_size, circular=circular)
        if data_uri:
            return data_uri
        return QUrl.fromLocalFile(os.path.normpath(path)).toString()
    return _svg_avatar_uri(fallback_label, fallback_color, size=AVATAR_SIZE)


def get_ai_chat_avatar_path() -> str:
    """聊天窗口 AI 侧头像（优先使用内置资源）。"""
    bundled = os.path.join(os.path.dirname(__file__), "assets", "ai_chat_avatar.png")
    return bundled if os.path.isfile(bundled) else ""


def _resolve_ai_avatar_path(pet_icon_path: str) -> str:
    return get_ai_chat_avatar_path() or pet_icon_path


# ─── 聊天历史存储 ───────────────────────────────────────────────

def _get_history_dir() -> str:
    """获取聊天历史存储目录。"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "data", "chat_history")
    os.makedirs(path, exist_ok=True)
    return path


def _load_conversations() -> List[Dict[str, Any]]:
    """加载所有对话的索引。"""
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
    # 更新索引
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
    """重命名对话标题。"""
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


# ─── 样式 ───────────────────────────────────────────────────────

_WINDOW_STYLE = """
QWidget#fullChatWindow {
    background: #fafafa;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

/* ── 侧边栏 ── */
QFrame#sidebar {
    background: #ffffff;
    border-right: 1px solid #e8e8e8;
}

/* ── 通用按钮 ── */
QPushButton {
    font-size: 13px;
    border-radius: 8px;
    padding: 7px 16px;
    border: none;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

/* ── 新对话按钮 ── */
QPushButton#newChatBtn {
    background: #4CAF50;
    color: white;
    font-weight: bold;
    font-size: 13px;
    padding: 9px 16px;
    border-radius: 10px;
}
QPushButton#newChatBtn:hover {
    background: #43a047;
}
QPushButton#newChatBtn:pressed {
    background: #388e3c;
}

/* ── 发送按钮 ── */
QPushButton#sendBtn {
    background: #4CAF50;
    color: white;
    font-weight: bold;
    font-size: 13px;
    padding: 9px 22px;
    border-radius: 10px;
}
QPushButton#sendBtn:hover {
    background: #43a047;
}
QPushButton#sendBtn:pressed {
    background: #388e3c;
}
QPushButton#sendBtn:disabled {
    background: #c8e6c9;
    color: #a5d6a7;
}

/* ── 输入框 ── */
QLineEdit#chatInput {
    font-size: 14px;
    border: 1.5px solid #e0e0e0;
    border-radius: 20px;
    padding: 10px 18px;
    background: white;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    selection-background-color: #c8e6c9;
}
QLineEdit#chatInput:focus {
    border-color: #81c784;
    background: #fcfcfc;
}

/* ── 聊天显示区 ── */
QTextBrowser#chatDisplay {
    background: #f3f4f6;
    border: none;
    font-size: 14px;
    padding: 12px 16px;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

/* ── 对话列表 ── */
QListWidget#convList {
    background: transparent;
    border: none;
    font-size: 13px;
    outline: none;
    padding: 4px 6px;
}
QListWidget#convList::item {
    padding: 10px 12px;
    border: none;
    border-radius: 10px;
    margin: 2px 4px;
    color: #444;
}
QListWidget#convList::item:selected {
    background: #e8f5e9;
    color: #2e7d32;
    font-weight: bold;
}
QListWidget#convList::item:hover:!selected {
    background: #f5f5f5;
}

/* ── 标题标签 ── */
QLabel#titleLabel {
    font-size: 15px;
    font-weight: bold;
    color: #333;
    padding: 10px 0;
}
QLabel#emptyHint {
    color: #aaa;
    font-size: 13px;
}
QLabel#chatHeader {
    font-size: 15px;
    font-weight: bold;
    color: #333;
    padding: 6px 4px;
    border-bottom: 1px solid #eee;
}
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
    完整聊天窗口。
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
            _resolve_ai_avatar_path(pet_icon_path),
            self._pet_name,
            "#FFB74D",
            raster_size,
            circular=True,
        )
        self._user_avatar_uri = _svg_avatar_uri("我", "#66BB6A", size=AVATAR_SIZE)
        self._current_conv: Optional[Dict[str, Any]] = None
        self._is_streaming = False
        self._suppress_item_changed = False  # 防止重命名时触发 itemChanged

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

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        root_layout.addWidget(splitter)

        # ── 左侧栏 ──
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(280)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(10, 12, 10, 12)
        sb_layout.setSpacing(10)

        title = QLabel("💬 对话列表")
        title.setObjectName("titleLabel")
        sb_layout.addWidget(title)

        self._new_btn = QPushButton("＋ 新对话")
        self._new_btn.setObjectName("newChatBtn")
        self._new_btn.setCursor(Qt.PointingHandCursor)
        self._new_btn.clicked.connect(self._new_conversation)
        sb_layout.addWidget(self._new_btn)

        self._conv_list = QListWidget()
        self._conv_list.setObjectName("convList")
        self._conv_list.currentRowChanged.connect(self._on_conv_selected)
        self._conv_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._conv_list.customContextMenuRequested.connect(self._show_context_menu)
        self._conv_list.itemChanged.connect(self._on_item_changed)
        sb_layout.addWidget(self._conv_list, 1)

        # 删除提示
        hint = QLabel("右键可重命名/删除")
        hint.setObjectName("emptyHint")
        hint.setAlignment(Qt.AlignCenter)
        sb_layout.addWidget(hint)

        splitter.addWidget(sidebar)

        # ── 右侧聊天区 ──
        chat_area = QWidget()
        ca_layout = QVBoxLayout(chat_area)
        ca_layout.setContentsMargins(16, 12, 16, 12)
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

        self._send_btn = QPushButton("发送")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.clicked.connect(self._on_send)
        input_bar.addWidget(self._send_btn)

        ca_layout.addLayout(input_bar)

        splitter.addWidget(chat_area)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    # ─── 对话列表 ────────────────────────────────────────────────

    def _load_conv_list(self):
        self._suppress_item_changed = True
        self._conv_list.clear()
        convs = _load_conversations()
        for c in convs:
            item = QListWidgetItem(c["title"])
            item.setData(Qt.UserRole, c["id"])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._conv_list.addItem(item)
        self._suppress_item_changed = False

    def _on_conv_selected(self, row: int):
        if row < 0:
            return
        item = self._conv_list.item(row)
        conv_id = item.data(Qt.UserRole)
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
        self._load_conv_list()
        self._conv_list.setCurrentRow(0)
        self._input.setFocus()
        if self._agent:
            self._agent.clear()

    # ─── 右键菜单：重命名 / 删除 ─────────────────────────────────

    def _show_context_menu(self, pos):
        item = self._conv_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 4px 0px;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 24px;
                color: #333;
            }
            QMenu::item:selected {
                background: #e8f5e9;
                color: #2e7d32;
            }
        """)

        rename_action = QAction("✏️ 重命名", self)
        rename_action.triggered.connect(lambda: self._rename_selected(item))
        menu.addAction(rename_action)

        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(lambda: self._delete_selected(item))
        menu.addAction(delete_action)

        menu.exec_(self._conv_list.viewport().mapToGlobal(pos))

    def _rename_selected(self, item: QListWidgetItem):
        """就地编辑重命名。"""
        self._conv_list.editItem(item)

    def _on_item_changed(self, item: QListWidgetItem):
        """就地编辑完成，保存新标题。"""
        if self._suppress_item_changed:
            return
        conv_id = item.data(Qt.UserRole)
        new_title = item.text().strip()
        if not new_title:
            return
        _rename_conversation(conv_id, new_title)
        # 同步更新当前对话
        if self._current_conv and self._current_conv["id"] == conv_id:
            self._current_conv["title"] = new_title
            self._chat_header.setText(new_title)

    def _delete_selected(self, item: QListWidgetItem):
        """删除对话（二次确认）。"""
        conv_id = item.data(Qt.UserRole)
        title = item.text()
        reply = QMessageBox.question(
            self, "删除对话",
            f"确定删除「{title}」？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        _delete_conversation(conv_id)

        # 如果删除的是当前对话，清空右侧
        if self._current_conv and self._current_conv["id"] == conv_id:
            self._current_conv = None
            self._display.clear()
            self._chat_header.setText("选择或新建一个对话")
            self._empty_hint.show()

        self._load_conv_list()

        # 自动选中下一个
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
        return """
        <body style="margin:0; padding:4px 0; font-family:'Microsoft YaHei','PingFang SC',sans-serif;">
        </body>
        """

    def _append_bubble(self, text: str, is_user: bool):
        safe_text = _escape_html(text)
        if is_user:
            html = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:14px 0;">
              <tr>
                <td width="18%"></td>
                <td align="right" valign="top">
                  <table cellpadding="0" cellspacing="0" align="right">
                    <tr>
                      <td valign="top" align="right" style="padding-right:10px;">
                        <table cellpadding="0" cellspacing="0" align="right">
                          <tr>
                            <td bgcolor="#43A047" style="color:#ffffff; font-size:14px;
                                line-height:1.6; padding:11px 15px;">
                              {safe_text}
                            </td>
                          </tr>
                        </table>
                      </td>
                      <td valign="top" width="{AVATAR_FRAME_SIZE}">
                        <table cellpadding="0" cellspacing="0" width="{AVATAR_FRAME_SIZE}"
                               height="{AVATAR_FRAME_SIZE}">
                          <tr>
                            <td width="{AVATAR_FRAME_SIZE}" height="{AVATAR_FRAME_SIZE}"
                                align="center" valign="middle">
                              <img src="{self._user_avatar_uri}" width="{AVATAR_SIZE}"
                                   height="{AVATAR_SIZE}"/>
                            </td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
            """
        else:
            safe_name = _escape_html(self._pet_name)
            html = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:14px 0;">
              <tr>
                <td align="left" valign="top" width="82%">
                  <table cellpadding="0" cellspacing="0">
                    <tr>
                      <td valign="top" width="{AVATAR_FRAME_SIZE}">
                        <table cellpadding="0" cellspacing="0" width="{AVATAR_FRAME_SIZE}"
                               height="{AVATAR_FRAME_SIZE}">
                          <tr>
                            <td width="{AVATAR_FRAME_SIZE}" height="{AVATAR_FRAME_SIZE}"
                                align="center" valign="middle">
                              <img src="{self._pet_avatar_uri}" width="{AVATAR_SIZE}"
                                   height="{AVATAR_SIZE}"/>
                            </td>
                          </tr>
                        </table>
                      </td>
                      <td valign="top" style="padding-left:10px;">
                        <table cellpadding="0" cellspacing="0" width="100%">
                          <tr>
                            <td style="color:#888; font-size:12px; padding-bottom:5px;">
                              {safe_name}
                            </td>
                          </tr>
                          <tr>
                            <td bgcolor="#FFFFFF" style="color:#333; font-size:14px;
                                line-height:1.6; padding:11px 15px; border:1px solid #E0E0E0;">
                              {safe_text}
                            </td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>
                </td>
                <td></td>
              </tr>
            </table>
            """
        self._display.append(html)
        self._scroll_to_bottom()

    def _append_tool_status(self, text: str):
        safe_text = _escape_html(text)
        html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 12px 0;">
          <tr>
            <td align="center">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td bgcolor="#F1F3F4" style="color:#888; font-size:12px;
                      padding:5px 14px;">
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

    def _scroll_to_bottom(self) -> None:
        self._display.moveCursor(self._display.textCursor().End)

    # ─── 发送消息 ────────────────────────────────────────────────

    def _on_send(self):
        if self._is_streaming:
            return
        text = self._input.text().strip()
        if not text:
            return
        if not self._current_conv:
            self._new_conversation()

        # 显示用户消息气泡
        self._append_bubble(text, is_user=True)
        self._current_conv["messages"].append({"role": "user", "content": text})

        # 自动标题：首条消息的前 15 个字（就地更新列表，避免 setCurrentRow 重载清空聊天区）
        user_msgs = [m for m in self._current_conv["messages"] if m.get("role") == "user"]
        if len(user_msgs) == 1:
            self._current_conv["title"] = text[:15] + ("..." if len(text) > 15 else "")
            self._chat_header.setText(self._current_conv["title"])
            for i in range(self._conv_list.count()):
                item = self._conv_list.item(i)
                if item.data(Qt.UserRole) == self._current_conv["id"]:
                    self._suppress_item_changed = True
                    item.setText(self._current_conv["title"])
                    self._suppress_item_changed = False
                    break
        _save_conversation(self._current_conv)

        self._input.clear()
        self._is_streaming = True
        self._send_btn.setEnabled(False)
        self._append_tool_status("思考中...")

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
        """流式 token 到达（暂不逐步更新气泡，最后统一渲染）。"""
        pass

    def _on_status(self, status: str):
        """工具状态提示。"""
        self._append_tool_status(status)

    def _on_reply_done(self, full_text: str):
        """AI 回复完成，追加最终气泡并保存。"""
        self._is_streaming = False
        self._send_btn.setEnabled(True)

        if not self._current_conv:
            return

        self._current_conv["messages"].append({"role": "assistant", "content": full_text})
        _save_conversation(self._current_conv)
        self._render_messages()

    def _on_error(self, error: str):
        self._is_streaming = False
        self._send_btn.setEnabled(True)
        self._append_bubble(f"⚠️ 出错了: {error}", is_user=False)
        self._scroll_to_bottom()

    # ─── 窗口事件 ────────────────────────────────────────────────

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
