"""圆角按钮 — QPainter 自绘，绕过 Qt QPushButton 的 QSS border-radius 渲染问题。"""

from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QPen

from .theme import (
    BTN_GREEN, BTN_GREEN_HOVER, BTN_GREEN_PRESS,
    TEXT_PRIMARY, FONT_SIZE_BASE,
)


class RoundButton(QPushButton):
    """支持 border-radius 的 QPushButton 替代品。

    因为 Qt Fusion/Windsows 样式下，QPushButton 在有父级 stylesheet
    时会忽略 border-radius，所以这里用 QPainter 直接绘制圆角矩形。
    """

    def __init__(
        self,
        text: str,
        parent=None,
        radius: int = 50,
        bg_color: str = BTN_GREEN,
        text_color: str = TEXT_PRIMARY,
        font_size: int = FONT_SIZE_BASE,
        bold: bool = True,
        padding_h: int = 24,
        padding_v: int = 10,
    ):
        super().__init__(text, parent)
        self._radius = radius
        self._bg = QColor(bg_color)
        self._bg_hover = QColor(BTN_GREEN_HOVER)
        self._bg_press = QColor(BTN_GREEN_PRESS)
        self._text_color = QColor(text_color)
        self._border_color = QColor(bg_color)
        self._font_size = font_size
        self._bold = bold
        self._padding_h = padding_h
        self._padding_v = padding_v
        self._hovered = False
        self._pressed = False
        self.setCursor(Qt.PointingHandCursor)

    # ── hover / press 状态跟踪 ──────────────────────

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    # ── 自绘 ──────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        r = self.rect()

        # 选颜色
        bg = self._bg
        border = self._border_color
        if self._pressed:
            bg = self._bg_press
            border = self._bg_press
        elif self._hovered:
            bg = self._bg_hover
            border = self._bg_hover

        # 圆角矩形
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(r).adjusted(1, 1, -1, -1),
            self._radius, self._radius,
        )
        painter.fillPath(path, bg)
        painter.setPen(QPen(border, 2))
        painter.drawPath(path)

        # 文字
        painter.setPen(self._text_color)
        font = self.font()
        font.setBold(self._bold)
        font.setPixelSize(self._font_size)
        painter.setFont(font)
        painter.drawText(r, Qt.AlignCenter, self.text())
