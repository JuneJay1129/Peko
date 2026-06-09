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
    font = QFont("Microsoft YaHei", max(10, size // 3), QFont.Bold)
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


# ─── Animal Island UI 样式 ──────────────────────────────────────

_WINDOW_STYLE = """
QWidget#fullChatWindow {
    background: #FFF8F0;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

/* ── 侧边栏 ── */
QFrame#sidebar {
    background: #F5EDE3;
    border: none;
}

/* ── 通用按钮 ── */
QPushButton {
    font-size: 15px;
    border-radius: 25px;
    padding: 8px 18px;
    border: none;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

/* ── 新对话按钮 ── */
QPushButton#newChatBtn {
    background: #9AB98C;
    color: #ffffff;
    font-weight: bold;
    font-size: 15px;
    padding: 10px 18px;
    border-radius: 25px;
}
QPushButton#newChatBtn:hover {
    background: #B5CCA8;
}
QPushButton#newChatBtn:pressed {
    background: #8AAE7A;
}

/* ── 发送按钮 ── */
QPushButton#sendBtn {
    background: #9AB98C;
    color: #ffffff;
    font-weight: bold;
    font-size: 15px;
    padding: 10px 24px;
    border-radius: 25px;
}
QPushButton#sendBtn:hover {
    background: #B5CCA8;
}
QPushButton#sendBtn:pressed {
    background: #8AAE7A;
}
QPushButton#sendBtn:disabled {
    background: #D5C9BA;
    color: #E8DDD1;
}

/* ── 输入框 ── */
QLineEdit#chatInput {
    font-size: 15px;
    border: 2px solid #E8DDD1;
    border-radius: 20px;
    padding: 10px 18px;
    background: #FFFCF7;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    selection-background-color: #F6C9B4;
}
QLineEdit#chatInput:focus {
    border-color: #9AB98C;
    background: #ffffff;
}

/* ── 聊天显示区 ── */
QTextBrowser#chatDisplay {
    background: #FFF8F0;
    border: none;
    font-size: 15px;
    padding: 12px 16px;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

/* ── 对话列表 ── */
QListWidget#convList {
    background: transparent;
    border: none;
    font-size: 15px;
    outline: none;
    padding: 4px 6px;
}
QListWidget#convList::item {
    padding: 12px 14px;
    border: none;
    border-radius: 16px;
    margin: 3px 4px;
    color: #5C4B3A;
}
QListWidget#convList::item:selected {
    background: #F4E4D0;
    color: #5C4B3A;
    font-weight: bold;
}
QListWidget#convList::item:hover:!selected {
    background: #F0E8DC;
}

/* ── 标题标签 ── */
QLabel#titleLabel {
    font-size: 17px;
    font-weight: bold;
    color: #5C4B3A;
    padding: 12px 0;
}
QLabel#emptyHint {
    color: #A89880;
    font-size: 14px;
}
QLabel#chatHeader {
    font-size: 17px;
    font-weight: bold;
    color: #5C4B3A;
    padding: 8px 4px;
    border-bottom: 2px solid #F0E8DC;
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

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(0)
        root_layout.addWidget(splitter)

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
        menu.setStyleSheet("""
            QMenu {
                background: #FFFCF7;
                border: 2px solid #F0E8DC;
                border-radius: 16px;
                padding: 6px 0px;
                font-size: 15px;
            }
            QMenu::item {
                padding: 10px 28px;
                color: #5C4B3A;
                border-radius: 12px;
                margin: 2px 6px;
            }
            QMenu::item:selected {
                background: #F4E4D0;
                color: #5C4B3A;
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
        reply = QMessageBox.question(
            self, "删除对话",
            f"确定删除「{title}」？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
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
        return """
        <body style="margin:0; padding:4px 0; font-family:'Microsoft YaHei','PingFang SC',sans-serif;">
        </body>
        """

    def _append_bubble(self, text: str, is_user: bool):
        safe_text = _escape_html(text)
        br = "border-radius:12px;"
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
                                line-height:1.6; padding:11px 15px; {br}">
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
                                line-height:1.6; padding:11px 15px; border:1px solid #E0E0E0;
                                {br}">
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

        self._append_bubble(text, is_user=True)
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
        pass

    def _on_status(self, status: str):
        self._append_tool_status(status)

    def _on_reply_done(self, full_text: str):
        self._is_streaming = False
        self._send_btn.setEnabled(True)

        if not self._current_conv:
            return

        self._append_bubble(full_text, is_user=False)
        self._current_conv["messages"].append({"role": "assistant", "content": full_text})
        _save_conversation(self._current_conv)

    def _on_error(self, error: str):
        self._is_streaming = False
        self._send_btn.setEnabled(True)
        self._append_bubble(f"⚠️ 出错了: {error}", is_user=False)

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
