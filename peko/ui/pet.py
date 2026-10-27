"""
桌宠组件：窗口、动画帧、气泡、拖拽；动作与聊天委托给独立模块。
- 动作：actions.auto（自动随机）、actions.control（键盘操控）
- 聊天：chat（输入框 + AI 气泡）
- 随机文案：配置 randomSayings 后偶尔用气泡弹出句子（复用气泡样式）
"""
import random
import sys
from typing import Any, Dict, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal, QDateTime, QRect, QPoint, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import (
    QLabel, QWidget, QApplication, QGraphicsOpacityEffect, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QPushButton,
)

from ..core.mood import MoodEngine
from .pet_parts.bubble_style import (
    _bubble_action_qss, _side_panel_style,
    _default_bubble_style, _bubble_style_from_config,
)
from .pet_parts.bubbles import BubbleMixin
from .pet_parts.comfort_flow import ComfortFlowMixin
from .pet_parts.interaction_panel import InteractionPanelMixin
from .pet_parts.sayings import SayingsMixin
from .pet_parts.state_params import StateParamsMixin
from .effects import EffectOverlay, EFFECTS
from .actions import (
    AutoActions,
    ControlActions,
    FollowMouseActions,
    STANDARD_MOVEMENT_STATES,
    RESERVED_STATES,
)

# 动作「控制窗口」：走向屏幕四角后对前台窗口最小化/最大化（仅 Windows）
WINDOW_CONTROL_STATE = "window_control"
WINDOW_CONTROL_REACH_THRESHOLD = 25










class DesktopPet(BubbleMixin, ComfortFlowMixin, SayingsMixin, StateParamsMixin, InteractionPanelMixin, QWidget):
    """
    桌宠窗口。动作与聊天委托给 actions 与 chat 模块。
    """
    bubble_text_ready = pyqtSignal(str, int)  # text, duration；供 chat 模块 emit 后主线程更新气泡
    bubble_stream_ready = pyqtSignal(str, int)  # text, duration；假流式（打字机）播报，供天气等模块跨线程使用
    comfort_turn_ready = pyqtSignal(object)  # 安慰对话轮次（dict），后台 AI 生成后主线程展示

    def __init__(self, pet_package: Dict[str, Any], frame_rate: int = 10):
        super().__init__()
        self.pet_package = pet_package
        raw_animations = pet_package["animations"]
        self.character = pet_package.get("character") or {}
        self.bubble_style_config = pet_package.get("bubbleStyle") or {}
        self.slots = pet_package.get("slots") or {}
        action_cfg = pet_package.get("actionConfig") or {}

        display = pet_package.get("displaySize")
        if isinstance(display, (list, tuple)) and len(display) >= 2:
            self._display_width, self._display_height = int(display[0]), int(display[1])
        elif isinstance(pet_package.get("frameWidth"), (int, float)) and isinstance(pet_package.get("frameHeight"), (int, float)):
            self._display_width = int(pet_package["frameWidth"])
            self._display_height = int(pet_package["frameHeight"])
        else:
            self._display_width = self._display_height = None
        self._display_scale = 1.0

        default_frame_rate = action_cfg.get("frameRate") or frame_rate
        default_switch_interval = action_cfg.get("stateSwitchInterval", 3000)
        default_move_speed = action_cfg.get("moveSpeed", 5)

        self.animations = {}
        self._state_config = {}
        for state_name, state_value in raw_animations.items():
            frames = state_value.get("frames") or []
            self.animations[state_name] = frames
            self._state_config[state_name] = {
                "frameRate": state_value.get("frameRate") if "frameRate" in state_value else default_frame_rate,
                "stateSwitchInterval": state_value.get("stateSwitchInterval") if "stateSwitchInterval" in state_value else default_switch_interval,
                "moveSpeed": state_value.get("moveSpeed") if "moveSpeed" in state_value else default_move_speed,
            }

        self.frame_rate = default_frame_rate
        self.state_switch_interval = default_switch_interval
        self.move_speed = default_move_speed
        self.current_state = "stand"
        self.previous_state = "stand"
        self.current_frame_index = 0
        self.allow_movement = True
        self.control_mode = False
        self.follow_mouse_mode = False
        self._mood_engine = MoodEngine(str(pet_package.get("id") or pet_package.get("name") or "pet"))
        self._interaction_panel = None
        self._destroy_running = False  # 摧毁表演进行中（托盘「摧毁文件」触发，destroy_show 编排）
        self._interaction_lock_until_ms = 0
        self._interaction_resume_timer = QTimer(self)
        self._interaction_resume_timer.setSingleShot(True)
        self._interaction_resume_timer.timeout.connect(self._resume_after_manual_interaction)
        self._ui_effect_animations = []

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        self._apply_state_frame_rate()
        self.timer.start()

        self.state_timer = QTimer(self)
        self._auto_actions = AutoActions(self, self.state_timer)
        self._control_actions = ControlActions(self)
        self._follow_mouse_actions = FollowMouseActions(self)
        self._chat = None  # 在 init 末尾创建，避免循环引用

        self._auto_actions.schedule_next()

        self.bubble_timer = QTimer(self)
        self.bubble_timer.timeout.connect(self.hide_bubble)
        self.bubble_text_ready.connect(self._on_bubble_text_ready)
        self.bubble_stream_ready.connect(self._on_bubble_stream_ready)
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self.type_next_character)
        self.comfort_turn_ready.connect(self._on_comfort_turn_ready)

        from .chat import ChatHandler
        self._chat = ChatHandler(self)

        # B3：订阅工作台「完成事件」，桌宠即时反馈（情绪 + 动画 + 靠谱值气泡）
        try:
            from .pet_link import get_notifier
            notifier = get_notifier()
            if notifier is not None:
                notifier.workspace_completed.connect(self._on_workspace_completed)
        except Exception:
            pass

        # 随机文案：从 randomSayings.phrases 随机取一句，用现有气泡弹出（复用气泡样式）
        sayings_cfg = pet_package.get("randomSayings") or {}
        self._sayings_phrases = sayings_cfg.get("phrases") or []
        self._sayings_enabled = sayings_cfg.get("enabled", True) if self._sayings_phrases else False
        self._sayings_interval_min = max(30000, int(sayings_cfg.get("intervalMinMs", 60000)))
        self._sayings_interval_max = max(
            self._sayings_interval_min,
            int(sayings_cfg.get("intervalMaxMs", 180000)),
        )
        self._sayings_duration = max(2000, int(sayings_cfg.get("durationMs", 5000)))
        self._sayings_timer = QTimer(self)
        self._sayings_timer.setSingleShot(True)
        self._sayings_timer.timeout.connect(self._on_sayings_tick)
        # 主动关心：距上次至少 CARE_MIN_INTERVAL_MS，且每次 sayings tick 以低概率触发
        self._last_care_ts = 0.0
        if self._sayings_enabled:
            self._schedule_next_saying(initial_delay=True)

        # 快速点击计数：用于“连续 3 次及以上点击触发 fight”
        self._click_count = 0
        self._last_click_time_ms = 0
        self._press_global_pos = None
        self._triple_click_window_ms = 500  # 在此时间内的点击算作连续

        # 分身模式动作覆盖：支持 cloneModeActions 里写入对象形式
        # 例如：
        # "cloneModeActions": [
        #   {"state":"walk_left","frameRate":12,"stateSwitchInterval":1500},
        #   "walk_right"
        # ]
        self._clone_mode_action_overrides: Dict[str, Dict[str, Any]] = {}
        clone_actions = pet_package.get("cloneModeActions")
        if isinstance(clone_actions, list):
            for item in clone_actions:
                if not isinstance(item, dict):
                    continue
                state_key = item.get("state") or item.get("action") or item.get("key") or item.get("name")
                if not isinstance(state_key, str) or not state_key:
                    continue
                ov: Dict[str, Any] = {}
                if "frameRate" in item:
                    ov["frameRate"] = item.get("frameRate")
                if "stateSwitchInterval" in item:
                    ov["stateSwitchInterval"] = item.get("stateSwitchInterval")
                if ov:
                    self._clone_mode_action_overrides[state_key] = ov

        # 分身模式动作属性随机抖动（每个宠物实例一组随机系数），让同一个动作在不同分身上表现不同
        # 支持配置：
        # "cloneModeActionJitter": { "frameRatePct": 0.2, "stateSwitchIntervalPct": 0.2, "moveSpeedPct": 0.2 }
        # 其中 *Pct* 支持 0~1（表示比例）或 0~100（表示百分比）
        jitter_cfg = pet_package.get("cloneModeActionJitter") or {}

        def _to_ratio(v: Any, default_ratio: float) -> float:
            try:
                val = float(v)
            except (TypeError, ValueError):
                return default_ratio
            if val > 1:
                val = val / 100.0
            return max(0.0, val)

        frame_rate_jitter_pct = _to_ratio(jitter_cfg.get("frameRatePct"), 0.2)
        interval_jitter_pct = _to_ratio(jitter_cfg.get("stateSwitchIntervalPct"), 0.2)
        move_speed_jitter_pct = _to_ratio(jitter_cfg.get("moveSpeedPct"), 0.2)

        self._clone_mode_action_jitter = {
            "frameRateMul": random.uniform(1.0 - frame_rate_jitter_pct, 1.0 + frame_rate_jitter_pct),
            "stateSwitchIntervalMul": random.uniform(1.0 - interval_jitter_pct, 1.0 + interval_jitter_pct),
            "moveSpeedMul": random.uniform(1.0 - move_speed_jitter_pct, 1.0 + move_speed_jitter_pct),
        }

    def init_ui(self):
        # macOS：Qt.Tool 多为 NSPanel，会在应用失焦时被系统隐藏，看起来像「切走程序桌宠就没了」。
        # 使用普通 Window + 无边框 + 置顶，切换焦点时仍留在桌面上。
        if sys.platform == "darwin":
            self.setWindowFlags(
                Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            )
        else:
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
            )
        self.setAttribute(Qt.WA_TranslucentBackground)

        first_frame_path = self.animations["stand"][0]
        first_frame = QPixmap(first_frame_path)
        if first_frame.isNull():
            print(f"[Peko] 无法加载首帧: {first_frame_path}")
            first_frame = QPixmap(1, 1)
        if self._display_width is not None and self._display_height is not None:
            self._base_display_width = self._display_width
            self._base_display_height = self._display_height
        else:
            self._base_display_width = first_frame.width()
            self._base_display_height = first_frame.height()
        w = max(1, int(self._base_display_width * self._display_scale))
        h = max(1, int(self._base_display_height * self._display_scale))
        self.setFixedSize(w, h)

        self.label = QLabel(self)
        self.label.setFixedSize(self.size())
        self.label.setScaledContents(False)

        # macOS 可见性守卫：切换桌面/Space 或系统隐藏后自动恢复显示
        # 防止切桌面后宠物"消失"的问题
        self._visibility_guard_timer = None
        if sys.platform == "darwin":
            self._visibility_guard_timer = QTimer(self)
            self._visibility_guard_timer.setInterval(2000)
            self._visibility_guard_timer.timeout.connect(self._ensure_visible)
            self._visibility_guard_timer.start()
            # 标记：上次显式隐藏的时间，避免守卫和显式隐藏冲突
            self._last_hide_manually_ms = 0

        screen_geometry = QApplication.desktop().screenGeometry()
        screen_width, screen_height = screen_geometry.width(), screen_geometry.height()
        pet_width, pet_height = self.width(), self.height()
        initial_x = screen_width - pet_width - 20
        initial_y = screen_height - pet_height - 50
        self.move(initial_x, initial_y)

        self.bubble_window = QWidget(self)
        if sys.platform == "darwin":
            self.bubble_window.setWindowFlags(
                Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
            )
        else:
            self.bubble_window.setWindowFlags(
                Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
            )
        self.bubble_window.setAttribute(Qt.WA_TranslucentBackground, True)
        # 气泡内布局：文本 + 安慰对话选项区 + 自由输入行
        self._bubble_v = QVBoxLayout(self.bubble_window)
        self._bubble_v.setContentsMargins(0, 0, 0, 0)
        self._bubble_v.setSpacing(6)

        self.bubble_label = QLabel(self.bubble_window)
        # 外观主题：读取持久化的主题（'pet' 用宠物自带样式，其余用预置主题）
        try:
            from ..core import appearance as appearance_mod
            theme = appearance_mod.get_theme()
            style_cfg = appearance_mod.get_bubble_style(theme)
        except Exception:
            style_cfg = None
        if not style_cfg:
            style_cfg = self.bubble_style_config
        self.bubble_label.setStyleSheet(_bubble_style_from_config(style_cfg))
        font = QFont("PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei", 15)
        font.setBold(True)
        self.bubble_label.setFont(font)
        self.bubble_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setContentsMargins(14, 14, 14, 14)
        self.bubble_label.setFixedWidth(220)
        self._bubble_v.addWidget(self.bubble_label)
        self.bubble_window.setStyleSheet(_bubble_action_qss())

        # 安慰对话侧面操作面板（选项按钮 + 自由输入，显示在宠物侧边）
        self._side_panel = QWidget(
            None, Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self._side_panel.setAttribute(Qt.WA_TranslucentBackground)
        self._side_panel.setStyleSheet(_side_panel_style())
        sp_outer = QVBoxLayout(self._side_panel)
        sp_outer.setContentsMargins(0, 0, 0, 0)
        sp_frame = QFrame(self._side_panel)
        sp_frame.setObjectName("sidePanel")
        sp_outer.addWidget(sp_frame)
        fv = QVBoxLayout(sp_frame)
        fv.setContentsMargins(14, 12, 14, 12)
        fv.setSpacing(8)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        hint = QLabel("怎么回它？", self._side_panel)
        hint.setObjectName("sideHint")
        header.addWidget(hint)
        header.addStretch(1)
        self._side_close_btn = QPushButton("×", self._side_panel)
        self._side_close_btn.setObjectName("sideClose")
        self._side_close_btn.setCursor(Qt.PointingHandCursor)
        self._side_close_btn.clicked.connect(self.close_comfort_dialog)
        header.addWidget(self._side_close_btn)
        fv.addLayout(header)
        self._side_opt_grid = QGridLayout()
        self._side_opt_grid.setHorizontalSpacing(8)
        self._side_opt_grid.setVerticalSpacing(6)
        fv.addLayout(self._side_opt_grid)
        self._side_inp_row = QHBoxLayout()
        self._side_inp_row.setSpacing(6)
        self._side_inp_edit = QLineEdit(self._side_panel)
        self._side_inp_edit.setPlaceholderText("自己说点什么…")
        self._side_inp_edit.returnPressed.connect(self._bubble_send)
        self._side_inp_send = QPushButton("发送", self._side_panel)
        self._side_inp_send.setCursor(Qt.PointingHandCursor)
        self._side_inp_send.clicked.connect(self._bubble_send)
        self._side_inp_row.addWidget(self._side_inp_edit, 1)
        self._side_inp_row.addWidget(self._side_inp_send)
        fv.addLayout(self._side_inp_row)
        self._side_panel.hide()
        self._side_follow_timer = QTimer(self)
        self._side_follow_timer.setInterval(250)
        self._side_follow_timer.timeout.connect(self._position_side_panel)

        self._comfort_session = None
        self._comfort_busy = False
        self._comfort_ai_mode = False
        self.bubble_window.setVisible(False)

        # 特效叠加层
        self.effect_overlay = EffectOverlay(self)
        self._current_effect = "none"

        # 主题切换总线：settings 广播 theme_changed 后气泡/侧栏自动刷新
        from ..core.bus import bus
        bus.subscribe("theme_changed", self.refresh_theme)

        self.update_frame()
        self.setFocusPolicy(Qt.StrongFocus)

    def set_effect(self, name: str) -> bool:
        """切换特效。name 为 EFFECTS 中的 key，返回是否成功。"""
        if name not in EFFECTS:
            return False
        self._current_effect = name
        self.effect_overlay.set_effect(name)
        # 重置暂停状态（切换特效时，若气泡显示着且新特效是 think，则暂停；否则恢复）
        bubble_visible = self.bubble_window.isVisible() if hasattr(self, "bubble_window") else False
        should_pause = (name == "think" and bubble_visible)
        self.effect_overlay.set_paused(should_pause)
        if name == "none":
            self.effect_overlay.hide()
        else:
            self.effect_overlay.follow_pet()
            self.effect_overlay.show()
            self.effect_overlay.raise_()
        return True

    def get_effect(self) -> str:
        return self._current_effect

    def set_control_mode(self, on: bool) -> None:
        """切换为操控模式或自动/跟随模式。"""
        self.control_mode = on
        if on:
            self._close_interaction_panel()
        if on:
            self.set_follow_mouse_mode(False)
        self.state_timer.stop()
        if on:
            self._control_actions.enter()
        else:
            self._control_actions.exit()
            if not self.follow_mouse_mode:
                self._auto_actions.resume()

    def set_follow_mouse_mode(self, on: bool) -> None:
        """切换为跟随鼠标模式；与操控模式互斥。"""
        self.follow_mouse_mode = on
        if on:
            self._close_interaction_panel()
        if on:
            self.control_mode = False
            self._control_actions.exit()
            self.state_timer.stop()
            self._follow_mouse_actions.enter()
        else:
            self._follow_mouse_actions.exit()
            self.state_timer.stop()
            if not self.control_mode:
                self._auto_actions.resume()




























    def comfort(self, text: str = "") -> None:
        """安慰打气：驱动情绪/动作/浮字（mood.comfort 互动），再显示安慰文案。

        text 为空时用内置语库生成；由 chat 层传入 AI 个性化结果（可选）。
        """
        try:
            self.apply_mood_interaction("comfort")
        except Exception:
            pass
        if not (text or "").strip():
            from ..core import comfort as comfort_lib
            text = comfort_lib.build_comfort_text()
        self.update_bubble(text, duration=4200)

    def _on_workspace_completed(self, kind: str, label: str, total: int) -> None:
        """B3：工作台完成事件 → 桌宠即时反馈（情绪 + 动画 + 靠谱值气泡）。

        复用 apply_mood_interaction("praise") 拿到情绪/浮字/动画/自动暂停，
        再把气泡换成「靠谱值」成就文案。由 pet_link notifier 发射，可能来自
        本地 HTTP 服务线程（浏览器版）或内嵌 WebChannel（主线程），Qt 队列连接
        保证槽函数在主线程执行。
        """
        try:
            self.apply_mood_interaction("praise")
        except Exception:
            pass
        kind_label = {"todo": "待办", "plan": "计划", "habit": "习惯", "focus": "专注"}.get(kind, "事项")
        if label:
            text = f"靠谱值 +1（当前 {total}）\n{kind_label}完成：{label}"
        else:
            text = f"靠谱值 +1（当前 {total}）\n{kind_label}完成，太靠谱了！"
        self.update_bubble(text, duration=3600)

    def next_frame(self):
        if self.follow_mouse_mode:
            self._follow_mouse_actions.update_direction_to_cursor()
        frames = self.animations.get(self.current_state)
        if not frames and self.current_state != "dragged":
            self.current_state = "stand"
            self.current_frame_index = 0
            frames = self.animations.get("stand")
        if not frames:
            return
        self.current_frame_index = (self.current_frame_index + 1) % len(frames)
        self.update_frame()
        if self.current_state in STANDARD_MOVEMENT_STATES and not self.follow_mouse_mode:
            self.update_position()
        elif self.current_state == WINDOW_CONTROL_STATE and not getattr(self, "clone_mode", False):
            self._update_window_control_position()

    def update_frame(self):
        frames = self.animations.get(self.current_state)
        if not frames and self.current_state == "dragged":
            frames = self.animations.get("stand")
        if not frames and self.current_state != "dragged":
            frames = self.animations.get("stand")
            if frames:
                self.current_state = "stand"
                self.current_frame_index = 0
        if not frames:
            return
        frame_path = frames[self.current_frame_index % len(frames)]
        pixmap = QPixmap(frame_path)
        if pixmap.isNull():
            print(f"[Peko] 无法加载帧: {frame_path}")
            stand_frames = self.animations.get("stand") or []
            if stand_frames:
                fallback_path = stand_frames[0]
                fallback_pixmap = QPixmap(fallback_path)
                if not fallback_pixmap.isNull():
                    self.label.setPixmap(fallback_pixmap.scaled(self.width(), self.height()))
            return
        scaled_pixmap = pixmap.scaled(self.width(), self.height())
        self.label.setPixmap(scaled_pixmap)

    def update_position(self):
        if getattr(self, "_exit_animating", False):
            return
        x, y = self.x(), self.y()
        # 分身模式：固定在任务栏上一行，只做水平位移
        clone_mode = getattr(self, "clone_mode", False)
        row_y = getattr(self, "clone_mode_row_y", None)
        if clone_mode and row_y is not None:
            y = row_y
            if self.current_state == "walk_left":
                cfg = self._state_config.get(self.current_state, {})
                speed = cfg.get("moveSpeed", self.move_speed)
                x -= speed
            elif self.current_state == "walk_right":
                cfg = self._state_config.get(self.current_state, {})
                speed = cfg.get("moveSpeed", self.move_speed)
                x += speed
            screen_geometry = QApplication.desktop().screenGeometry()
            x = max(0, min(x, screen_geometry.width() - self.width()))
            self.move(x, y)
            self._position_bubble_window()
            return
        if self.current_state not in STANDARD_MOVEMENT_STATES:
            return
        cfg = self._state_config.get(self.current_state, {})
        speed = cfg.get("moveSpeed") if "moveSpeed" in cfg else self.move_speed
        if self.current_state == "walk_left":
            x -= speed
        elif self.current_state == "walk_right":
            x += speed
        elif self.current_state == "walk_up":
            y -= speed
        elif self.current_state == "walk_down":
            y += speed
        screen_geometry = QApplication.desktop().screenGeometry()
        x = max(0, min(x, screen_geometry.width() - self.width()))
        y = max(0, min(y, screen_geometry.height() - self.height()))
        self.move(x, y)
        self._position_bubble_window()

    def _get_window_control_target(self) -> Optional[Tuple[int, int]]:
        """随机选一个屏幕四角坐标（宠物左上角目标），仅 Windows 有效。"""
        screen = QApplication.desktop().screenGeometry()
        sw = screen.width()
        sh = screen.height()
        pw = self.width()
        ph = self.height()
        corners = [
            (0, 0),
            (sw - pw, 0),
            (0, sh - ph),
            (sw - pw, sh - ph),
        ]
        return random.choice(corners)

    def _update_window_control_position(self) -> None:
        """window_control 动作：朝目标角移动，到达后对前台窗口最小化/最大化并切回 stand。"""
        target = getattr(self, "_window_control_target", None)
        if target is None:
            self._window_control_target = self._get_window_control_target()
            target = self._window_control_target
        tx, ty = target
        x, y = self.x(), self.y()
        cfg = self._state_config.get(WINDOW_CONTROL_STATE, {})
        speed = cfg.get("moveSpeed", self.move_speed)
        dx = tx - x
        dy = ty - y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= WINDOW_CONTROL_REACH_THRESHOLD:
            self._do_window_control_action()
            self._window_control_target = None
            self.current_state = "stand"
            self.current_frame_index = 0
            self._apply_state_frame_rate()
            self.update_frame()
            if not self.control_mode and not self.follow_mouse_mode and hasattr(self, "_auto_actions"):
                self._auto_actions.schedule_next()
            return
        if dist > 0:
            step = min(speed, dist)
            x = int(x + (dx / dist) * step)
            y = int(y + (dy / dist) * step)
        screen = QApplication.desktop().screenGeometry()
        x = max(0, min(x, screen.width() - self.width()))
        y = max(0, min(y, screen.height() - self.height()))
        self.move(x, y)
        self._position_bubble_window()

    def _do_window_control_action(self) -> None:
        """对当前前台窗口执行：最小化、最大化、或缩放（变大/变小）（仅 Windows）。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            SW_MINIMIZE = 6
            SW_MAXIMIZE = 3
            SW_RESTORE = 9
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return
            action = random.choice(["minimize", "maximize", "resize_larger", "resize_smaller"])
            if action == "minimize":
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            elif action == "maximize":
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.ShowWindow(hwnd, SW_MAXIMIZE)
            else:
                # 变大或变小：先还原再按当前尺寸缩放
                if user32.IsZoomed(hwnd):
                    user32.ShowWindow(hwnd, SW_RESTORE)
                class RECT(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                rect = RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                screen = QApplication.desktop().screenGeometry()
                max_w = screen.width()
                max_h = screen.height()
                min_w, min_h = 200, 150
                if action == "resize_larger":
                    new_w = min(int(w * 1.2), max_w)
                    new_h = min(int(h * 1.2), max_h)
                    if new_w <= w and new_h <= h:
                        new_w = min(w + 80, max_w)
                        new_h = min(h + 60, max_h)
                else:
                    new_w = max(int(w * 0.8), min_w)
                    new_h = max(int(h * 0.8), min_h)
                    if new_w >= w and new_h >= h:
                        new_w = max(w - 80, min_w)
                        new_h = max(h - 60, min_h)
                user32.MoveWindow(hwnd, rect.left, rect.top, new_w, new_h, 1)
        except Exception:
            pass






















    def _cleanup_for_destroy(self) -> None:
        """彻底清理：停止所有定时器并关闭气泡窗口，用于分身模式退出时，避免气泡残留和卡顿。"""
        self.timer.stop()
        self.state_timer.stop()
        self._interaction_resume_timer.stop()
        self._stop_bubble_timers()
        self._close_interaction_panel()
        self._clear_ui_effects()
        self.bubble_window.close()

    def play_exit_animation(self, duration_ms: int = 2000) -> None:
        """退场动画：使用 walk_up 向上移动并逐渐透明，渐行渐远。"""
        self._exit_animating = True
        self._stop_bubble_timers()
        self.state_timer.stop()
        if "walk_up" in self.animations and (self.animations.get("walk_up") or []):
            self.current_state = "walk_up"
        else:
            self.current_state = "stand"
        self.current_frame_index = 0
        self._apply_state_frame_rate()
        self.update_frame()

        start_rect = QRect(self.x(), self.y(), self.width(), self.height())
        end_y = -self.height() - 100
        end_rect = QRect(self.x(), end_y, self.width(), self.height())

        anim_geom = QPropertyAnimation(self, b"geometry")
        anim_geom.setDuration(duration_ms)
        anim_geom.setStartValue(start_rect)
        anim_geom.setEndValue(end_rect)
        anim_geom.setEasingCurve(QEasingCurve.OutCubic)

        anim_opacity = QPropertyAnimation(self, b"windowOpacity")
        anim_opacity.setDuration(duration_ms)
        anim_opacity.setStartValue(1.0)
        anim_opacity.setEndValue(0.0)
        anim_opacity.setEasingCurve(QEasingCurve.InQuad)

        self._exit_animation_group = QParallelAnimationGroup(self)
        self._exit_animation_group.addAnimation(anim_geom)
        self._exit_animation_group.addAnimation(anim_opacity)
        self._exit_animation_group.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_frame()
        self.update()

    def hide(self):
        """显式隐藏时记录时间，避免可见性守卫立即拉回来。"""
        import sys
        if sys.platform == "darwin" and hasattr(self, "_last_hide_manually_ms"):
            from PyQt5.QtCore import QDateTime
            self._last_hide_manually_ms = QDateTime.currentMSecsSinceEpoch()
        super().hide()

    def _ensure_visible(self) -> None:
        """macOS 可见性守卫：如果应该显示却被系统隐藏了，重新显示。"""
        if not hasattr(self, "_last_hide_manually_ms"):
            return
        # 如果最近 3 秒内显式隐藏过，不守卫
        from PyQt5.QtCore import QDateTime
        if QDateTime.currentMSecsSinceEpoch() - self._last_hide_manually_ms < 3000:
            return
        # 分身模式永远保持显示；主宠只要没被手动隐藏就保持显示
        if not self.isVisible():
            clone = getattr(self, "clone_mode", False)
            if clone:
                self.show()
            elif not getattr(self, "_user_hidden", False):
                self.show()

    def closeEvent(self, event):
        # 退出主题总线订阅，防总线持有已关闭窗口引用
        try:
            from ..core.bus import bus
            bus.unsubscribe("theme_changed", self.refresh_theme)
        except Exception:
            pass
        self._stop_bubble_timers()
        self._close_interaction_panel()
        self._clear_ui_effects()
        self._mood_engine.save()
        # 关闭特效叠加层
        if hasattr(self, "effect_overlay"):
            try:
                self.effect_overlay.close()
            except Exception:
                pass
        super().closeEvent(event)






    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.show_mood_panel(event.globalPos())
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self._close_interaction_panel()
            self._press_global_pos = event.globalPos()
            self.previous_state = self.current_state
            self.current_state = "dragged"
            self.current_frame_index = 0
            self.state_timer.stop()
            self._apply_state_frame_rate()
            self.mouse_drag_position = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.mouse_drag_position)
            self._position_bubble_window()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 快速三击检测（仅自动模式且该宠物有 fight 动作时）：位移小于阈值视为一次“点击”
            triggered_fight = False
            if (
                self._press_global_pos is not None
                and "fight" in self.animations
                and not self.control_mode
                and not getattr(self, "follow_mouse_mode", False)
                and self.current_state != "fight"
            ):
                release_pos = event.globalPos()
                dx = release_pos.x() - self._press_global_pos.x()
                dy = release_pos.y() - self._press_global_pos.y()
                if dx * dx + dy * dy <= 225:  # 约 15px 内视为点击
                    now = QDateTime.currentMSecsSinceEpoch()
                    if now - self._last_click_time_ms > self._triple_click_window_ms:
                        self._click_count = 0
                    self._click_count += 1
                    self._last_click_time_ms = now
                    if self._click_count >= 3:
                        self._click_count = 0
                        self.current_state = "fight"
                        self.current_frame_index = 0
                        self._apply_state_frame_rate()
                        self.update_frame()
                        cfg = self._state_config.get("fight", {})
                        interval = cfg.get("stateSwitchInterval") or self.state_switch_interval
                        interval = max(500, int(interval) if isinstance(interval, (int, float)) else self.state_switch_interval)
                        self.state_timer.setInterval(interval)
                        self.state_timer.start()
                        triggered_fight = True
            self._press_global_pos = None

            if not triggered_fight:
                # 分身模式下松手后把 y 贴回任务栏一行，保持在同一排
                if getattr(self, "clone_mode", False):
                    row_y = getattr(self, "clone_mode_row_y", None)
                    if row_y is not None:
                        screen = QApplication.desktop().screenGeometry()
                        x = max(0, min(self.x(), screen.width() - self.width()))
                        self.move(x, row_y)
                        self._position_bubble_window()
                self.current_state = self.previous_state
                self.current_frame_index = 0
                self._apply_state_frame_rate()
                QTimer.singleShot(10, self._resume_after_drag)
            event.accept()

    def _resume_after_drag(self) -> None:
        if self.current_state == "dragged":
            self.current_state = "stand"
        if not self.control_mode and not self.follow_mouse_mode and not self.is_interaction_locked():
            self._auto_actions.resume()

    def enter_listen(self) -> None:
        """进入 listen 动作（对话前待机）。仅自动模式且配置了 listen 时生效；会暂停 state_timer，直到 exit_listen。"""
        if self.control_mode or getattr(self, "follow_mouse_mode", False) or "listen" not in self.animations:
            return
        self.state_timer.stop()
        self._state_before_listen = self.current_state
        self.current_state = "listen"
        self.current_frame_index = 0
        self._apply_state_frame_rate()
        self.update_frame()

    def exit_listen(self) -> None:
        """结束 listen 动作（用户发送消息或关闭对话框后调用），恢复此前状态并继续自动切换。"""
        if self.current_state != "listen":
            return
        self.current_state = getattr(self, "_state_before_listen", "stand")
        self.current_frame_index = 0
        self._apply_state_frame_rate()
        self.update_frame()
        if not self.control_mode and not getattr(self, "follow_mouse_mode", False):
            self._auto_actions.resume()

    def keyPressEvent(self, event):
        if self.control_mode and self._control_actions.handle_key_press(event):
            event.accept()
            return
        # ESC：退出控制模式（若在控制模式）、关闭安慰对话（若开着）、否则隐藏宠物
        if event.key() == Qt.Key_Escape:
            if self.control_mode:
                self.set_control_mode(False)
                event.accept()
                return
            # 如果安慰对话开着，先关安慰
            if getattr(self, "_comfort_session", None) is not None:
                self.close_comfort_dialog()
                event.accept()
                return
            # 普通状态：ESC 隐藏宠物
            if self.isVisible():
                self.hide()
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.control_mode and self._control_actions.handle_key_release(event):
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def set_allow_movement(self, allow: bool) -> None:
        self.allow_movement = allow
        if not allow:
            self.current_state = "stand"
            self.current_frame_index = 0
            self._apply_state_frame_rate()
        elif not self.control_mode and not getattr(self, "follow_mouse_mode", False) and self.current_state != "listen":
            self._auto_actions.resume()
