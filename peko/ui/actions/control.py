"""
操控动作模块：方向键 + 空格控制宠物移动与待机，长按持续执行。
上下左右固定对应 walk_up / walk_down / walk_left / walk_right（与 BB 等宠物一致）。
长时间无操作则自动进入 sleep 循环，直到新指令到来并重新计时。
"""
from typing import TYPE_CHECKING, Any

from PyQt5.QtCore import Qt, QTimer

if TYPE_CHECKING:
    from ..pet import DesktopPet

# 无操作多少毫秒后进入 sleep（如 15 秒）
IDLE_TIMEOUT_MS = 15000

# 方向键 -> 动作（walk_up / walk_down / walk_left / walk_right）
CONTROL_KEY_TO_STATE = {
    Qt.Key_Up: "walk_up",
    Qt.Key_Down: "walk_down",
    Qt.Key_Left: "walk_left",
    Qt.Key_Right: "walk_right",
    Qt.Key_Space: "stand",
}


class ControlActions:
    """操控模式：键盘控制宠物动作。"""

    def __init__(self, pet: "DesktopPet"):
        self.pet = pet
        self._key_held = None  # 当前按下的操控键
        self._idle_timer = QTimer(pet)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)

    def _reset_idle_timer(self) -> None:
        """收到新指令时重置「无操作」倒计时。"""
        self._idle_timer.stop()
        self._idle_timer.start(IDLE_TIMEOUT_MS)

    def _on_idle_timeout(self) -> None:
        """超过设定时间未操作：若当前宠物有 sleep 动作则一直循环执行 sleep，直到新指令。"""
        if not self.pet.control_mode:
            return
        if "sleep" in self.pet.animations and self.pet.animations["sleep"]:
            self.apply_state("sleep")

    def enter(self) -> None:
        """进入操控模式：切到待机、获得焦点、抓取键盘，并启动无操作倒计时。"""
        self._key_held = None
        self.pet.current_state = "stand"
        self.pet.current_frame_index = 0
        self.pet._apply_state_frame_rate()
        self.pet.update_frame()
        self.pet.setFocus()
        if hasattr(self.pet, "grabKeyboard"):
            self.pet.grabKeyboard()
        self._reset_idle_timer()
        self.pet.show_bubble("点击宠物后，用方向键 ↑↓←→ 移动，空格 待机", duration=3000, typing_speed=30)

    def exit(self) -> None:
        """退出操控模式时停止无操作定时器并释放键盘。"""
        self._key_held = None
        self._idle_timer.stop()
        if hasattr(self.pet, "releaseKeyboard"):
            try:
                self.pet.releaseKeyboard()
            except Exception:
                pass

    def apply_state(self, state: str) -> None:
        """切换到指定动作并刷新（仅当该动作存在时）。"""
        if state not in self.pet.animations or not self.pet.animations[state]:
            return
        self.pet.current_state = state
        self.pet.current_frame_index = 0
        self.pet._apply_state_frame_rate()
        self.pet.update_frame()

    def handle_key_press(self, event: Any) -> bool:
        """处理按键按下，返回 True 表示已消费。忽略 isAutoRepeat，避免长按时反复重置帧。每次按键都会重置无操作倒计时。"""
        key = event.key()
        if key not in CONTROL_KEY_TO_STATE:
            return False
        state = CONTROL_KEY_TO_STATE[key]
        if state not in self.pet.animations or not self.pet.animations[state]:
            return True
        # 长按时系统会不断发 keyPress（重复事件），若响应会每次把 current_frame_index 置 0，动画就卡在一轮
        if getattr(event, "isAutoRepeat", lambda: False)():
            return True
        self._reset_idle_timer()
        self._key_held = key
        self.apply_state(state)
        return True

    def handle_key_release(self, event: Any) -> bool:
        """处理按键释放，返回 True 表示已消费。忽略重复事件的 release，只响应真正的松键。"""
        key = event.key()
        if getattr(event, "isAutoRepeat", lambda: False)():
            return True
        if key != self._key_held:
            return False
        self._key_held = None
        if "stand" in self.pet.animations and self.pet.animations["stand"]:
            self.apply_state("stand")
        return True
