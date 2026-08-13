"""
动作参数面板：用滑动条实时调整宠物的帧率、状态切换间隔、移动速度、
大小，可针对「全部」或当前宠物的某一个动作进行设置。
动作显示名称来自各宠物的 pet_config.json 中的 actionDisplayNames。
支持拖动标题栏移动面板；打开时居中显示。
"""
import sys
from typing import TYPE_CHECKING, List, Tuple

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSlider,
    QComboBox,
    QWidget,
)
if TYPE_CHECKING:
    from .pet import DesktopPet

# 标题栏高度，此区域内按下可拖动窗口
HEADER_DRAG_HEIGHT = 56

# ---- 主题色板（暖色奶油风，统一动作参数与互动面板）----
ACCENT_TOP = "#f6bd92"
ACCENT_BOTTOM = "#e08f5e"
ACCENT_TEXT = "#b9692f"
INK = "#3d2e1f"
INK_SOFT = "#7a6350"

CONTAINER_STYLE = """
    QFrame#dialogContainer {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #fff7ee, stop:1 #fdeede);
        border: 1px solid #f0d9bd;
        border-radius: 24px;
    }
"""

# 每一行的小卡片容器
ROW_CONTAINER_STYLE = """
    QFrame#rowContainer {
        background: rgba(255, 255, 255, 0.62);
        border: 1px solid rgba(232, 210, 184, 0.9);
        border-radius: 16px;
        padding: 14px 18px;
    }
"""
ROW_MIN_WIDTH = 484  # 小容器最小宽度，保证对齐一致
ROW_SPACING = 14     # 卡片之间的纵向间距

CONTENT_STYLE = """
    QLabel { font-size: 14px; color: #5b4636; }
    QLabel.paramLabel { font-weight: 700; }
    QComboBox {
        font-size: 14px;
        color: #5b4636;
        border: 1px solid #e6d4ba;
        border-radius: 12px;
        padding: 4px 12px;
        background: #fffdf8;
        min-height: 30px;
        text-align: center;
    }
    QComboBox:focus { border-color: #e0a86a; }
    QComboBox:hover { border-color: #ecc79a; background: #fff7ec; }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 32px;
        border-left: 1px solid #ecd2b1;
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #fff6ec, stop:1 #ffe6cf);
        border-top-right-radius: 11px;
        border-bottom-right-radius: 11px;
    }
    QComboBox::down-arrow {
        width: 12px;
        height: 12px;
    }
    QComboBox QAbstractItemView {
        background: #fffdf8;
        border: 1px solid #e6d4ba;
        selection-background-color: #fbe4cf;
        selection-color: #5b4636;
        padding: 2px;
    }
    QSlider::groove:horizontal {
        height: 8px;
        background: #f1e6d3;
        border-radius: 4px;
    }
    QSlider::sub-page:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #f6bd92, stop:1 #e08f5e);
        border-radius: 4px;
    }
    QSlider::handle:horizontal {
        width: 20px;
        height: 20px;
        margin: -6px 0;
        background: qradialgradient(cx:0.35, cy:0.35, radius:0.7,
            stop:0 #ffffff, stop:1 #eaa068);
        border: 2px solid #ffffff;
        border-radius: 10px;
    }
    QSlider::handle:horizontal:hover { background: qradialgradient(cx:0.35, cy:0.35, radius:0.7,
            stop:0 #ffffff, stop:1 #e08f5e); }
    QLabel.rangeLabel {
        font-size: 12px;
        color: #9a8068;
        min-width: 110px;
    }
    QLabel.valueBadge {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #f6bd92, stop:1 #e08f5e);
        color: #ffffff;
        font-size: 13px;
        font-weight: 700;
        border-radius: 12px;
        padding: 4px 12px;
        min-width: 60px;
        qproperty-alignment: AlignCenter;
    }
    QPushButton#closeBtn {
        font-size: 20px;
        font-weight: 400;
        background: rgba(255, 255, 255, 0.85);
        color: #8a715c;
        border: 1px solid #e6d4ba;
        border-radius: 18px;
        padding: 0;
        min-width: 38px;
        max-width: 38px;
        min-height: 38px;
        max-height: 38px;
    }
    QPushButton#closeBtn:hover {
        background: #fff0e2;
        color: #b9692f;
        border-color: #e0a86a;
    }
"""

# 参数范围 (min, max, 步长)
FRAME_RATE_RANGE = (1, 60)
INTERVAL_RANGE = (500, 120000)   # ms，步长 500
MOVE_SPEED_RANGE = (1, 50)
SIZE_SCALE_RANGE = (50, 200)     # 百分比，100 = 原始大小


def _action_choices(pet: "DesktopPet") -> List[Tuple[str, str]]:
    """返回 (value, display_name) 列表，首项为「全部」。显示名来自宠物配置 actionDisplayNames，未配置则用动作 key。"""
    choices = [("__all__", "全部动作")]
    labels = (pet.pet_package or {}).get("actionDisplayNames") or {}
    for key in pet.animations.keys():
        display = labels.get(key) if isinstance(labels.get(key), str) else key
        choices.append((key, display))
    return choices


def _bold(label: QLabel) -> None:
    """将 label 设为粗体，不破坏父级样式表继承的 color / font-size。"""
    f = label.font()
    f.setWeight(QFont.Bold)
    label.setFont(f)


def _badge(label: QLabel) -> None:
    """将 label 设为数值徽章样式（渐变背景 + 白字）。"""
    label.setObjectName("valueBadge")
    label.setAttribute(Qt.WA_StyledBackground, True)


class ActionParamsDialog(QDialog):
    """动作参数对话框：滑动条调整，可针对单个动作设置。"""

    def __init__(self, parent, pet: "DesktopPet"):
        super().__init__(parent)
        self.pet = pet
        self.setWindowTitle("动作参数")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(self)
        container.setObjectName("dialogContainer")
        container.setStyleSheet(CONTAINER_STYLE + ROW_CONTAINER_STYLE + CONTENT_STYLE)

        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(ROW_SPACING)
        main_layout.setContentsMargins(30, 26, 30, 26)
        main_layout.setAlignment(Qt.AlignHCenter)

        # 关闭按钮：对话框子控件，showEvent 时定位到右上角
        self._close_btn = QPushButton("×", self)
        self._close_btn.setObjectName("closeBtn")
        self._close_btn.setFixedSize(38, 38)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self.reject)

        # 针对动作：标签与下拉框同一行（小卡片）
        action_frame = QFrame()
        action_frame.setObjectName("rowContainer")
        action_frame.setMinimumWidth(ROW_MIN_WIDTH)
        action_row = QHBoxLayout(action_frame)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        action_row.setSpacing(12)
        action_label = QLabel("🐾 针对动作：")
        _bold(action_label)
        action_label.setFixedWidth(150)
        action_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        action_label.setMinimumHeight(30)
        action_row.addWidget(action_label)
        self.action_combo = QComboBox(self)
        self.action_combo.setMinimumHeight(30)
        for value, display in _action_choices(pet):
            self.action_combo.addItem(display, value)
        # 按最长动作名计算宽度，避免名称被截断
        fm = self.action_combo.fontMetrics()
        longest = max((fm.width(display) for _, display in _action_choices(pet)), default=0)
        self.action_combo.setFixedWidth(min(320, max(180, longest + 46)))
        self.action_combo.setCursor(Qt.PointingHandCursor)
        self.action_combo.setEditable(True)
        le = self.action_combo.lineEdit()
        le.setReadOnly(True)
        le.setAlignment(Qt.AlignCenter)
        self.action_combo.currentIndexChanged.connect(self._on_action_changed)
        action_row.addWidget(self.action_combo)
        action_row.addStretch()
        main_layout.addWidget(action_frame, 0, Qt.AlignHCenter)

        # 动画帧率（小卡片）
        fr_frame = QFrame()
        fr_frame.setObjectName("rowContainer")
        fr_frame.setMinimumWidth(ROW_MIN_WIDTH)
        fr_layout = QVBoxLayout(fr_frame)
        fr_layout.setContentsMargins(0, 0, 0, 0)
        fr_layout.setSpacing(8)
        self.frame_rate_label = QLabel(self)
        _badge(self.frame_rate_label)
        fr_label = QLabel("✨ 动画帧率（帧/秒）：")
        _bold(fr_label)
        fr_layout.addWidget(fr_label)
        self.frame_rate_slider = QSlider(Qt.Horizontal, self)
        self.frame_rate_slider.setRange(FRAME_RATE_RANGE[0], FRAME_RATE_RANGE[1])
        self.frame_rate_slider.valueChanged.connect(self._on_frame_rate_changed)
        fr_layout.addWidget(self._slider_row(self.frame_rate_slider, self.frame_rate_label, FRAME_RATE_RANGE))
        main_layout.addWidget(fr_frame, 0, Qt.AlignHCenter)

        # 状态切换间隔（小卡片）
        iv_frame = QFrame()
        iv_frame.setObjectName("rowContainer")
        iv_frame.setMinimumWidth(ROW_MIN_WIDTH)
        iv_layout = QVBoxLayout(iv_frame)
        iv_layout.setContentsMargins(0, 0, 0, 0)
        iv_layout.setSpacing(8)
        self.interval_label = QLabel(self)
        _badge(self.interval_label)
        iv_label = QLabel("😴 状态切换间隔（毫秒）：")
        _bold(iv_label)
        iv_layout.addWidget(iv_label)
        self.interval_slider = QSlider(Qt.Horizontal, self)
        self.interval_slider.setRange(INTERVAL_RANGE[0] // 500, INTERVAL_RANGE[1] // 500)
        self.interval_slider.valueChanged.connect(self._on_interval_changed)
        iv_layout.addWidget(self._slider_row(self.interval_slider, self.interval_label, INTERVAL_RANGE, step=500))
        main_layout.addWidget(iv_frame, 0, Qt.AlignHCenter)

        # 移动速度（小卡片）
        mv_frame = QFrame()
        mv_frame.setObjectName("rowContainer")
        mv_frame.setMinimumWidth(ROW_MIN_WIDTH)
        mv_layout = QVBoxLayout(mv_frame)
        mv_layout.setContentsMargins(0, 0, 0, 0)
        mv_layout.setSpacing(8)
        self.move_speed_label = QLabel(self)
        _badge(self.move_speed_label)
        mv_label = QLabel("🏃 移动速度（像素/帧）：")
        _bold(mv_label)
        mv_layout.addWidget(mv_label)
        self.move_speed_slider = QSlider(Qt.Horizontal, self)
        self.move_speed_slider.setRange(MOVE_SPEED_RANGE[0], MOVE_SPEED_RANGE[1])
        self.move_speed_slider.valueChanged.connect(self._on_move_speed_changed)
        mv_layout.addWidget(self._slider_row(self.move_speed_slider, self.move_speed_label, MOVE_SPEED_RANGE))
        main_layout.addWidget(mv_frame, 0, Qt.AlignHCenter)

        # 宠物大小（小卡片）
        sz_frame = QFrame()
        sz_frame.setObjectName("rowContainer")
        sz_frame.setMinimumWidth(ROW_MIN_WIDTH)
        sz_layout = QVBoxLayout(sz_frame)
        sz_layout.setContentsMargins(0, 0, 0, 0)
        sz_layout.setSpacing(8)
        self.size_label = QLabel(self)
        _badge(self.size_label)
        sz_label = QLabel("📐 宠物大小（%）：")
        _bold(sz_label)
        sz_layout.addWidget(sz_label)
        self.size_slider = QSlider(Qt.Horizontal, self)
        self.size_slider.setRange(SIZE_SCALE_RANGE[0], SIZE_SCALE_RANGE[1])
        self.size_slider.valueChanged.connect(self._on_size_changed)
        sz_layout.addWidget(self._slider_row(self.size_slider, self.size_label, SIZE_SCALE_RANGE))
        main_layout.addWidget(sz_frame, 0, Qt.AlignHCenter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        self.setFixedSize(648, 600)
        self._block_signals = False
        self._dragging = False
        self._drag_start = QPoint()
        self.setMouseTracking(True)
        self._load_for_current_action()
        self._load_size()

    def showEvent(self, event):
        """显示时再定位关闭按钮，确保对话框已应用 setFixedSize。"""
        super().showEvent(event)
        self._position_close_button()

    def _position_close_button(self):
        """将关闭按钮固定在对话框右上角（距右、距上 14px）。"""
        btn = getattr(self, "_close_btn", None)
        if btn is None:
            return
        margin = 14
        w = self.width()
        if w < 100:
            return
        x = w - btn.width() - margin
        btn.move(x, margin)
        btn.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_close_button()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() < HEADER_DRAG_HEIGHT:
            self._dragging = True
            self._drag_start = event.globalPos() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPos() - self._drag_start)
            event.accept()
        else:
            if event.pos().y() < HEADER_DRAG_HEIGHT:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _slider_row(
        self,
        slider: QSlider,
        value_label: QLabel,
        range_tuple: Tuple[int, int],
        step: int = 1,
    ) -> QWidget:
        """一行：左侧范围，中间滑动条，右侧当前值（胶囊徽标）；留足边距避免裁切。"""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(16)
        range_lbl = QLabel(f"{range_tuple[0]}–{range_tuple[1]}")
        range_lbl.setObjectName("rangeLabel")
        layout.addWidget(range_lbl)
        layout.addWidget(slider, 1)
        layout.addWidget(value_label)
        return row

    def _current_action_value(self) -> str:
        """当前下拉选中的动作 value（__all__ 或 state key）。"""
        idx = self.action_combo.currentIndex()
        return self.action_combo.itemData(idx)

    def _load_for_current_action(self) -> None:
        """根据当前选中的动作加载参数到滑动条和标签。"""
        state = self._current_action_value()
        params = self.pet.get_action_params_for_state(state if state != "__all__" else None)
        self._block_signals = True
        self.frame_rate_slider.setValue(params.get("frameRate", 10))
        # interval 存的是 500 的倍数索引
        iv = params.get("stateSwitchInterval", 5000)
        self.interval_slider.setValue(max(INTERVAL_RANGE[0] // 500, min(INTERVAL_RANGE[1] // 500, iv // 500)))
        self.move_speed_slider.setValue(params.get("moveSpeed", 15))
        self._block_signals = False
        self._update_labels()

    def _update_labels(self) -> None:
        """根据滑动条当前值更新右侧数值标签。"""
        self.frame_rate_label.setText(str(self.frame_rate_slider.value()))
        self.interval_label.setText(str(self.interval_slider.value() * 500))
        self.move_speed_label.setText(str(self.move_speed_slider.value()))
        self.size_label.setText(f"{self.size_slider.value()}%")

    def _load_size(self) -> None:
        """加载宠物大小到滑动条。"""
        scale = self.pet.get_display_scale()
        self._block_signals = True
        self.size_slider.setValue(max(SIZE_SCALE_RANGE[0], min(SIZE_SCALE_RANGE[1], int(scale * 100))))
        self._block_signals = False
        self.size_label.setText(f"{self.size_slider.value()}%")

    def _on_action_changed(self) -> None:
        """切换动作时，加载该动作的参数。"""
        self._load_for_current_action()

    def _on_frame_rate_changed(self, value: int) -> None:
        self._update_labels()
        if self._block_signals or not self.pet:
            return
        state = self._current_action_value()
        self.pet.set_action_params_for_state(
            state if state != "__all__" else None,
            frame_rate=value,
            state_switch_interval=None,
            move_speed=None,
        )

    def _on_interval_changed(self, value: int) -> None:
        ms = value * 500
        self.interval_label.setText(str(ms))
        if self._block_signals or not self.pet:
            return
        state = self._current_action_value()
        self.pet.set_action_params_for_state(
            state if state != "__all__" else None,
            frame_rate=None,
            state_switch_interval=ms,
            move_speed=None,
        )

    def _on_move_speed_changed(self, value: int) -> None:
        self._update_labels()
        if self._block_signals or not self.pet:
            return
        state = self._current_action_value()
        self.pet.set_action_params_for_state(
            state if state != "__all__" else None,
            frame_rate=None,
            state_switch_interval=None,
            move_speed=value,
        )

    def _on_size_changed(self, value: int) -> None:
        self.size_label.setText(f"{value}%")
        if self._block_signals or not self.pet:
            return
        self.pet.set_display_scale(value / 100.0)
