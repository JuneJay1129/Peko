"""
召唤跟班：跟随主桌宠动作的「跟班宠物」。

- 完全同步主宠的动作帧（同一宠物包，同一状态与帧索引），100ms 轮询。
- 大小三档（大/中/小 = 主宠显示尺寸的 0.9 / 0.7 / 0.5）。
- 跟随主宠位置（右上角外侧 +8px，超屏自动收进）。
- 不创建气泡、不挂聊天——纯视觉跟随，鼠标点击穿透（WA_TransparentForMouseEvents）。
- 主宠被切换/隐藏/销毁时自动退出。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QLabel, QApplication


SCALE_OPTIONS = (("大号", 2), ("中号", 1.0), ("小号", 0.5))


class FollowerPet(QWidget):
    def __init__(self, master, holder, scale: float = 0.7):
        super().__init__(
            None, Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.master = master
        self.holder = holder
        self.scale = float(scale)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label = QLabel(self)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.sync)
        self._timer.start()
        self.sync()

    def sync(self) -> None:
        """同步主宠当前动作帧与位置。"""
        try:
            if self.holder and self.holder[0] is not self.master:
                self._kill()
                return
            if not self.master.isVisible():
                self._kill()
                return
            frames = self.master.animations.get(self.master.current_state) or []
            if not frames:
                return
            idx = self.master.current_frame_index % len(frames)
            w = max(1, int(self.master.width() * self.scale))
            h = max(1, int(self.master.height() * self.scale))
            pm = QPixmap(frames[idx]).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not pm.isNull():
                self.label.setPixmap(pm)
                self.label.resize(pm.size())
                self.resize(pm.size())
            mpos = self.master.mapToGlobal(self.master.rect().topLeft())
            x = mpos.x() + self.master.width() + 8
            y = mpos.y() + self.master.height() - self.height()  # 底部对齐主宠
            screen = QApplication.desktop().screenGeometry()
            x = max(0, min(x, screen.width() - self.width()))
            y = max(0, min(y, screen.height() - self.height()))
            self.move(x, y)
        except Exception:
            self._kill()

    def _kill(self) -> None:
        self._timer.stop()
        self.hide()
        self.close()
