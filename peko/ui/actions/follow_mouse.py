"""
跟随鼠标模式：宠物自动朝鼠标方向移动，复用 walk_up/down/left/right 动画表现朝向。
位移为每帧沿直线向光标逼近（xy 同时移动），不再只走单轴。
支持扩展：当与鼠标距离小于阈值时视为「抓到鼠标」，可触发指定动作（如 wave）。
"""
import math
from typing import TYPE_CHECKING, Any, Dict

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication

if TYPE_CHECKING:
    from ..pet import DesktopPet

# 与鼠标距离小于此像素视为「抓到」
CATCH_RADIUS_DEFAULT = 28
# 抓到后播放的动作（若宠物有该动作），未配置时用 wave
ON_CATCH_ACTION_DEFAULT = "wave"
# 抓到后保持该动作的时长（毫秒），结束后继续跟随
ON_CATCH_DURATION_MS_DEFAULT = 2000


def _get_follow_mouse_config(pet: "DesktopPet") -> Dict[str, Any]:
    """从宠物配置读取 interactionModes.follow_mouse，供扩展。"""
    modes = (pet.pet_package or {}).get("interactionModes") or {}
    return modes.get("follow_mouse") or {}


class FollowMouseActions:
    """跟随鼠标模式：根据光标位置设置行走方向，靠近时触发「抓到」动作。"""

    def __init__(self, pet: "DesktopPet"):
        self.pet = pet
        self._catching = False
        self._catch_timer = QTimer(pet)
        self._catch_timer.setSingleShot(True)
        self._catch_timer.timeout.connect(self._on_catch_end)

    def _config(self) -> Dict[str, Any]:
        cfg = _get_follow_mouse_config(self.pet)
        move_speed = cfg.get("moveSpeed")
        frame_rate = cfg.get("frameRate")
        return {
            "catchRadius": int(cfg.get("catchRadius", CATCH_RADIUS_DEFAULT)),
            "onCatchAction": cfg.get("onCatchAction") or ON_CATCH_ACTION_DEFAULT,
            "onCatchDurationMs": int(cfg.get("onCatchDurationMs", ON_CATCH_DURATION_MS_DEFAULT)),
            "moveSpeed": int(move_speed) if move_speed is not None else None,
            "frameRate": int(frame_rate) if frame_rate is not None else None,
        }

    def enter(self) -> None:
        """进入跟随鼠标模式。"""
        self._catching = False
        self._catch_timer.stop()
        cfg = self._config()
        self.pet._follow_mouse_frame_rate = cfg.get("frameRate")
        self.pet._follow_mouse_move_speed = cfg.get("moveSpeed")
        self.pet.current_state = "stand"
        self.pet.current_frame_index = 0
        self.pet._apply_state_frame_rate()
        self.pet.update_frame()
        self.pet.show_bubble("跟随鼠标模式：BB鼠会朝光标移动，靠近可触发互动", duration=3000, typing_speed=30)

    def exit(self) -> None:
        """退出跟随鼠标模式。"""
        self._catching = False
        self._catch_timer.stop()
        self.pet._follow_mouse_frame_rate = None
        self.pet._follow_mouse_move_speed = None

    def _on_catch_end(self) -> None:
        """抓到动作播放结束，恢复跟随。"""
        self._catching = False

    def update_direction_to_cursor(self) -> None:
        """
        根据当前光标位置设置行走朝向（动画）并沿直线朝光标移动（xy 同时位移）。
        由 pet.next_frame() 在 follow_mouse_mode 下每帧调用。
        """
        if self._catching:
            return
        cursor_pos = QCursor.pos()
        pet_center = self.pet.mapToGlobal(self.pet.rect().center())
        dx = cursor_pos.x() - pet_center.x()
        dy = cursor_pos.y() - pet_center.y()
        cfg = self._config()
        radius = cfg["catchRadius"]
        dist_sq = dx * dx + dy * dy
        if dist_sq < radius * radius:
            # 抓到鼠标：播放配置的互动动作
            action = cfg["onCatchAction"]
            if action in self.pet.animations and self.pet.animations[action]:
                self._catching = True
                self.pet.current_state = action
                self.pet.current_frame_index = 0
                self.pet._apply_state_frame_rate()
                self.pet.update_frame()
                self._catch_timer.setInterval(cfg["onCatchDurationMs"])
                self._catch_timer.start()
            return
        # 根据方向选择行走动画（仅表现朝向）
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        if abs_dx <= 2 and abs_dy <= 2:
            state = "stand"
        elif abs_dx >= abs_dy:
            state = "walk_right" if dx > 0 else "walk_left"
        else:
            state = "walk_down" if dy > 0 else "walk_up"
        if state not in self.pet.animations or not self.pet.animations[state]:
            state = "stand"
        self.pet.current_state = state
        self.pet._apply_state_frame_rate()

        # 沿直线朝光标移动：每帧 xy 同时逼近，步长不超过 move_speed
        if state == "stand":
            return
        distance = math.sqrt(dx * dx + dy * dy)
        if distance <= 0:
            return
        speed = cfg.get("moveSpeed")
        if speed is None:
            state_cfg = self.pet._state_config.get(state, {})
            speed = state_cfg.get("moveSpeed", self.pet.move_speed)
        else:
            speed = int(speed)
        step_len = min(speed, distance)
        step_x = (dx / distance) * step_len
        step_y = (dy / distance) * step_len
        new_x = self.pet.x() + int(round(step_x))
        new_y = self.pet.y() + int(round(step_y))
        screen = QApplication.desktop().screenGeometry()
        new_x = max(0, min(new_x, screen.width() - self.pet.width()))
        new_y = max(0, min(new_y, screen.height() - self.pet.height()))
        self.pet.move(new_x, new_y)
        self.pet._position_bubble_window()
