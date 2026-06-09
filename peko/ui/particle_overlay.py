"""
心情粒子效果叠加层：在宠物图片周围一圈飘出粒子，直观反映内在状态。
- 低心情 (<30)   → 灰蓝色小圆点缓慢上升，像叹息的烟圈
- 低饱食度 (<20) → 🍙🍞 等食物 emoji 从头顶冒出
- 低精力 (<20)   → z Z 字母从头部飘出，像打瞌睡
- 高心情 (>80)   → ❤️⭐ 爱心星星向上漂浮
"""
import math
import random
import sys
from dataclasses import dataclass, field
from typing import List

from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtWidgets import QWidget


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float          # 剩余生命 0.0 ~ 1.0（每帧衰减）
    decay: float         # 每帧衰减量
    size: float
    r: int = 120         # 颜色 RGBA
    g: int = 120
    b: int = 160
    a: int = 200
    shape: str = "circle"  # "circle" | "text"
    text: str = ""         # shape == "text" 时使用


# ── 状态粒子配置 ─────────────────────────────────────────────

_LOW_MOOD_THRESHOLD = 30
_LOW_SATIETY_THRESHOLD = 20
_LOW_ENERGY_THRESHOLD = 20
_HIGH_MOOD_THRESHOLD = 80


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _spawn_low_mood_particles(width: int, height: int, intensity: float) -> List[Particle]:
    """低心情：灰蓝色小圆点，从底部两侧缓慢上升，像叹息的烟圈。"""
    count = max(1, int(2 * intensity))
    particles = []
    for _ in range(count):
        side = random.choice([-1, 1])
        x = width / 2 + side * random.uniform(width * 0.2, width * 0.48)
        y = height * random.uniform(0.7, 0.95)
        particles.append(Particle(
            x=x, y=y,
            vx=random.uniform(-0.3, 0.3),
            vy=-random.uniform(0.4, 1.0),
            life=1.0,
            decay=random.uniform(0.008, 0.018),
            size=random.uniform(3, 6),
            r=100, g=120, b=170, a=int(160 * intensity),
            shape="circle",
        ))
    return particles


def _spawn_low_satiety_particles(width: int, height: int, intensity: float) -> List[Particle]:
    """低饱食度：食物 emoji 从头顶冒出。"""
    foods = ["🍙", "🍞", "🍜", "🍙", "🍞"]
    count = max(1, int(1.5 * intensity))
    particles = []
    for _ in range(count):
        x = width / 2 + random.uniform(-width * 0.2, width * 0.2)
        y = height * 0.05
        particles.append(Particle(
            x=x, y=y,
            vx=random.uniform(-0.4, 0.4),
            vy=-random.uniform(0.5, 1.2),
            life=1.0,
            decay=random.uniform(0.007, 0.015),
            size=random.uniform(14, 20),
            r=200, g=170, b=60, a=220,
            shape="text",
            text=random.choice(foods),
        ))
    return particles


def _spawn_low_energy_particles(width: int, height: int, intensity: float) -> List[Particle]:
    """低精力：z Z 字母从头部飘出。"""
    z_texts = ["z", "Z", "z", "Z", "zZ"]
    count = max(1, int(1.5 * intensity))
    particles = []
    for _ in range(count):
        x = width * random.uniform(0.55, 0.85)
        y = height * random.uniform(0.05, 0.25)
        particles.append(Particle(
            x=x, y=y,
            vx=random.uniform(0.2, 0.8),
            vy=-random.uniform(0.4, 1.0),
            life=1.0,
            decay=random.uniform(0.008, 0.016),
            size=random.uniform(13, 20),
            r=100, g=80, b=180, a=int(200 * intensity),
            shape="text",
            text=random.choice(z_texts),
        ))
    return particles


def _spawn_high_mood_particles(width: int, height: int, intensity: float) -> List[Particle]:
    """高心情：爱心星星向上漂浮（稀疏）。"""
    hearts = ["❤️", "⭐", "💖", "✨", "💕"]
    count = 1  # 每次只生成 1 个，避免密集
    particles = []
    for _ in range(count):
        x = width / 2 + random.uniform(-width * 0.4, width * 0.4)
        y = height * random.uniform(0.3, 0.8)
        particles.append(Particle(
            x=x, y=y,
            vx=random.uniform(-0.3, 0.3),
            vy=-random.uniform(0.5, 1.3),
            life=1.0,
            decay=random.uniform(0.008, 0.016),
            size=random.uniform(13, 19),
            r=255, g=140, b=180, a=220,
            shape="text",
            text=random.choice(hearts),
        ))
    return particles


# ── 粒子叠加层 ───────────────────────────────────────────────

class ParticleOverlay(QWidget):
    """
    透明叠加层，覆盖在宠物图片上，绘制飘浮粒子。
    粒子在宠物图片矩形周围一圈生成和运动。
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._particles: List[Particle] = []
        self._spawn_accum = 0.0      # 通用粒子生成节奏（每 3 帧 ~150ms）
        self._high_mood_accum = 0.0  # 高心情粒子单独节流（每 6 帧 ~300ms）
        self._enabled = True

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(50)  # ~20 FPS

    # ── 外部接口 ──

    def update_mood_state(self, mood_score: float, satiety: float, energy: float) -> None:
        """每帧调用：根据心情三维值决定生成哪些粒子。"""
        if not self._enabled:
            return
        self._spawn_accum += 1.0
        if self._spawn_accum < 3:  # 每 3 帧（~150ms）生成一批
            return
        self._spawn_accum = 0.0

        w, h = self.width(), self.height()
        if w < 4 or h < 4:
            return

        # 粒子上限，避免堆积
        max_particles = 25
        if len(self._particles) >= max_particles:
            return

        # 低心情
        if mood_score < _LOW_MOOD_THRESHOLD:
            intensity = _clamp(1 - mood_score / _LOW_MOOD_THRESHOLD)
            self._particles.extend(_spawn_low_mood_particles(w, h, intensity))

        # 低饱食度
        if satiety < _LOW_SATIETY_THRESHOLD:
            intensity = _clamp(1 - satiety / _LOW_SATIETY_THRESHOLD)
            self._particles.extend(_spawn_low_satiety_particles(w, h, intensity))

        # 低精力
        if energy < _LOW_ENERGY_THRESHOLD:
            intensity = _clamp(1 - energy / _LOW_ENERGY_THRESHOLD)
            self._particles.extend(_spawn_low_energy_particles(w, h, intensity))

        # 高心情（独立节流，更稀疏）
        if mood_score > _HIGH_MOOD_THRESHOLD:
            self._high_mood_accum += 1.0
            if self._high_mood_accum >= 6:  # 每 6 帧（~300ms）生成一个
                self._high_mood_accum = 0.0
                intensity = _clamp((mood_score - _HIGH_MOOD_THRESHOLD) / (100 - _HIGH_MOOD_THRESHOLD))
                self._particles.extend(_spawn_high_mood_particles(w, h, intensity))

        # 再次裁剪
        if len(self._particles) > max_particles:
            self._particles = self._particles[-max_particles:]

    def set_enabled(self, enabled: bool) -> None:
        """开启/关闭粒子效果。关闭时清空现有粒子并停止生成。"""
        self._enabled = enabled
        if not enabled:
            self.clear_particles()

    def is_enabled(self) -> bool:
        return getattr(self, "_enabled", True)

    def clear_particles(self) -> None:
        """清除所有粒子。"""
        self._particles.clear()
        self.update()

    # ── 内部 ──

    def _tick(self) -> None:
        """定时器驱动：更新粒子位置与生命周期，触发重绘。"""
        alive: List[Particle] = []
        for p in self._particles:
            p.life -= p.decay
            if p.life <= 0:
                continue
            p.x += p.vx
            p.y += p.vy
            # 轻微摇摆
            p.vx += random.uniform(-0.08, 0.08)
            p.vy += random.uniform(-0.05, 0.03)
            alive.append(p)
        self._particles = alive
        self.update()

    def paintEvent(self, event) -> None:
        if not self._particles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        for p in self._particles:
            alpha_f = _clamp(p.life)  # 随生命衰减而透明
            color = QColor(p.r, p.g, p.b, int(p.a * alpha_f))

            if p.shape == "circle":
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                sz = p.size * (0.6 + 0.4 * alpha_f)  # 逐渐缩小
                painter.drawEllipse(QPointF(p.x, p.y), sz, sz)
            elif p.shape == "text":
                font = QFont()
                font.setPixelSize(int(p.size))
                painter.setFont(font)
                painter.setPen(color)
                painter.drawText(int(p.x - p.size / 2), int(p.y), p.text)

        painter.end()
