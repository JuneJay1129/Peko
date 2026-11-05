"""BB 鼠的表情与姿态状态机：呼吸、歪头、眨眼、打瞌睡、惊醒、打字气泡。

为什么是「整只鼠做姿态」而不是「单独转脑袋」：body.svg 里 `head` 组是空的，
27 条 path 全在 `body` 组里，主轮廓从耳朵一路连通到脚。把头切下来单独转，
脖子处必然留断口。这里的折中是绕颈部一点整体旋转 —— 下半身被键盘和桌沿
盖住，看起来就是歪头、点头、起身。

眼睛是**重绘**的，不是叠一张贴纸：先把原来的眼珠用脸灰抹掉，再按状态画。
所以眨眼、半睁、闭眼都没有接缝。

状态流转（都按「最后一次按键」的时刻算，不用累计计时器，不会漂）：

    有按键  ──1.5s──▶  idle（呼吸 + 歪头 + 眨眼循环）
    idle ──16s──▶ sleepy（闭眼 + z 气泡）
    sleepy ──按键──▶ wake（瞪眼 + 缩一下 + ! 气泡）──0.9s──▶ typing

离屏预览脚本 scripts/preview_pet_anim.py 直接复用这里的状态机，
两边不会各写一套然后慢慢漂开。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

# 眼睛状态
EYE_OPEN = "open"
EYE_BLINK = "blink"
EYE_HALF = "half"
EYE_CLOSED = "closed"
EYE_WIDE = "wide"

# 气泡内容（空串 = 不显示）
BUBBLE_NONE = ""
BUBBLE_SLEEP = "z"
BUBBLE_BANG = "!"


@dataclass(frozen=True)
class Pose:
    """一帧的姿态。frozen 是为了能直接比相等来决定要不要重绘。"""

    rot: float = 0.0       # 绕颈部旋转，正数 = 画面顺时针
    dy: float = 0.0        # 整只上下位移
    scale: float = 1.0     # 整只缩放，支点压在身体底部
    eye: str = EYE_OPEN
    bubble: str = BUBBLE_NONE
    bub: float = 0.0       # 气泡弹出比例，0 不画、1 正常大小


NEUTRAL = Pose()


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


# 待机循环的关键帧：(秒, Pose)。eye / bubble 在关键帧处直接切换，
# 数值字段（rot / dy / scale / bub）在相邻两帧之间缓动。
IDLE_KEYS: List[Tuple[float, Pose]] = [
    (0.00, Pose()),
    (0.80, Pose(dy=-1.8, scale=1.012)),                       # 吸气
    (1.40, Pose()),                                           # 呼气
    (1.95, Pose(rot=-6.0)),                                   # 歪头看左
    (2.70, Pose(rot=-6.0)),                                   # 停住
    (2.85, Pose(rot=-5.0, eye=EYE_BLINK)),                    # 眨一下
    (3.05, Pose(rot=-4.0)),
    (3.65, Pose()),                                           # 回正
    (4.25, Pose(rot=5.0, eye=EYE_HALF)),                      # 歪头看右，眯眼
    (5.20, Pose(rot=5.0, eye=EYE_HALF)),
    (5.75, Pose()),                                           # 回正，收尾
]
IDLE_CYCLE = 6.30


# 惊醒关键帧，全长 1.55s，四拍结构：
#   起跳 0~0.10  窜高 7px + 后仰，越快越像吓一跳
#   卡顿 0.10~0.55  悬在半空一动不动 —— 这是「愣住」的那拍，瞪眼和「!」
#                   气泡就停在这里，正好躲过爪子还在继续的打字动画
#   发抖 0.55~1.05  左右快速摇摆（rot ±2.5°、dy 颤动），受惊的样子；
#                   气泡在这段已经消失，只剩抖
#   落回 1.05~1.55  慢慢落地，眼睛一直是 WIDE，最后一帧才切回 open
# sample_keys 取区间起点的 eye / bubble，所以「保持瞪眼」不用每帧重复写。
WAKE_KEYS: List[Tuple[float, Pose]] = [
    (0.00, Pose(dy=-1.5, scale=1.02, eye=EYE_WIDE,
                bubble=BUBBLE_BANG, bub=1.0)),
    (0.10, Pose(dy=-7.0, scale=1.06, rot=-3.0, eye=EYE_WIDE,
                bubble=BUBBLE_BANG, bub=1.0)),
    (0.55, Pose(dy=-7.0, scale=1.06, rot=-3.0, eye=EYE_WIDE,
                bubble=BUBBLE_BANG, bub=1.0)),
    (0.62, Pose(dy=-6.2, scale=1.05, rot=2.5, eye=EYE_WIDE)),
    (0.70, Pose(dy=-7.0, scale=1.06, rot=-2.5, eye=EYE_WIDE)),
    (0.78, Pose(dy=-6.2, scale=1.05, rot=2.5, eye=EYE_WIDE)),
    (0.86, Pose(dy=-7.0, scale=1.06, rot=-2.5, eye=EYE_WIDE)),
    (0.94, Pose(dy=-6.4, scale=1.05, rot=2.0, eye=EYE_WIDE)),
    (1.02, Pose(dy=-7.0, scale=1.06, rot=-1.5, eye=EYE_WIDE)),
    (1.15, Pose(dy=-3.0, scale=1.02, rot=-0.5, eye=EYE_WIDE)),
    (1.35, Pose(dy=0.0, scale=1.0, rot=0.0, eye=EYE_WIDE)),
    (1.55, Pose()),
]


def sample_keys(keys: List[Tuple[float, Pose]], t: float) -> Pose:
    """在关键帧序列里取值。t 超出范围按端点处理。"""
    if not keys:
        return NEUTRAL
    if t <= keys[0][0]:
        return keys[0][1]
    for i in range(len(keys) - 1):
        t0, p0 = keys[i]
        t1, p1 = keys[i + 1]
        if t0 <= t <= t1:
            k = _ease((t - t0) / max(1e-6, t1 - t0))
            return Pose(
                rot=_lerp(p0.rot, p1.rot, k),
                dy=_lerp(p0.dy, p1.dy, k),
                scale=_lerp(p0.scale, p1.scale, k),
                eye=p0.eye,
                bubble=p0.bubble,
                bub=_lerp(p0.bub, p1.bub, k),
            )
    return keys[-1][1]


class PetAnim(QObject):
    """按时间推进表情姿态，宿主每帧取 pose() 去画。

    宿主只需要做两件事：按键时调 note_key()，显示/隐藏时调 start() / stop()。
    """

    changed = pyqtSignal()

    FRAME_MS = 40            # 25fps：比打字触发（60fps）慢，肉眼看不出
    TYPING_HOLD = 1.5        # 最后一次按键后多久还算「正在打字」
    SLEEP_AFTER = 16.0       # 停手多久开始打瞌睡
    WAKE_SEC = 1.55          # 惊醒动作长度（起跳 + 卡顿 + 发抖 + 落回）
    BLINK_GAP = (2.6, 5.0)   # 打字时两次眨眼的间隔区间

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._mode = "typing"
        self._last_key = time.monotonic()
        self._mode_t0 = self._last_key
        self._idle_t0 = self._last_key
        self._pose: Pose = NEUTRAL
        self._next_blink = self._last_key + self.BLINK_GAP[1]
        self._blink_until = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ---- 宿主接口 ----
    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self._tick()

    def stop(self) -> None:
        self._timer.stop()

    def pose(self) -> Pose:
        return self._pose

    def note_key(self) -> None:
        """有一次按键：重置待机计时；睡着的时候进入惊醒动作。

        惊醒是**强制播放**的：wake 状态下继续敲键盘只重置待机计时，
        不切回 typing，整段 1.55s 的动作播完才交还表情控制权——
        不然连续打字第一下就把惊醒覆盖掉，等于没演。
        """
        now = time.monotonic()
        self._last_key = now
        if self._mode == "sleepy":
            self._mode = "wake"
            self._mode_t0 = now
        elif self._mode == "idle":
            self._mode = "typing"
            self._mode_t0 = now
        self._tick()

    # ---- 推进 ----
    def _tick(self) -> None:
        pose = self._sample(time.monotonic())
        if pose != self._pose:
            self._pose = pose
            self.changed.emit()

    def _sample(self, now: float) -> Pose:
        idle_for = now - self._last_key

        if self._mode == "typing":
            if idle_for >= self.SLEEP_AFTER:
                return self._enter("sleepy", now)
            if idle_for >= self.TYPING_HOLD:
                return self._enter("idle", now)
            return self._typing_pose(now)

        if self._mode == "wake":
            if now - self._mode_t0 >= self.WAKE_SEC:
                return self._enter("typing", now)
            return self._wake_pose(now)

        if self._mode == "idle":
            if idle_for >= self.SLEEP_AFTER:
                return self._enter("sleepy", now)
            t = (now - self._idle_t0) % IDLE_CYCLE
            return sample_keys(IDLE_KEYS, t)

        # sleepy
        if idle_for < self.SLEEP_AFTER:
            return self._enter("idle", now)
        return self._sleepy_pose(now)

    def _enter(self, mode: str, now: float) -> Pose:
        """切状态并立刻给出该状态的第一帧。

        这里**不能**回头调 _sample：typing 一进来就会因为「停手够久」再切
        idle，idle 又切回来，无限递归。各状态的 pose 直接算。
        """
        self._mode = mode
        self._mode_t0 = now
        if mode == "idle":
            self._idle_t0 = now
            return sample_keys(IDLE_KEYS, 0.0)
        if mode == "typing":
            return self._typing_pose(now)
        if mode == "wake":
            return self._wake_pose(now)
        return self._sleepy_pose(now)

    def _blink_now(self, now: float) -> bool:
        """打字状态的随机眨眼。到点开一段，结束再抽下一次。"""
        if now >= self._next_blink:
            self._blink_until = now + 0.13
            gap = self.BLINK_GAP
            self._next_blink = now + gap[0] + (gap[1] - gap[0]) * 0.5
        return now < self._blink_until

    def _typing_pose(self, now: float) -> Pose:
        # 打字不打气泡：每敲一下弹一个 ♪，节奏快了像催命，用户嫌吵。
        # 表情就剩随机眨眼，安静得多。
        eye = EYE_BLINK if self._blink_now(now) else EYE_OPEN
        return Pose(eye=eye)

    def _sleepy_pose(self, now: float) -> Pose:
        """入睡有个渐入：眼皮分两拍慢慢耷拉下来，不是睁眼瞬间变闭眼。

        idle 循环 6.3s 一圈，切到 sleepy 时往往循环走了一半，姿势各不相同；
        这里不接姿势（接了反而要做全身缓动），只管眼皮——0.35s 半睁、
        再 0.35s 压成眯眼，然后闭眼 + z 气泡起伏。z 气泡等睡着才冒出来。
        """
        t = now - self._mode_t0
        if t < 0.35:
            return Pose(eye=EYE_HALF, scale=1.012)
        if t < 0.7:
            return Pose(eye=EYE_BLINK)
        # z 气泡跟着呼吸涨落，静态的话像贴纸
        k = 0.5 + 0.5 * math.sin(now * 2.2)
        return Pose(eye=EYE_CLOSED, bubble=BUBBLE_SLEEP, bub=0.92 + 0.12 * k)

    def _wake_pose(self, now: float) -> Pose:
        """惊醒四拍：窜起 → 卡顿悬停 → 左右发抖 → 落回（见 WAKE_KEYS）。

        整段强制播完才回 typing；落回阶段 eye 还停在 WIDE（sample_keys
        取区间起点的 eye），到终点帧才切回 open —— 愣了一下才反应过来。
        """
        return sample_keys(WAKE_KEYS, now - self._mode_t0)
