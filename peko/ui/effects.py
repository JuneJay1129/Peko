"""
特效装饰系统：在宠物周围叠加各种炫酷特效。
- 纯 QPainter 代码绘制，零素材依赖
- 独立透明叠加层，鼠标穿透，不影响操作
- 特效与宠物窗口同步移动
"""
import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple

from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt5.QtGui import (
    QPainter, QColor, QBrush, QPen, QRadialGradient, QLinearGradient,
    QPainterPath, QPolygonF, QFont
)
from PyQt5.QtWidgets import QWidget


# ============================================================
# 特效基类
# ============================================================

class BaseEffect:
    """特效基类：子类实现 paint() 即可，每帧 tick 一次。"""

    def __init__(self):
        self.t = 0.0  # 累计时间（秒）

    def tick(self, dt: float):
        """每帧调用，dt 为距上次调用的秒数。"""
        self.t += dt

    def paint(self, painter: QPainter, w: int, h: int):
        """在 w×h 的画布上绘制特效，宠物居中。"""
        pass


# ============================================================
# 🔥 火冒三丈（生气特效）
# ============================================================

class FireAuraEffect(BaseEffect):
    """冲天烈焰束生气特效：挺拔的锥形火焰从头顶冲天而起，
    底部窄顶端宽，多层火舌翻腾，顶端火星四溅烟雾升腾，气势汹汹。"""

    def __init__(self):
        super().__init__()
        # 火星粒子
        self._sparks: List[dict] = []
        # 烟雾粒子
        self._smoke: List[dict] = []
        # 火舌边缘波动相位（多层独立波动模拟翻腾）
        self._phases = [random.random() * math.pi * 2 for _ in range(5)]

    def tick(self, dt: float):
        super().tick(dt)
        # 更新各层相位
        for i in range(len(self._phases)):
            self._phases[i] += dt * (2.5 + i * 0.6)

        # 更新火星
        for s in self._sparks:
            s["x"] += s["vx"] * dt
            s["y"] += s["vy"] * dt
            s["vy"] += 0.06 * dt
            s["life"] -= dt
            s["size"] = max(0.6, s["size"] - dt * 2.5)
        self._sparks = [s for s in self._sparks if s["life"] > 0]

        # 生成火星（火焰中上部向两侧喷发）
        if random.random() < dt * 20:
            side = random.choice([-1, 1])
            self._sparks.append({
                "x": side * random.uniform(0.02, 0.12),
                "y": -random.uniform(0.3, 0.6),
                "vx": side * random.uniform(0.15, 0.4) + random.uniform(-0.05, 0.05),
                "vy": -random.uniform(0.5, 1.0),
                "life": random.uniform(0.6, 1.3),
                "size": random.uniform(1.5, 3.5),
            })

        # 更新烟雾
        for s in self._smoke:
            s["x"] += s["vx"] * dt
            s["y"] += s["vy"] * dt
            s["size"] += dt * 0.05
            s["life"] -= dt * 0.4
        self._smoke = [s for s in self._smoke if s["life"] > 0]

        # 生成烟雾（火焰顶端向上飘散）
        if random.random() < dt * 6:
            self._smoke.append({
                "x": random.uniform(-0.06, 0.06),
                "y": -random.uniform(0.65, 0.8),
                "vx": random.uniform(-0.03, 0.03),
                "vy": -random.uniform(0.08, 0.15),
                "size": random.uniform(0.04, 0.08),
                "life": random.uniform(1.5, 2.8),
            })

    def _flame_edge_wave(self, y_norm, side, phase_base, base_w):
        """计算火焰边缘波动偏移。y_norm: 0=底, 1=顶；side: -1左 1右。"""
        # 底部几乎不动，顶端摆动大（二次曲线）
        sway = y_norm * y_norm
        wave = 0.0
        for i, ph in enumerate(self._phases):
            freq = 1.2 + i * 1.0
            amp = 0.12 / (i + 1)
            wave += math.sin(ph + phase_base + y_norm * freq * math.pi) * amp
        return wave * sway * base_w * side * 0.5

    def _flame_width_profile(self, y_norm, base_w, tip_w):
        """火焰宽度剖面：底部窄 → 中上部最宽 → 顶端收尖。"""
        if y_norm < 0.2:
            # 底部窄，快速扩张
            t = y_norm / 0.2
            return base_w + (tip_w * 1.5 - base_w) * t
        elif y_norm < 0.7:
            # 中上部维持最宽
            return tip_w * 1.5
        else:
            # 顶端收尖
            t = (y_norm - 0.7) / 0.3
            return tip_w * 1.5 * (1 - t) + tip_w * 0.08 * t

    def _build_flame_layer(self, cx, base_y, total_h, base_w, tip_w, phase_off):
        """构建单层火焰路径。"""
        n_points = 40
        path = QPainterPath()

        # 左半边（从底到顶）
        for i in range(n_points + 1):
            y_norm = i / n_points
            y = base_y - total_h * y_norm
            w = self._flame_width_profile(y_norm, base_w, tip_w)
            off = self._flame_edge_wave(y_norm, -1, phase_off, base_w)
            x = cx - w + off
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        # 右半边（从顶回到底）
        for i in range(n_points, -1, -1):
            y_norm = i / n_points
            y = base_y - total_h * y_norm
            w = self._flame_width_profile(y_norm, base_w, tip_w)
            off = self._flame_edge_wave(y_norm, 1, phase_off + 0.8, base_w)
            x = cx + w + off
            path.lineTo(x, y)

        path.closeSubpath()
        return path

    def paint(self, painter: QPainter, w: int, h: int):
        cx = w / 2
        top_y = h * 0.55  # 宠物头顶位置
        base_size = min(w, h)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 整体脉动（呼吸感）
        pulse = 0.92 + 0.08 * math.sin(self.t * 4)

        # ===== 底部热浪光晕 =====
        glow_r = base_size * 0.32 * pulse
        heat_glow = QRadialGradient(cx, top_y, glow_r * 2.0)
        heat_glow.setColorAt(0, QColor(255, 70, 20, 100))
        heat_glow.setColorAt(0.3, QColor(255, 40, 0, 60))
        heat_glow.setColorAt(0.7, QColor(255, 20, 0, 20))
        heat_glow.setColorAt(1, QColor(255, 0, 0, 0))
        painter.setBrush(QBrush(heat_glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, top_y), glow_r * 2.0, glow_r)

        # ===== 烟雾（画在火焰后面） =====
        for s in self._smoke:
            sx = cx + s["x"] * base_size
            sy = top_y + s["y"] * base_size
            size = s["size"] * base_size
            alpha = int(min(1.0, s["life"]) * 45)
            sg = QRadialGradient(sx, sy, size)
            sg.setColorAt(0, QColor(65, 50, 45, alpha))
            sg.setColorAt(1, QColor(35, 25, 25, 0))
            painter.setBrush(QBrush(sg))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(sx, sy), size, size * 0.7)

        # ===== 主火焰（5 层叠加，外→内：宽暗→窄亮） =====
        total_h = base_size * 0.70 * pulse  # 总高度
        base_w = base_size * 0.10  # 底部窄
        tip_w = base_size * 0.22   # 顶端宽

        # 5 层配置：(高度比, 宽度比, 相位偏移, 底部色, 顶部色)
        layers = [
            (1.00, 1.00, 0.0,   QColor(180, 15, 0, 170),   QColor(255, 70, 0, 100)),
            (0.92, 0.86, 1.5,   QColor(255, 50, 0, 220),   QColor(255, 140, 0, 170)),
            (0.82, 0.70, 2.8,   QColor(255, 130, 0, 240),  QColor(255, 210, 30, 220)),
            (0.68, 0.50, 0.7,   QColor(255, 210, 40, 250), QColor(255, 255, 140, 230)),
            (0.50, 0.28, 3.5,   QColor(255, 255, 210, 255), QColor(255, 255, 180, 180)),
        ]

        for h_ratio, w_ratio, phase_off, c_bot, c_top in layers:
            path = self._build_flame_layer(
                cx, top_y,
                total_h * h_ratio,
                base_w * w_ratio,
                tip_w * w_ratio,
                phase_off
            )
            grad = QLinearGradient(cx, top_y, cx, top_y - total_h * h_ratio)
            grad.setColorAt(0, c_bot)
            grad.setColorAt(0.5, c_top)
            grad.setColorAt(1, QColor(c_top.red(), c_top.green(), c_top.blue(), 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

        # ===== 两侧分叉小火舌 =====
        for side in [-1, 1]:
            for i in range(2):
                fh = total_h * (0.30 + i * 0.12)
                fw = base_w * (0.35 + i * 0.18)
                fx = cx + side * base_size * (0.13 + i * 0.04)
                fy = top_y - total_h * (0.18 + i * 0.12)

                path = QPainterPath()
                sway = math.sin(self._phases[i] + side * 2) * fw * 0.25
                path.moveTo(fx - fw, fy)
                path.cubicTo(fx - fw * 0.75, fy - fh * 0.35,
                             fx - fw * 0.25 + sway, fy - fh * 0.75,
                             fx + sway * 0.4, fy - fh)
                path.cubicTo(fx + fw * 0.25 + sway, fy - fh * 0.75,
                             fx + fw * 0.75, fy - fh * 0.35,
                             fx + fw, fy)
                path.closeSubpath()

                grad = QLinearGradient(fx, fy, fx, fy - fh)
                grad.setColorAt(0, QColor(255, 90, 0, 190))
                grad.setColorAt(0.5, QColor(255, 170, 30, 210))
                grad.setColorAt(1, QColor(255, 230, 100, 90))
                painter.setBrush(QBrush(grad))
                painter.setPen(Qt.NoPen)
                painter.drawPath(path)

        # ===== 火星粒子 =====
        for s in self._sparks:
            sx = cx + s["x"] * base_size
            sy = top_y + s["y"] * base_size
            alpha = int(min(255, s["life"] * 255))
            # 外发光
            sg = QRadialGradient(sx, sy, s["size"] * 5)
            sg.setColorAt(0, QColor(255, 200, 60, int(alpha * 0.75)))
            sg.setColorAt(0.5, QColor(255, 110, 0, int(alpha * 0.35)))
            sg.setColorAt(1, QColor(255, 50, 0, 0))
            painter.setBrush(QBrush(sg))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(sx, sy), s["size"] * 5, s["size"] * 5)
            # 核心亮点
            painter.setBrush(QBrush(QColor(255, 255, 200, alpha)))
            painter.drawEllipse(QPointF(sx, sy), s["size"], s["size"])

        painter.restore()


# ============================================================
# ⚡ 闪电环绕
# ============================================================

class LightningEffect(BaseEffect):
    """周围随机劈下蓝紫色闪电，带闪光。"""

    def __init__(self):
        super().__init__()
        self._bolts: List[dict] = []
        self._flash = 0.0

    def tick(self, dt: float):
        super().tick(dt)
        self._flash = max(0, self._flash - dt * 3)

        # 更新闪电
        for b in self._bolts:
            b["life"] -= dt
        self._bolts = [b for b in self._bolts if b["life"] > 0]

        # 随机生成新闪电
        if random.random() < dt * 1.2:
            side = random.choice(["left", "right", "top"])
            self._bolts.append({
                "side": side,
                "life": random.uniform(0.15, 0.35),
                "max_life": 0.35,
                "seed": random.randint(0, 10000),
                "jitter": random.uniform(0.3, 0.6),
            })
            self._flash = min(1.0, self._flash + 0.4)

    def _draw_bolt(self, painter, x0, y0, x1, y1, jitter, seed):
        """绘制一段锯齿闪电。"""
        random.seed(seed)
        steps = 8
        points = [QPointF(x0, y0)]
        for i in range(1, steps):
            t = i / steps
            x = x0 + (x1 - x0) * t + random.uniform(-jitter, jitter) * 40
            y = y0 + (y1 - y0) * t + random.uniform(-jitter, jitter) * 20
            points.append(QPointF(x, y))
        points.append(QPointF(x1, y1))

        path = QPainterPath()
        path.moveTo(points[0])
        for p in points[1:]:
            path.lineTo(p)

        pen = QPen(QColor(180, 160, 255, 255), 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)

        # 外层光晕
        pen2 = QPen(QColor(120, 80, 255, 120), 8)
        pen2.setCapStyle(Qt.RoundCap)
        painter.setPen(pen2)
        painter.drawPath(path)

    def paint(self, painter: QPainter, w: int, h: int):
        cx, cy = w / 2, h / 2
        radius = min(w, h) * 0.4

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景闪光
        if self._flash > 0:
            alpha = int(self._flash * 60)
            glow = QRadialGradient(cx, cy, radius * 2)
            glow.setColorAt(0, QColor(180, 150, 255, alpha))
            glow.setColorAt(1, QColor(100, 50, 255, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), radius * 2, radius * 2)

        # 绘制各条闪电
        for b in self._bolts:
            alpha = int(min(1.0, b["life"] / 0.15) * 255)
            side = b["side"]
            if side == "left":
                x0 = cx - radius * 0.8
                y0 = cy - radius * 0.8
                x1 = cx - radius * 0.1
                y1 = cy + radius * 0.1
            elif side == "right":
                x0 = cx + radius * 0.8
                y0 = cy - radius * 0.7
                x1 = cx + radius * 0.1
                y1 = cy + radius * 0.2
            else:  # top
                x0 = cx + random.uniform(-radius * 0.3, radius * 0.3)
                y0 = cy - radius * 0.9
                x1 = cx
                y1 = cy - radius * 0.1

            self._draw_bolt(painter, x0, y0, x1, y1, b["jitter"], b["seed"])

        painter.restore()


# ============================================================
# 🌑 暗黑魔气
# ============================================================

class DarkAuraEffect(BaseEffect):
    """紫黑色烟雾盘旋上升 + 红色裂纹。"""

    def __init__(self):
        super().__init__()
        self._smoke: List[dict] = []
        self._cracks: List[dict] = []

    def tick(self, dt: float):
        super().tick(dt)
        for s in self._smoke:
            s["y"] -= s["vy"] * dt
            s["x"] += math.sin(self.t * 2 + s["seed"]) * 0.15 * dt
            s["size"] += dt * 0.15
            s["life"] -= dt * 0.6
        self._smoke = [s for s in self._smoke if s["life"] > 0]

        if random.random() < dt * 3:
            self._smoke.append({
                "x": random.uniform(-0.2, 0.2),
                "y": 0.45,
                "vy": random.uniform(0.15, 0.35),
                "size": random.uniform(0.1, 0.2),
                "life": random.uniform(1.5, 2.5),
                "seed": random.random() * 6.28,
            })

        for c in self._cracks:
            c["life"] -= dt
        self._cracks = [c for c in self._cracks if c["life"] > 0]

        if random.random() < dt * 0.8:
            self._cracks.append({
                "life": random.uniform(0.1, 0.25),
                "seed": random.randint(0, 99999),
            })

    def paint(self, painter: QPainter, w: int, h: int):
        cx, cy = w / 2, h / 2
        radius = min(w, h) * 0.4

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 底部魔气光晕
        glow = QRadialGradient(cx, cy + radius * 0.3, radius * 1.2)
        glow.setColorAt(0, QColor(80, 20, 120, 100))
        glow.setColorAt(0.6, QColor(40, 0, 80, 60))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy + radius * 0.2), radius * 1.3, radius * 0.8)

        # 烟雾团
        for s in self._smoke:
            sx = cx + s["x"] * radius * 2
            sy = cy + s["y"] * radius * 2
            size = s["size"] * radius * 2
            alpha = int(min(1.0, s["life"]) * 80)

            sg = QRadialGradient(sx, sy, size)
            sg.setColorAt(0, QColor(60, 20, 100, alpha))
            sg.setColorAt(0.6, QColor(30, 5, 60, alpha // 2))
            sg.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(sg))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(sx, sy), size, size * 0.8)

        # 红色闪电裂纹
        for c in self._cracks:
            alpha = int(min(1.0, c["life"] / 0.15) * 255)
            random.seed(c["seed"])
            points = []
            n = 6
            start_angle = random.uniform(0, math.pi * 2)
            start_r = radius * 0.6
            end_r = radius * 1.1
            for i in range(n + 1):
                t = i / n
                r = start_r + (end_r - start_r) * t
                angle = start_angle + t * random.uniform(-0.5, 0.5)
                angle += random.uniform(-0.2, 0.2)
                points.append(QPointF(
                    cx + math.cos(angle) * r,
                    cy + math.sin(angle) * r
                ))
            path = QPainterPath()
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
            pen = QPen(QColor(255, 30, 30, alpha), 2)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.restore()


# ============================================================
# ✨ 星光环绕
# ============================================================

class StarEffect(BaseEffect):
    """金色星星绕宠物旋转。"""

    def __init__(self):
        super().__init__()
        self._stars = [
            {"orbit": 1.0, "speed": 1.0, "size": 1.0, "phase": 0.0},
            {"orbit": 0.8, "speed": -1.3, "size": 0.7, "phase": 1.5},
            {"orbit": 1.2, "speed": 0.7, "size": 0.9, "phase": 3.0},
            {"orbit": 0.9, "speed": -0.9, "size": 0.6, "phase": 0.8},
            {"orbit": 1.1, "speed": 1.2, "size": 0.8, "phase": 2.2},
            {"orbit": 0.7, "speed": 1.5, "size": 0.5, "phase": 4.0},
        ]

    def _draw_star(self, painter, cx, cy, outer_r, inner_r, points=5, rotation=0):
        poly = QPolygonF()
        for i in range(points * 2):
            angle = i * math.pi / points + rotation - math.pi / 2
            r = outer_r if i % 2 == 0 else inner_r
            poly.append(QPointF(
                cx + math.cos(angle) * r,
                cy + math.sin(angle) * r
            ))
        painter.drawPolygon(poly)

    def paint(self, painter: QPainter, w: int, h: int):
        cx, cy = w / 2, h / 2
        base_r = min(w, h) * 0.38

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        for s in self._stars:
            angle = self.t * s["speed"] + s["phase"]
            ox = cx + math.cos(angle) * base_r * s["orbit"]
            oy = cy + math.sin(angle) * base_r * s["orbit"] * 0.6  # 椭圆轨道
            size = s["size"] * base_r * 0.12
            # 闪烁
            twinkle = 0.6 + 0.4 * math.sin(self.t * 4 + s["phase"] * 2)

            # 光晕
            glow = QRadialGradient(ox, oy, size * 3)
            glow.setColorAt(0, QColor(255, 220, 80, int(100 * twinkle)))
            glow.setColorAt(1, QColor(255, 200, 0, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(ox, oy), size * 3, size * 3)

            # 星星
            painter.setBrush(QBrush(QColor(255, 230, 100, int(255 * twinkle))))
            painter.setPen(QPen(QColor(255, 200, 30, int(255 * twinkle)), 1))
            self._draw_star(painter, ox, oy, size, size * 0.4, 5, self.t * s["speed"] * 2)

        painter.restore()


# ============================================================
# 🌈 彩虹光环
# ============================================================

class RainbowAuraEffect(BaseEffect):
    """平面拱形彩虹：只有上半圈，7 色清晰分明，柔光外发光，呼吸浮动。"""

    def __init__(self):
        super().__init__()

    def paint(self, painter: QPainter, w: int, h: int):
        cx = w / 2
        cy = h * 0.62  # 彩虹底部中心（宠物中部偏下）
        radius = min(w, h) * 0.42
        band_width = radius * 0.07  # 每条色带宽度

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 呼吸浮动
        breathe = math.sin(self.t * 1.5) * radius * 0.03
        cy += breathe

        # 7 色（从外到内：红橙黄绿青蓝紫）
        rainbow_colors = [
            QColor(255, 70, 70),     # 红
            QColor(255, 150, 50),    # 橙
            QColor(255, 220, 50),    # 黄
            QColor(90, 220, 90),     # 绿
            QColor(60, 200, 200),    # 青
            QColor(80, 140, 255),    # 蓝
            QColor(180, 100, 240),   # 紫
        ]

        # 外层柔光光晕（只画半圆，用 QPainterPath + 渐变填充）
        glow_path = QPainterPath()
        outer_glow_r = radius + band_width * 3
        # 上半椭圆光晕
        glow_path.moveTo(cx - outer_glow_r, cy)
        glow_path.arcTo(QRectF(cx - outer_glow_r, cy - outer_glow_r,
                               outer_glow_r * 2, outer_glow_r * 2),
                        180, -180)
        glow_path.lineTo(cx + outer_glow_r, cy)
        glow_path.closeSubpath()

        glow_gradient = QLinearGradient(cx, cy - outer_glow_r, cx, cy)
        glow_gradient.setColorAt(0, QColor(200, 150, 255, 0))
        glow_gradient.setColorAt(0.5, QColor(255, 180, 200, 25))
        glow_gradient.setColorAt(1.0, QColor(255, 200, 220, 0))
        painter.setBrush(QBrush(glow_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawPath(glow_path)

        # 画 7 条色带（从外到内画，用 drawArc 画上半弧）
        for i, color in enumerate(rainbow_colors):
            r = radius - i * band_width
            pen = QPen(color, band_width * 0.9)
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            rect = QRectF(cx - r + band_width / 2, cy - r + band_width / 2,
                         (r - band_width / 2) * 2, (r - band_width / 2) * 2)
            # 180 度上半弧（从 180° 扫到 0°）
            painter.drawArc(rect, 180 * 16, -180 * 16)

        painter.restore()


# ============================================================
# 🌸 樱花飘落
# ============================================================

class SakuraEffect(BaseEffect):
    """粉色樱花花瓣飘落。"""

    def __init__(self):
        super().__init__()
        self._petals: List[dict] = []

    def tick(self, dt: float):
        super().tick(dt)
        for p in self._petals:
            p["y"] += p["vy"] * dt
            p["x"] += math.sin(self.t * p["swing"] + p["seed"]) * p["vxAmp"] * dt
            p["rot"] += p["vr"] * dt
            p["life"] -= dt
        self._petals = [p for p in self._petals if p["life"] > 0 and p["y"] < 1.2]

        if random.random() < dt * 8:
            self._petals.append({
                "x": random.uniform(-0.5, 0.5),
                "y": -0.5,
                "vy": random.uniform(0.15, 0.35),
                "vxAmp": random.uniform(0.1, 0.25),
                "swing": random.uniform(1.0, 3.0),
                "size": random.uniform(0.04, 0.09),
                "rot": random.random() * 6.28,
                "vr": random.uniform(-2.0, 2.0),
                "life": random.uniform(3.0, 5.0),
                "seed": random.random() * 6.28,
            })

    def _draw_petal(self, painter, x, y, size, rot):
        painter.save()
        painter.translate(x, y)
        painter.rotate(math.degrees(rot))

        # 5瓣樱花
        color = QColor(255, 180, 210, 220)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(255, 150, 190, 180), 1))

        for i in range(5):
            angle = i * (2 * math.pi / 5) - math.pi / 2
            px = math.cos(angle) * size * 0.4
            py = math.sin(angle) * size * 0.4
            painter.drawEllipse(QPointF(px, py), size * 0.5, size * 0.35)

        # 花芯
        painter.setBrush(QBrush(QColor(255, 240, 100, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, 0), size * 0.15, size * 0.15)

        painter.restore()

    def paint(self, painter: QPainter, w: int, h: int):
        cx, cy = w / 2, h / 2
        radius = min(w, h) * 0.5

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        for p in self._petals:
            px = cx + p["x"] * radius * 2
            py = cy + p["y"] * radius * 2
            size = p["size"] * radius
            self._draw_petal(painter, px, py, size, p["rot"])

        painter.restore()


# ============================================================
# ❄️ 冰雪气场
# ============================================================

class IceEffect(BaseEffect):
    """多轨道旋转雪花粒子，无底部底盘。"""

    def __init__(self):
        super().__init__()
        self._flakes: List[dict] = []
        # 25 片雪花，三层轨道
        for i in range(25):
            layer = i % 3  # 0 内层, 1 中层, 2 外层
            orbit_range = [(0.35, 0.55), (0.6, 0.85), (0.9, 1.2)][layer]
            speed_range = [(1.5, 2.5), (1.0, 1.8), (0.5, 1.2)][layer]
            dir_mul = 1 if layer != 1 else -1  # 中层反向
            self._flakes.append({
                "orbit": random.uniform(*orbit_range),
                "speed": random.uniform(*speed_range) * dir_mul,
                "size": random.uniform(0.035, 0.10),
                "phase": random.random() * math.pi * 2,
                "y_off": random.uniform(-0.35, 0.35),
                "wobble_phase": random.random() * math.pi * 2,
                "wobble_speed": random.uniform(1.5, 3.0),
            })

    def _draw_snowflake(self, painter, x, y, size, rot, alpha=255):
        painter.save()
        painter.translate(x, y)
        painter.rotate(math.degrees(rot))
        pen = QPen(QColor(210, 235, 255, alpha), max(1, size * 0.15))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        # 六角雪花
        for i in range(6):
            angle = i * math.pi / 3
            painter.drawLine(
                QPointF(0, 0),
                QPointF(math.cos(angle) * size, math.sin(angle) * size)
            )
            # 小分支
            mid_x = math.cos(angle) * size * 0.55
            mid_y = math.sin(angle) * size * 0.55
            perp = angle + math.pi / 2
            painter.drawLine(
                QPointF(mid_x, mid_y),
                QPointF(mid_x + math.cos(perp) * size * 0.28, mid_y + math.sin(perp) * size * 0.28)
            )
            # 内侧小分支
            mid2_x = math.cos(angle) * size * 0.3
            mid2_y = math.sin(angle) * size * 0.3
            painter.drawLine(
                QPointF(mid2_x, mid2_y),
                QPointF(mid2_x + math.cos(perp) * size * 0.18, mid2_y + math.sin(perp) * size * 0.18)
            )
        painter.restore()

    def paint(self, painter: QPainter, w: int, h: int):
        cx, cy = w / 2, h / 2
        radius = min(w, h) * 0.42

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 雪花（从外层往内层画，内层在上）
        for f in sorted(self._flakes, key=lambda x: -x["orbit"]):
            angle = self.t * f["speed"] + f["phase"]
            wobble = math.sin(self.t * f["wobble_speed"] + f["wobble_phase"]) * 0.08
            fx = cx + math.cos(angle) * radius * f["orbit"] + wobble * radius
            fy = cy + f["y_off"] * radius + math.sin(angle * 2) * radius * 0.08
            size = f["size"] * radius
            # 外层雪花更透明
            alpha = int(180 + (1 - f["orbit"] / 1.2) * 75)
            self._draw_snowflake(painter, fx, fy, size, self.t * f["speed"] * 2.5, alpha)

        painter.restore()


# ============================================================
# 🔮 魔法阵
# ============================================================

class MagicCircleEffect(BaseEffect):
    """底部 3D 立体魔法阵：扁椭圆透视 + 光柱 + 动态变色 + 脉冲呼吸 + 双层反向旋转。"""

    # 颜色循环：蓝→紫→粉→金→蓝
    _COLOR_CYCLE = [
        QColor(100, 180, 255),   # 蓝
        QColor(180, 120, 255),   # 紫
        QColor(255, 120, 200),   # 粉
        QColor(255, 210, 80),    # 金
        QColor(100, 180, 255),   # 蓝（回到起点）
    ]

    def __init__(self):
        super().__init__()

    def _lerp_color(self, c1: QColor, c2: QColor, t: float) -> QColor:
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
            int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
        )

    def _get_cycle_color(self) -> QColor:
        n = len(self._COLOR_CYCLE) - 1
        t = (self.t * 0.15) % n
        idx = int(t)
        frac = t - idx
        return self._lerp_color(self._COLOR_CYCLE[idx], self._COLOR_CYCLE[idx + 1], frac)

    def _draw_hexagram_3d(self, painter, cx, cy, rx, ry, rot, color, alpha=220):
        """绘制 3D 透视扁椭圆魔法阵。
        正确的 3D 透视旋转：先 translate 到中心 → scale(1, ry/rx) 压扁 y 轴 → rotate 旋转。
        这样圆环、六角星、符文点都在扁坐标系内同步旋转，形状不变形。
        """
        painter.save()
        painter.translate(cx, cy)
        painter.scale(1.0, ry / rx)  # 先把正圆坐标系压扁成椭圆透视
        painter.rotate(math.degrees(rot))  # 再旋转（整阵同步转）

        c = QColor(color)
        c.setAlpha(alpha)

        # ===== 底部发光底座（正圆 → scale 后变椭圆） =====
        base_glow = QRadialGradient(0, 0, rx)
        base_glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), int(alpha * 0.5)))
        base_glow.setColorAt(0.6, QColor(color.red(), color.green(), color.blue(), int(alpha * 0.2)))
        base_glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(base_glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, 0), rx, rx)

        # ===== 外圆环 =====
        pen = QPen(c, max(2, rx * 0.03))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), rx, rx)

        # 内圆环
        inner_c = QColor(color)
        inner_c.setAlpha(int(alpha * 0.7))
        pen2 = QPen(inner_c, max(1.5, rx * 0.02))
        painter.setPen(pen2)
        painter.drawEllipse(QPointF(0, 0), rx * 0.8, rx * 0.8)

        # 更内圆
        pen3 = QPen(c, max(1, rx * 0.015))
        painter.setPen(pen3)
        painter.drawEllipse(QPointF(0, 0), rx * 0.55, rx * 0.55)

        # ===== 六角星（在正圆坐标系内画，scale 自动压扁） =====
        star_c = QColor(color)
        star_c.setAlpha(int(alpha * 0.9))
        pen4 = QPen(star_c, max(2.5, rx * 0.035))
        pen4.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen4)
        r_star = rx * 0.65
        for direction in [1, -1]:
            tri = QPolygonF()
            for i in range(3):
                angle = i * (2 * math.pi / 3) + direction * math.pi / 6
                tri.append(QPointF(
                    math.cos(angle) * r_star,
                    math.sin(angle) * r_star
                ))
            painter.drawPolygon(tri)

        # ===== 12 个符文点（正圆坐标系 → 透视近大远小通过角度计算深度） =====
        for i in range(12):
            angle = i * math.pi / 6  # 已经 rotate 过了，这里用静态角度即可
            px = math.cos(angle) * rx * 0.9
            py = math.sin(angle) * rx * 0.9
            # 近大远小：在扁透视中，y 越大（越靠下/越靠近观察者）点越大
            # 注意：因为 scale 了 y 轴，真实视觉深度由 py/rx 决定
            depth = (math.sin(angle) + 1) / 2  # 0~1，下=1上=0
            dot_size = rx * (0.03 + depth * 0.035)
            dot_c = QColor(color)
            dot_c.setAlpha(int(alpha * (0.5 + depth * 0.5)))
            painter.setBrush(QBrush(dot_c))
            painter.setPen(Qt.NoPen)
            # 在压扁坐标系内画正圆，scale 后视觉上是椭圆
            painter.drawEllipse(QPointF(px, py), dot_size, dot_size)

        # ===== 中心光点 =====
        center_glow = QRadialGradient(0, 0, rx * 0.3)
        center_c = QColor(color)
        center_c.setAlpha(int(alpha * 0.8))
        center_glow.setColorAt(0, center_c)
        center_glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(center_glow))
        painter.drawEllipse(QPointF(0, 0), rx * 0.3, rx * 0.3)

        painter.restore()

    def paint(self, painter: QPainter, w: int, h: int):
        cx = w / 2
        cy = h * 0.70  # 魔法阵圆心位置（上移，离宠物更近）
        rx = min(w, h) * 0.36  # 水平半径（缩小，更精致贴身）
        ry = rx * 0.28  # 垂直半径（3D 透视压扁）

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        color = self._get_cycle_color()

        # 脉冲缩放（呼吸）
        pulse = 1.0 + 0.05 * math.sin(self.t * 2.5)
        cur_rx = rx * pulse
        cur_ry = ry * pulse

        # 外层魔法阵（正向旋转，慢）
        self._draw_hexagram_3d(painter, cx, cy, cur_rx, cur_ry, self.t * 0.5, color, 210)
        # 内层魔法阵（反向旋转，快，更小）
        inner_color = self._lerp_color(color, QColor(255, 255, 255), 0.25)
        self._draw_hexagram_3d(painter, cx, cy, cur_rx * 0.5, cur_ry * 0.5,
                               -self.t * 1.2, inner_color, 170)

        painter.restore()


# ============================================================
# 💧 水之波动
# ============================================================

class WaterWaveEffect(BaseEffect):
    """气泡从底部一直升到顶部，左右摆动，无底盘。大量气泡，大小差异大。"""

    def __init__(self):
        super().__init__()
        self._bubbles: List[dict] = []
        # 预生成一些气泡
        for _ in range(20):
            self._bubbles.append(self._make_bubble(random_y=True))

    def _make_bubble(self, random_y=False):
        return {
            "x": random.uniform(-0.35, 0.35),
            "y": random.uniform(0.5, -0.5) if random_y else 0.5,
            "vy": random.uniform(0.12, 0.28),
            "size": random.uniform(0.02, 0.07),
            "seed": random.random() * math.pi * 2,
            "wobble": random.uniform(0.03, 0.1),
            "wobble_speed": random.uniform(1.0, 3.0),
        }

    def tick(self, dt: float):
        super().tick(dt)
        for b in self._bubbles:
            b["y"] -= b["vy"] * dt
            b["x"] += math.sin(self.t * b["wobble_speed"] + b["seed"]) * b["wobble"] * dt
            # 顶部慢慢变大
            b["size"] += dt * 0.005
        # 移出顶部的替换掉
        new_bubbles = []
        for b in self._bubbles:
            if b["y"] < -0.55:
                new_bubbles.append(self._make_bubble())
            else:
                new_bubbles.append(b)
        self._bubbles = new_bubbles

    def paint(self, painter: QPainter, w: int, h: int):
        cx, cy = w / 2, h / 2
        base_r = min(w, h) * 0.45

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 按 y 排序，靠后的先画（底部的在后面）
        for b in sorted(self._bubbles, key=lambda x: -x["y"]):
            bx = cx + b["x"] * base_r * 2
            by = cy + b["y"] * base_r * 2
            size = b["size"] * base_r

            # 顶部渐隐
            fade = 1.0
            if b["y"] < -0.4:
                fade = max(0, (-0.4 - b["y"]) / (-0.4 + 0.55))
                fade = 1.0 - fade
            # 底部渐入
            if b["y"] > 0.4:
                fade = min(fade, (0.5 - b["y"]) / 0.1)
            alpha = int(180 * max(0, min(1, fade)))

            # 气泡本体（半透明填充 + 边框）
            painter.setBrush(QBrush(QColor(180, 220, 255, alpha // 4)))
            pen = QPen(QColor(100, 180, 255, alpha), max(1, size * 0.12))
            painter.setPen(pen)
            painter.drawEllipse(QPointF(bx, by), size, size)

            # 高光点
            hl_alpha = int(alpha * 1.2)
            painter.setBrush(QBrush(QColor(255, 255, 255, hl_alpha)))
            painter.setPen(Qt.NoPen)
            hl_x = bx - size * 0.3
            hl_y = by - size * 0.35
            hl_size = size * 0.22
            painter.drawEllipse(QPointF(hl_x, hl_y), hl_size, hl_size * 0.8)

            # 内部第二个小高光
            painter.setBrush(QBrush(QColor(220, 240, 255, alpha // 2)))
            painter.drawEllipse(QPointF(bx + size * 0.2, by + size * 0.25), size * 0.12, size * 0.08)

        painter.restore()


# ============================================================
# 💖 爱心气泡
# ============================================================

class HeartBubbleEffect(BaseEffect):
    """大量爱心从宠物上方/周围冒出上升，多种形状+多种颜色，路径随机。"""

    _HEART_COLORS = [
        QColor(255, 120, 160),   # 粉红
        QColor(255, 60, 100),    # 玫红
        QColor(255, 190, 210),   # 浅粉
        QColor(255, 100, 150),   # 深粉
        QColor(255, 210, 225),   # 粉白
    ]

    def __init__(self):
        super().__init__()
        self._hearts: List[dict] = []
        # 预填充一批
        for _ in range(8):
            self._hearts.append(self._make_heart(random_y=True))

    def _make_heart(self, random_y=False):
        shape = random.choice(["standard", "fat", "small"])
        return {
            "x": random.uniform(-0.35, 0.35),
            "y": random.uniform(0.4, -0.5) if random_y else random.uniform(0.3, 0.5),
            "vy": random.uniform(0.12, 0.28),
            "size": random.uniform(0.03, 0.10),
            "shape": shape,
            "color": random.choice(self._HEART_COLORS),
            "life": random.uniform(2.5, 4.0),
            "max_life": 4.0,
            "seed": random.random() * math.pi * 2,
            "wobble": random.uniform(0.05, 0.15),
            "wobble_speed": random.uniform(1.0, 3.0),
            "rot": random.uniform(-0.3, 0.3),
            "rot_speed": random.uniform(-0.5, 0.5),
        }

    def tick(self, dt: float):
        super().tick(dt)
        for h in self._hearts:
            h["y"] -= h["vy"] * dt
            h["x"] += math.sin(self.t * h["wobble_speed"] + h["seed"]) * h["wobble"] * dt
            h["rot"] += h["rot_speed"] * dt
            h["life"] -= dt
        # 飞出顶部的补充新的
        new_hearts = []
        for h in self._hearts:
            if h["y"] < -0.55 or h["life"] <= 0:
                new_hearts.append(self._make_heart())
            else:
                new_hearts.append(h)
        self._hearts = new_hearts
        # 控制数量在 10~15 之间
        while len(self._hearts) < 10:
            self._hearts.append(self._make_heart())

    def _draw_heart(self, painter, x, y, size, shape, color, rot=0):
        painter.save()
        painter.translate(x, y)
        painter.rotate(math.degrees(rot))

        # 形状参数
        if shape == "fat":
            width_scale = 1.3
            height_scale = 0.85
        elif shape == "small":
            width_scale = 0.7
            height_scale = 0.7
        else:  # standard
            width_scale = 1.0
            height_scale = 1.0

        s = size
        path = QPainterPath()
        # 标准心形
        w = s * width_scale
        hgt = s * height_scale * 1.1
        path.moveTo(0, hgt * 0.25)
        path.cubicTo(0, -hgt * 0.1, -w, -hgt * 0.1, -w, hgt * 0.25)
        path.cubicTo(-w, hgt * 0.75, 0, hgt * 1.1, 0, hgt * 1.2)
        path.cubicTo(0, hgt * 1.1, w, hgt * 0.75, w, hgt * 0.25)
        path.cubicTo(w, -hgt * 0.1, 0, -hgt * 0.1, 0, hgt * 0.25)

        # 渐变
        gradient = QRadialGradient(0, hgt * 0.3, s)
        c_light = QColor(color)
        c_light = c_light.lighter(130)
        c_light.setAlpha(240)
        c_dark = QColor(color)
        c_dark = c_dark.darker(115)
        c_dark.setAlpha(220)
        gradient.setColorAt(0, c_light)
        gradient.setColorAt(1, c_dark)
        painter.setBrush(QBrush(gradient))

        # 描边
        edge = QColor(color)
        edge = edge.darker(120)
        edge.setAlpha(200)
        painter.setPen(QPen(edge, max(1, size * 0.08)))
        painter.drawPath(path)

        # 高光
        hl = QColor(255, 255, 255, 150)
        painter.setBrush(QBrush(hl))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(-w * 0.35, hgt * 0.1), w * 0.18, hgt * 0.15)

        painter.restore()

    def paint(self, painter: QPainter, w: int, h: int):
        cx, cy = w / 2, h / 2
        radius = min(w, h) * 0.45

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 按 y 排序：靠后的先画
        for heart in sorted(self._hearts, key=lambda x: -x["y"]):
            hx = cx + heart["x"] * radius * 2
            hy = cy + heart["y"] * radius * 2
            size = heart["size"] * radius

            # 顶部渐隐 + 底部渐入
            fade = 1.0
            if heart["y"] < -0.4:
                fade = max(0, (-0.4 - heart["y"]) / 0.15)
                fade = 1.0 - fade
            if heart["y"] > 0.35:
                fade = min(fade, (0.5 - heart["y"]) / 0.15)
            life_fade = min(1.0, heart["life"] / 0.5)
            fade = min(fade, life_fade)
            fade = max(0, min(1, fade))

            painter.save()
            painter.setOpacity(fade)
            self._draw_heart(painter, hx, hy, size, heart["shape"], heart["color"], heart["rot"])
            painter.restore()

        painter.restore()


# ============================================================
# 🪙 金币雨
# ============================================================

class CoinRainEffect(BaseEffect):
    """金色硬币从天而降。"""

    def __init__(self):
        super().__init__()
        self._coins: List[dict] = []

    def tick(self, dt: float):
        super().tick(dt)
        for c in self._coins:
            c["y"] += c["vy"] * dt
            c["vy"] += dt * 0.3  # 重力
            c["spin"] += c["vspin"] * dt
            c["life"] -= dt
        self._coins = [c for c in self._coins if c["life"] > 0 and c["y"] < 0.8]

        if random.random() < dt * 6:
            self._coins.append({
                "x": random.uniform(-0.4, 0.4),
                "y": -0.5,
                "vy": random.uniform(0.1, 0.2),
                "size": random.uniform(0.05, 0.09),
                "spin": random.random() * 6.28,
                "vspin": random.uniform(3.0, 6.0),
                "life": random.uniform(3.0, 5.0),
            })

    def _draw_coin(self, painter, x, y, size, spin_angle):
        # 用椭圆宽度模拟旋转
        scale_x = abs(math.cos(spin_angle))
        rx = size * max(0.15, scale_x)
        ry = size

        # 金币本体
        gradient = QRadialGradient(x - rx * 0.3, y - ry * 0.3, rx)
        gradient.setColorAt(0, QColor(255, 240, 120, 255))
        gradient.setColorAt(1, QColor(220, 160, 20, 255))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(180, 120, 0, 255), 1.5))
        painter.drawEllipse(QPointF(x, y), rx, ry)

        # 中间的$符号（只在正对时显示）
        if scale_x > 0.5:
            painter.setPen(QPen(QColor(160, 100, 0, 200), 1.5))
            font = QFont()
            font.setBold(True)
            font.setPixelSize(int(ry * 1.2))
            painter.setFont(font)
            painter.drawText(QRectF(x - rx, y - ry, rx * 2, ry * 2),
                           Qt.AlignCenter, "$")

    def paint(self, painter: QPainter, w: int, h: int):
        cx, cy = w / 2, h / 2
        radius = min(w, h) * 0.5

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        for c in self._coins:
            cx_i = cx + c["x"] * radius * 2
            cy_i = cy + c["y"] * radius * 2
            size = c["size"] * radius
            self._draw_coin(painter, cx_i, cy_i, size, c["spin"])

        painter.restore()


# ============================================================
# 💭 思考气泡
# ============================================================

class ThinkBubbleEffect(BaseEffect):
    """头顶思考图标，无气泡背景，5 种内容循环，带外发光。"""

    # 5 种内容：灯泡灵感 / 问号疑惑 / 感叹号震惊 / 省略号思考 / Zzz 犯困
    _CONTENTS = ["bulb", "question", "exclamation", "ellipsis", "zzz"]
    _FADE_IN = 1.5    # 淡入 1.5s
    _HOLD = 6.0       # 保持 6s
    _FADE_OUT = 1.5   # 淡出 1.5s
    _WAIT = 1.0       # 等待 1s
    _CYCLE = _FADE_IN + _HOLD + _FADE_OUT + _WAIT  # 10s

    def _get_alpha_scale(self):
        t = self.t % self._CYCLE
        if t < self._FADE_IN:
            return t / self._FADE_IN
        elif t < self._FADE_IN + self._HOLD:
            return 1.0
        elif t < self._FADE_IN + self._HOLD + self._FADE_OUT:
            return (self._FADE_IN + self._HOLD + self._FADE_OUT - t) / self._FADE_OUT
        else:
            return 0.0

    def _get_current_content(self):
        idx = int(self.t / self._CYCLE) % len(self._CONTENTS)
        return self._CONTENTS[idx]

    def paint(self, painter: QPainter, w, h):
        alpha_scale = self._get_alpha_scale()
        if alpha_scale <= 0:
            return

        cx = w / 2
        # 头顶位置（特效层上方区域）
        # 特效层 expand_top=0.9, 宠物高度比例 = 1 / (1 + 0.9 + 0.5) ≈ 0.417
        # 宠物头顶 y ≈ h * 0.9 / (1 + 0.9 + 0.5) * h ≈ h * 0.375
        # 思考内容放在头顶再往上一点
        cy = h * 0.32

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(alpha_scale)

        content = self._get_current_content()
        size = min(w, h) * 0.18  # 图标大小

        if content == "bulb":
            # 💡 灯泡 + 外发光
            # 发光
            glow = QRadialGradient(cx, cy, size * 1.8)
            glow.setColorAt(0, QColor(255, 230, 80, 180))
            glow.setColorAt(0.5, QColor(255, 180, 0, 80))
            glow.setColorAt(1, QColor(255, 150, 0, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), size * 1.8, size * 1.8)
            # 灯泡本体
            bulb_r = size * 0.55
            gradient = QRadialGradient(cx - bulb_r * 0.3, cy - bulb_r * 0.3, bulb_r)
            gradient.setColorAt(0, QColor(255, 250, 150, 255))
            gradient.setColorAt(1, QColor(255, 180, 20, 255))
            painter.setBrush(QBrush(gradient))
            painter.setPen(QPen(QColor(220, 150, 0, 255), 2.5))
            painter.drawEllipse(QPointF(cx, cy), bulb_r, bulb_r)
            # 高光
            painter.setBrush(QBrush(QColor(255, 255, 220, 255)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx - bulb_r * 0.25, cy - bulb_r * 0.3),
                              bulb_r * 0.25, bulb_r * 0.2)
            # 灯座
            painter.setBrush(QBrush(QColor(150, 150, 150, 255)))
            painter.setPen(QPen(QColor(100, 100, 100, 255), 2))
            painter.drawRoundedRect(QRectF(cx - bulb_r * 0.35, cy + bulb_r * 0.7,
                                          bulb_r * 0.7, bulb_r * 0.35), 4, 4)
            # 螺纹
            pen = QPen(QColor(90, 90, 90, 255), 1.5)
            painter.setPen(pen)
            for i in range(2):
                ly = cy + bulb_r * 0.82 + i * bulb_r * 0.12
                painter.drawLine(QPointF(cx - bulb_r * 0.3, ly),
                               QPointF(cx + bulb_r * 0.3, ly))

        elif content == "question":
            # ❓ 问号 + 外发光
            glow = QRadialGradient(cx, cy, size * 1.5)
            glow.setColorAt(0, QColor(255, 200, 50, 120))
            glow.setColorAt(1, QColor(255, 150, 0, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), size * 1.5, size * 1.5)
            # 问号
            font = QFont()
            font.setBold(True)
            font.setPixelSize(int(size * 1.4))
            painter.setFont(font)
            painter.setPen(QColor(60, 60, 60, 255))
            painter.drawText(QRectF(cx - size, cy - size, size * 2, size * 2),
                           Qt.AlignCenter, "?")

        elif content == "exclamation":
            # ❗ 感叹号 + 红色发光
            glow = QRadialGradient(cx, cy, size * 1.5)
            glow.setColorAt(0, QColor(255, 80, 80, 150))
            glow.setColorAt(1, QColor(255, 0, 0, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), size * 1.5, size * 1.5)
            # 感叹号
            font = QFont()
            font.setBold(True)
            font.setPixelSize(int(size * 1.5))
            painter.setFont(font)
            painter.setPen(QColor(230, 30, 30, 255))
            painter.drawText(QRectF(cx - size, cy - size, size * 2, size * 2),
                           Qt.AlignCenter, "!")

        elif content == "ellipsis":
            # …… 省略号（三个点跳动）
            phase_t = (self.t * 2.0) % 1.0
            dot_r = size * 0.18
            spacing = size * 0.5
            for i in range(3):
                offset = math.sin(phase_t * math.pi * 2 - i * 0.8) * dot_r * 1.0
                dx = cx + (i - 1) * spacing
                dy = cy - offset
                # 发光
                dg = QRadialGradient(dx, dy, dot_r * 2.5)
                dg.setColorAt(0, QColor(100, 100, 100, 120))
                dg.setColorAt(1, QColor(80, 80, 80, 0))
                painter.setBrush(QBrush(dg))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(dx, dy), dot_r * 2.5, dot_r * 2.5)
                # 点
                painter.setBrush(QBrush(QColor(80, 80, 80, 255)))
                painter.drawEllipse(QPointF(dx, dy), dot_r, dot_r)

        elif content == "zzz":
            # 💤 Zzz（三个从小到大漂浮的 Z）
            font = QFont()
            font.setBold(True)
            painter.setPen(QColor(80, 130, 220, 255))
            # 小 Z（左下）
            font.setPixelSize(int(size * 0.5))
            painter.setFont(font)
            painter.drawText(QRectF(cx - size * 0.9, cy - size * 0.2, size * 0.5, size * 0.5),
                           Qt.AlignCenter, "z")
            # 中 Z（中间偏上）
            font.setPixelSize(int(size * 0.75))
            painter.setFont(font)
            painter.drawText(QRectF(cx - size * 0.3, cy - size * 0.6, size * 0.6, size * 0.6),
                           Qt.AlignCenter, "Z")
            # 大 Z（右上）
            font.setPixelSize(int(size * 1.0))
            painter.setFont(font)
            painter.drawText(QRectF(cx + size * 0.3, cy - size * 1.0, size * 0.7, size * 0.7),
                           Qt.AlignCenter, "Z")
            # Z 的发光
            glow = QRadialGradient(cx + size * 0.4, cy - size * 0.5, size * 1.3)
            glow.setColorAt(0, QColor(100, 160, 255, 80))
            glow.setColorAt(1, QColor(80, 120, 200, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx + size * 0.4, cy - size * 0.5), size * 1.3, size * 1.3)

        painter.restore()


# ============================================================
# 特效目录
# ============================================================

EFFECTS = {
    "none": {"name": "无", "class": None},
    "fire": {"name": "🔥 火焰光环", "class": FireAuraEffect},
    "lightning": {"name": "⚡ 闪电环绕", "class": LightningEffect},
    "dark_aura": {"name": "🌑 暗黑魔气", "class": DarkAuraEffect},
    "star": {"name": "✨ 星光环绕", "class": StarEffect},
    "rainbow": {"name": "🌈 彩虹光环", "class": RainbowAuraEffect},
    "sakura": {"name": "🌸 樱花飘落", "class": SakuraEffect},
    "ice": {"name": "❄️ 冰雪气场", "class": IceEffect},
    "magic_circle": {"name": "🔮 魔法阵", "class": MagicCircleEffect},
    "water": {"name": "💧 水之波动", "class": WaterWaveEffect},
    "heart": {"name": "💖 爱心气泡", "class": HeartBubbleEffect},
    "coin_rain": {"name": "🪙 金币雨", "class": CoinRainEffect},
    "think": {"name": "💭 思考气泡", "class": ThinkBubbleEffect},
}


# ============================================================
# 特效叠加窗口
# ============================================================

class EffectOverlay(QWidget):
    """特效叠加层：独立透明窗口，始终跟随宠物，绘制在宠物上方。"""

    def __init__(self, pet_widget):
        super().__init__(None)
        self._pet = pet_widget
        self._effect = None
        self._effect_name = "none"

        # 窗口属性：无边框、透明、置顶、鼠标穿透
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        # 扩展尺寸（上方多扩展，给头顶特效留出空间）
        self._expand_top = 0.9
        self._expand_sides = 0.5
        self._expand_bottom = 0.5
        self._update_size_and_pos()

        # 动画定时器（60fps）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._last_time = None

    def set_effect(self, name: str):
        """切换特效。name 为 EFFECTS 中的 key。"""
        if name == self._effect_name and self._effect is not None:
            return
        self._effect_name = name
        effect_info = EFFECTS.get(name)
        if effect_info and effect_info["class"]:
            self._effect = effect_info["class"]()
            if not self._timer.isActive():
                self._timer.start(16)  # ~60fps
                self._last_time = None
            self.show()
        else:
            self._effect = None
            self._timer.stop()
            self.hide()
        self.update()

    def _on_tick(self):
        if self._effect is None:
            return
        import time
        now = time.time()
        if self._last_time is None:
            dt = 0.016
        else:
            dt = min(0.1, now - self._last_time)
        self._last_time = now
        self._effect.tick(dt)
        self._sync_position()
        self.update()

    def _update_size_and_pos(self):
        pw = self._pet.width()
        ph = self._pet.height()
        w = int(pw * (1 + self._expand_sides * 2))
        h = int(ph * (1 + self._expand_top + self._expand_bottom))
        self.setFixedSize(w, h)

    def _sync_position(self):
        """同步到宠物位置，顶部对齐宠物上方扩展更多。"""
        pw = self._pet.width()
        ph = self._pet.height()
        dx = int(pw * self._expand_sides)
        dy = int(ph * self._expand_top)
        px = self._pet.x()
        py = self._pet.y()
        self.move(px - dx, py - dy)

    def follow_pet(self):
        """宠物移动后调用，同步位置和尺寸。"""
        self._update_size_and_pos()
        self._sync_position()

    def set_paused(self, paused: bool):
        """暂停/恢复绘制（用于对话气泡遮挡时隐藏特效）。"""
        self._paused = paused
        self.update()

    def paintEvent(self, event):
        if self._effect is None or getattr(self, "_paused", False):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._effect.paint(painter, self.width(), self.height())
        painter.end()
