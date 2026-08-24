"""
摧毁表演：托盘「摧毁文件…」→ 选文件 → 点一下文件在屏幕上的位置 → 宠物跑过去
→ listen 确认 → smash 砸烂 → 砰！→ 回收站 → wave 庆祝。

- 仅对拥有 smash 动作的宠物开放（BB）；无 smash 动作的宠物气泡婉拒，不删除。
- 删除优先 send2trash，失败回退 PowerShell（VisualBasic FileSystem，进回收站）；
  全程有确认，真实错误写入日志并在气泡给出简要原因。
- 五阶段：walk 长途跑过去 → listen 确认 → smash 砸烂（命中瞬间浮字「砰！」+ 删文件）
  → wave 庆祝 → stand 收场。
- 全部为调用侧编排：直接操作 pet 的 current_state / 定时器（与 actions/control.py 同约定），
  不改公共动作逻辑。
"""
from __future__ import annotations

import os
import subprocess
import traceback
from typing import Callable, List, Optional

from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

STATE_CONFIRM = "listen"      # 确认：竖耳倾听
STATE_ATTACK = "smash"        # 摧毁：砸烂（攻击文件动作素材）
STATE_CELEBRATE = "wave"      # 庆祝：挥手
WALK_MIN_MS = 800             # 跑向目标的最短时长
WALK_MAX_MS = 4000            # 跑向目标的最长时长
DESTROY_DURATION_MS = 3000    # 摧毁（砸烂）动画总时长
DESTROY_STRIKE_MS = 1650      # 砸烂「命中」时刻（浮字+删除）
CELEBRATE_DURATION_MS = 2500  # 庆祝（挥手）时长

_UNSET = object()             # 哨兵：标记动作原本未单独设置 moveSpeed

# 狙击遮罩的半透明背景图（大脸.png，攻击文件动作素材）。
# 缺失时回退为 alpha=1 的不可见底色，保证功能仍可用。
_BG_IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "大脸.png")
_OVERLAY_BG_OPACITY = 0.6      # 背景图不透明度 0~1：越大越不透明（仍透出桌面图标）

_CONTAINER_STYLE = """
    QFrame#destroyContainer {
        background-color: rgba(255, 255, 255, 0.95);
        border: 2px solid #4CAF50;
        border-radius: 15px;
        padding: 10px;
    }
"""
_CONTENT_STYLE = """
    QLabel#destroyText { font-size: 14px; color: black; font-weight: bold; }
    QLabel#destroySub { font-size: 11px; color: #888888; }
    QPushButton#destroyOk {
        font-size: 13px; background-color: #E24B4A; color: white;
        border-radius: 8px; padding: 5px 16px;
    }
    QPushButton#destroyOk:hover { background-color: #C93A3A; }
    QPushButton#destroyNo {
        font-size: 13px; background-color: #F1EFE8; color: #444444;
        border-radius: 8px; padding: 5px 16px;
    }
    QPushButton#destroyNo:hover { background-color: #E2E0D5; }
"""


def _state_duration_ms(pet, state: str) -> int:
    """一个动作完整播一遍的时长（帧数 × 帧间隔 + 缓冲）。"""
    frames = pet.animations.get(state) or []
    if not frames:
        return 0
    cfg = pet._state_config.get(state, {})
    fps = max(1, int(cfg.get("frameRate") or pet.frame_rate))
    return int(len(frames) * (1000 / fps)) + 150


def _play_once(pet, state: str, on_done: Callable[[], None]) -> None:
    """切换到指定动作（循环帧），播完一遍后回调。动作缺失则立即回调。"""
    duration = _state_duration_ms(pet, state)
    if duration <= 0:
        QTimer.singleShot(0, on_done)
        return
    pet.current_state = state
    pet.current_frame_index = 0
    pet._apply_state_frame_rate()
    pet.update_frame()
    QTimer.singleShot(duration, on_done)


def _trash_one(path: str) -> Optional[str]:
    """把一个文件送进回收站；成功返回 None，失败返回错误原因。每步成败都打印控制台。"""
    if not os.path.exists(path):
        return "文件不存在"
    first_err = ""
    try:
        from send2trash import send2trash
        send2trash(path)
        if not os.path.exists(path):
            print(f"[Peko 摧毁] send2trash 成功: {path}")
            return None
        first_err = "send2trash 调用成功但文件仍在"
        print(f"[Peko 摧毁] send2trash 未生效: {path}")
    except Exception as e:
        first_err = f"{type(e).__name__}: {e}"
        print(f"[Peko 摧毁] send2trash 失败: {path}")
        traceback.print_exc()
    # 回退：PowerShell VisualBasic FileSystem（进回收站）
    try:
        esc = path.replace("'", "''")
        ps = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('{esc}', 'OnlyErrorDialogs', 'SendToRecycleBin')"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=30,
        )
        if not os.path.exists(path):
            print(f"[Peko 摧毁] PowerShell 回退成功: {path}")
            return None
        err_out = proc.stderr.decode("utf-8", "ignore").strip()
        if err_out:
            print(f"[Peko 摧毁] PowerShell 回退输出: {err_out}")
        return first_err or "删除未生效"
    except Exception as e2:
        print(f"[Peko 摧毁] PowerShell 回退异常: {path}")
        traceback.print_exc()
        return first_err or f"{type(e2).__name__}: {e2}"


class _TargetOverlay(QWidget):
    """全屏狙击层：半透明大脸背景 + 红色准星 + 顶部提示条，点哪就识别哪个文件（Esc 取消）。"""

    picked = pyqtSignal(QPoint)
    cancelled = pyqtSignal()

    def __init__(self, hint: str):
        super().__init__()
        self._hint = hint
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 覆盖整个虚拟桌面（多屏），而非仅主屏
        self.setGeometry(QApplication.desktop().geometry())
        self.setCursor(self._make_crosshair_cursor())
        # 预加载半透明背景图；为空则回退到不可见底色
        self._bg = QPixmap(_BG_IMAGE_PATH)
        self._bg_ok = not self._bg.isNull()
        # 淡入淡出状态：当前背景不透明度 + 动画对象 + 防重入标记
        self._bg_opacity = 0.0
        self._fade_anim: Optional[QPropertyAnimation] = None
        self._fading_out = False

    @staticmethod
    def _make_crosshair_cursor():
        # 红色狙击准星（参考 MonsterDeleter：圆环 + 十字线）
        size = 40
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(230, 40, 40))
        pen.setWidth(2)
        painter.setPen(pen)
        center = size // 2
        radius = 12
        painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)
        painter.drawLine(center, 0, center, center - 4)
        painter.drawLine(center, center + 4, center, size)
        painter.drawLine(0, center, center - 4, center)
        painter.drawLine(center + 4, center, size, center)
        painter.end()
        return QCursor(pixmap, center, center)

    # ----- 背景图淡入淡出 -----
    def get_bg_opacity(self) -> float:
        return self._bg_opacity

    @pyqtProperty(float)
    def bgOpacity(self) -> float:
        return self._bg_opacity

    @bgOpacity.setter
    def bgOpacity(self, value: float) -> None:
        self._bg_opacity = float(value)
        self.update()

    def _fade_in(self) -> None:
        anim = QPropertyAnimation(self, b"bgOpacity", self)
        anim.setDuration(350)
        anim.setStartValue(0.0)
        anim.setEndValue(_OVERLAY_BG_OPACITY)
        anim.setEasingCurve(QEasingCurve.OutQuad)
        self._fade_anim = anim
        anim.start()

    def _fade_out(self, on_done: Callable[[], None]) -> None:
        if self._fading_out:
            return
        self._fading_out = True
        anim = QPropertyAnimation(self, b"bgOpacity", self)
        anim.setDuration(250)
        anim.setStartValue(self._bg_opacity)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InQuad)
        self._fade_anim = anim
        anim.finished.connect(on_done)
        anim.start()

    def set_hint(self, hint: str) -> None:
        self._hint = hint
        self.update()

    def paintEvent(self, event) -> None:
        # 基础底色：alpha=1 近乎透明，但能让窗口在全屏「实体化」，
        # 避免完全透明的区域在 Windows 上穿透（光标/点击落到下层窗口）。
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        # 半透明大脸背景图：contain 完整显示（KeepAspectRatio 等比缩到能整个放进主屏，
        # 不裁切、不变形），居中于主屏（虚拟桌面坐标 -> 本地坐标）。副屏仅保留不可见底色。
        if self._bg_ok and self._bg_opacity > 0:
            painter.setOpacity(self._bg_opacity)
            virt = self.geometry()
            pg = QApplication.primaryScreen().geometry()
            local_pg = QRect(pg.x() - virt.x(), pg.y() - virt.y(), pg.width(), pg.height())
            scaled = self._bg.scaled(
                local_pg.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = local_pg.x() + (local_pg.width() - scaled.width()) // 2
            y = local_pg.y() + (local_pg.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.setOpacity(1.0)
        # 顶部提示条（居中于主屏）
        bar_w, bar_h = 460, 46
        virt = self.geometry()
        pg = QApplication.primaryScreen().geometry()
        x = pg.x() - virt.x() + (pg.width() - bar_w) // 2
        y = pg.y() - virt.y() + 28
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 20, 20, 185))
        painter.drawRoundedRect(x, y, bar_w, bar_h, 12, 12)
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = painter.font()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(x, y, bar_w, bar_h, Qt.AlignCenter, self._hint)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 抢键盘焦点，保证 Esc 可达（遮罩为 Tool 窗，默认可能无焦点）
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)
        self.grabKeyboard()
        # 背景图淡入
        self._fade_in()

    def hideEvent(self, event) -> None:
        self.releaseKeyboard()
        super().hideEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self._fading_out:
                return
            pos = event.globalPos()
            # 先淡出、再隐藏、最后才发 picked——确保 UIA 识别时遮罩已不存在
            self._fade_out(lambda: (self.hide(), self.picked.emit(pos)))
        elif event.button() == Qt.RightButton:
            # 右键 = 取消（狙击 UI 惯例，Esc 之外的兜底）
            self.cancelled.emit()
            self._fade_out(lambda: self.close())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self._fade_out(lambda: self.close())


class _ConfirmDialog(QDialog):
    """摧毁确认小窗：红「摧毁」/ 灰「算了」。样式与对话输入框一致。"""

    def __init__(self, pet, file_label: str):
        super().__init__(pet)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(self)
        container.setObjectName("destroyContainer")
        container.setStyleSheet(_CONTAINER_STYLE + _CONTENT_STYLE)
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        text = QLabel(f"要摧毁《{file_label}》吗？")
        text.setObjectName("destroyText")
        layout.addWidget(text)
        sub = QLabel("会进回收站，反悔还能捞回来")
        sub.setObjectName("destroySub")
        layout.addWidget(sub)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_no = QPushButton("算了", self)
        btn_no.setObjectName("destroyNo")
        btn_no.setCursor(Qt.PointingHandCursor)
        btn_no.clicked.connect(self.reject)
        btn_row.addWidget(btn_no)
        btn_ok = QPushButton("摧毁", self)
        btn_ok.setObjectName("destroyOk")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)
        self.adjustSize()

    def show_near_pet(self, pet) -> None:
        screen = QApplication.desktop().screenGeometry()
        x = pet.x() + (pet.width() - self.width()) // 2
        y = pet.y() - self.height() - 15
        if y < 0:
            y = pet.y() + pet.height() + 10
        x = max(0, min(x, screen.width() - self.width()))
        y = max(0, min(y, screen.height() - self.height()))
        self.move(x, y)
        self.show()


class DestroyShow:
    """摧毁表演编排器：五阶段回调链。实例挂在 pet._destroy_show 上保活。"""

    def __init__(self, pet, paths: List[str], target_pos: QPoint):
        self.pet = pet
        self.paths = paths
        self.target_pos = target_pos
        self._anims: List[QPropertyAnimation] = []
        self._dlg: Optional[_ConfirmDialog] = None
        self._deleted_ok = False
        self._delete_error = ""
        self._frozen_speeds = {}  # 走位阶段被冻结的 moveSpeed：{state: 原值或 _UNSET}

    # ----- 阶段 0：启动 -----
    def start(self) -> None:
        pet = self.pet
        pet._destroy_running = True
        pet._close_interaction_panel()
        pet.state_timer.stop()
        pet._auto_actions.stop()
        self._phase_walk_to_target()

    # ----- 走位通用：冻结走路逐帧位移，由 QPropertyAnimation 平滑驱动到指定点 -----
    def _walk_to(self, end_x: int, end_y: int, on_done: Callable[[], None]) -> None:
        pet = self.pet
        go_right = end_x >= pet.x() + pet.width() // 2
        state = "walk_right" if go_right else "walk_left"
        if not pet.animations.get(state):
            on_done()
            return

        # 冻结走路动作自带的逐帧位移（否则与属性动画叠加会走过头）。
        # 只改本宠物的 _state_config，属 caller 侧临时调整；确认/收场阶段恢复。
        cfg = pet._state_config.setdefault(state, {})
        if state not in self._frozen_speeds:
            self._frozen_speeds[state] = cfg.get("moveSpeed", _UNSET)
        cfg["moveSpeed"] = 0

        pet.current_state = state
        pet.current_frame_index = 0
        pet._apply_state_frame_rate()
        pet.update_frame()

        screen = QApplication.desktop().screenGeometry()
        end_x = max(0, min(end_x, screen.width() - pet.width()))
        end_y = max(0, min(end_y, screen.height() - pet.height()))
        distance = abs(end_x - pet.x()) + abs(end_y - pet.y())
        duration = max(WALK_MIN_MS, min(WALK_MAX_MS, int(distance * 2.5)))

        anim = QPropertyAnimation(pet, b"pos", pet)
        anim.setDuration(duration)
        anim.setStartValue(pet.pos())
        anim.setEndValue(QPoint(end_x, end_y))
        anim.setEasingCurve(QEasingCurve.OutQuad)
        anim.finished.connect(on_done)
        self._anims.append(anim)
        anim.start()

    def _restore_walk_speed(self) -> None:
        if not self._frozen_speeds:
            return
        pet = self.pet
        for state, original in self._frozen_speeds.items():
            cfg = pet._state_config.get(state)
            if cfg is not None and cfg.get("moveSpeed") == 0:
                if original is _UNSET:
                    cfg.pop("moveSpeed", None)
                else:
                    cfg["moveSpeed"] = original
        self._frozen_speeds = {}

    # ----- 阶段 1：长途跑到文件上方 -----
    def _phase_walk_to_target(self) -> None:
        pet = self.pet
        # 停在文件正上方：水平居中对齐目标，垂直位于其上 25px（贴着文件顶部）
        end_x = self.target_pos.x() - pet.width() // 2
        end_y = self.target_pos.y() - pet.height() - 25
        self._walk_to(end_x, end_y, self._phase_confirm)

    # ----- 阶段 2：确认 -----
    def _phase_confirm(self) -> None:
        self._restore_walk_speed()
        pet = self.pet
        _play_once(pet, STATE_CONFIRM, lambda: None)  # listen 保持循环，等待用户选择
        name = os.path.basename(self.paths[0].rstrip("\\/")) or self.paths[0]
        label = name if len(self.paths) == 1 else f"{name} 等 {len(self.paths)} 个文件"
        if len(label) > 20:
            label = label[:17] + "..."
        pet.update_bubble(f"要摧毁《{label}》吗？", duration=60000)

        dlg = _ConfirmDialog(pet, label)
        self._dlg = dlg
        dlg.accepted.connect(self._on_confirm)
        dlg.rejected.connect(self._on_cancel)
        dlg.show_near_pet(pet)

    # ----- 阶段 3：摧毁（出拳循环 3 秒，命中瞬间浮字 + 删除）-----
    def _on_confirm(self) -> None:
        self._dlg = None
        pet = self.pet
        pet.hide_bubble()
        if pet.animations.get(STATE_ATTACK):
            pet.current_state = STATE_ATTACK
            pet.current_frame_index = 0
            pet._apply_state_frame_rate()
            pet.update_frame()
        QTimer.singleShot(DESTROY_STRIKE_MS, self._strike)
        QTimer.singleShot(DESTROY_DURATION_MS, self._phase_celebrate)

    def _strike(self) -> None:
        self.pet._show_floating_effects([{"text": "砰！", "color": "#d85a30"}])
        self._delete_files()

    def _delete_files(self) -> None:
        errors = []
        for path in self.paths:
            err = _trash_one(path)
            if err:
                errors.append(f"{os.path.basename(path)}: {err}")
        self._deleted_ok = not errors
        self._delete_error = "; ".join(errors)
        if errors:
            print("[Peko 摧毁失败]", self._delete_error)

    # ----- 阶段 4：庆祝（挥手循环 2.5 秒）-----
    def _phase_celebrate(self) -> None:
        pet = self.pet
        if self._deleted_ok:
            pet.update_bubble("已丢进回收站～", duration=2600)
        else:
            reason = self._delete_error or "未知原因"
            if "SAFE_DELETE" in reason or "sandbox" in reason.lower():
                reason = "当前运行环境拦截了删除（沙箱保护）；请从普通终端启动桌宠再试"
            elif len(reason) > 40:
                reason = reason[:37] + "..."
            pet.update_bubble(f"摧毁失败：{reason}", duration=3600)
        # wave 动作循环播放 CELEBRATE_DURATION_MS，随后进入回家阶段
        if pet.animations.get(STATE_CELEBRATE):
            pet.current_state = STATE_CELEBRATE
            pet.current_frame_index = 0
            pet._apply_state_frame_rate()
            pet.update_frame()
            QTimer.singleShot(CELEBRATE_DURATION_MS, self._phase_walk_home)
        else:
            self._phase_walk_home()

    # ----- 阶段 5：跑回桌面右下角（宠物老家）-----
    def _phase_walk_home(self) -> None:
        pet = self.pet
        screen = QApplication.desktop().screenGeometry()
        home_x = screen.width() - pet.width() - 20
        home_y = screen.height() - pet.height() - 50
        self._walk_to(home_x, home_y, self._finish)

    # ----- 取消 / 收场 -----
    def _on_cancel(self) -> None:
        self._dlg = None
        self.pet.update_bubble("好嘞，那先留着它。", duration=2200)
        self._phase_walk_home()

    def _finish(self) -> None:
        pet = self.pet
        self._restore_walk_speed()
        pet._destroy_running = False
        pet.current_state = "stand"
        pet.current_frame_index = 0
        pet._apply_state_frame_rate()
        pet.update_frame()
        pet._auto_actions.resume()
        pet._destroy_show = None


def start_destroy_show_at(pet, paths: List[str], target_pos: QPoint) -> bool:
    """指定屏幕坐标启动表演。返回是否成功启动；不满足条件时气泡提示并返回 False。"""
    if getattr(pet, "_destroy_running", False):
        return False
    if pet.control_mode or getattr(pet, "follow_mouse_mode", False):
        pet.update_bubble("切回自动模式后再摧毁吧。", duration=2400)
        return False
    if not pet.animations.get(STATE_ATTACK):
        pet.update_bubble("这个表演我还不会哦。", duration=2400)
        return False
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        pet.update_bubble("没接到文件耶。", duration=2200)
        return False
    show = DestroyShow(pet, paths, target_pos)
    pet._destroy_show = show
    show.start()
    return True


def begin_destroy_flow(pet, parent: Optional[QWidget] = None) -> None:
    """托盘入口：狙击点选文件（红色准星，不变暗）→ 识别文件 → 宠物跑过去摧毁。"""
    if getattr(pet, "_destroy_running", False):
        pet.update_bubble("上一场还没演完呢。", duration=2200)
        return
    overlay = _TargetOverlay("点击要摧毁的文件图标（Esc 取消）")
    pet._destroy_overlay = overlay  # 挂宠物上保活

    def on_picked(pos: QPoint) -> None:
        def resolve():
            from ..core.file_picker import resolve_file_at_point
            path = resolve_file_at_point(pos.x(), pos.y())
            if path:
                pet._destroy_overlay = None
                start_destroy_show_at(pet, [path], pos)
            else:
                pet.update_bubble("没认出这是哪个文件，再点一次试试。", duration=2600)
                overlay.set_hint("没认出这个文件，再点一次（Esc 取消）")
                overlay.show()

        # 等遮罩隐藏后再做 UIA 识别，否则 ControlFromPoint 命中遮罩自己
        QTimer.singleShot(150, resolve)

    def on_cancel() -> None:
        pet._destroy_overlay = None

    overlay.picked.connect(on_picked)
    overlay.cancelled.connect(on_cancel)
    overlay.show()
