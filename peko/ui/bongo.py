"""Bongo 模式：跟着键盘敲击左右摆爪的叠加层。

三块东西：
    BongoRenderer   解析 body.svg + bongo.svg，按状态画身体、键盘、手臂、爪子
    BongoController 按键状态机：按下立即落爪、松开立即抬起，过滤长按自动重复
    BongoOverlay    透明置顶叠加窗口，贴在宠物身上

键盘是 60% 布局的 61 个键，**每个键都有 id**，按哪个哪个就亮、爪子就挪过去。
两个素材都由脚本生成，别手改 SVG：
    python scripts/gen_bongo_cat.py         # body.svg
    python scripts/gen_bongo_keyboard.py    # bongo.svg

单独看效果：python -m peko.ui.bongo
"""
from __future__ import annotations

import os
import sys
import time
from typing import Dict, Iterable, Optional

from PyQt5.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget

try:
    from ..core.bongo_keys import (
        KEY_CAPS,
        cap_for,
        cap_for_pynput,
        side_for,
        side_for_pynput,
    )
except ImportError:
    # 直接 python peko/ui/bongo.py 跑时没有包上下文，补上项目根再绝对导入
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from peko.core.bongo_keys import (
        KEY_CAPS,
        cap_for,
        cap_for_pynput,
        side_for,
        side_for_pynput,
    )

# SVG 的 viewBox 与窗口坐标一致，改动这里要同步改 bongo.svg / body.svg
# 420x280 装 60% 键盘（15u，1u=22px）：键帽 20.5 宽、字母 10px，字符清楚。
# 身体铺满整个画布（坐标写死在 body.svg 里），下半截由键盘盖掉。
RENDER_W, RENDER_H = 420, 280

# 按住超过这个秒数还没收到 release，就当作 release 丢了
_STUCK_KEY_SEC = 5.0

_RES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "pets", "BB", "resource", "bongo",
)
_DEFAULT_SVG = os.path.join(_RES_DIR, "bongo.svg")
_DEFAULT_BODY = os.path.join(_RES_DIR, "body.svg")


class BongoRenderer:
    """把 bongo.svg 拆成「键盘」「两只爪子」，外加 body.svg 那只鼠。

    坑：QSvgRenderer.render(painter, elementId) 会把元素拉伸到整个 viewport，
    必须传 boundsOnElement 的目标矩形，否则键盘会被放大成整屏黑块。

    键盘是**宠物视角**：正对着鼠摆，等比于整块键盘绕中心旋转 180°——画面上
    Q 区在右、Enter 在左、数字行在最下面、键帽上的字也是倒的。于是画面右爪
    = 宠物左手，PET_TO_SCREEN 必须是对调映射；写成同侧会按 Q 动错手。
    别因为"看着别扭"就把它翻正，用户要的就是这个倒着的效果。
    """

    DESK = "desk"
    PAWS = {
        ("l", False): "paw_l_rest",
        ("l", True): "paw_l_down",
        ("r", False): "paw_r_rest",
        ("r", True): "paw_r_down",
    }
    # 键盘转 180° 后画面是左右反的 → 宠物左手在画面右边。
    # 所以这里是**对调**映射：left 走画面右爪 r，right 走画面左爪 l。
    PET_TO_SCREEN = {"left": "r", "right": "l"}
    # 按下的键帽不另画一套 SVG，直接用这个颜色盖一层圆角矩形，换肤只改这里。
    # 别用白色（和键帽同形同调，看着像掉了个键），也别用肉垫那个 #F0A0A0。
    HIGHLIGHT = "#FFC94D"

    # 手臂根部写死在身体两侧，不跟着爪子跑。
    # 之前是夹取爪子的 x，手一动臂根就在身上来回蹭，看着像皮肤底下有虫子爬。
    # 固定在 y=164（键盘上沿），正好是身体露出键盘的那条边，像从肩膀长出来。
    # x 对齐两只手的休息位（194/260），静止时手臂是垂直的，最自然；
    # 真要按边的键再斜出去。y 压在键盘上沿 164，臂根圆头有一半缩进键盘，
    # 像从键盘后面伸手出来。
    SHOULDERS = {"l": QPointF(194.0, 164.0), "r": QPointF(260.0, 164.0)}
    # 爪子直径 22，手臂 11：比爪子细一档，看着才像手而不是两根香肠
    ARM_W = 11.0
    ARM_FILL = "#C9C9C9"
    ARM_EDGE = "#1A1A1A"

    def __init__(self, svg_path: str = _DEFAULT_SVG, body_path: str = _DEFAULT_BODY):
        from PyQt5.QtSvg import QSvgRenderer

        self._renderer = QSvgRenderer(svg_path)
        # 身体单独一个文件：绘制顺序是 身体 → 键盘 → 手臂 → 爪子，
        # 塞进同一个 SVG 就没法把键盘插在中间了。
        self._body = QSvgRenderer(body_path)
        self.valid = self._renderer.isValid()
        self._highlight = QColor(self.HIGHLIGHT)
        self._bounds = {}
        if not self.valid:
            return
        # 键帽 id 统一是 "k" + 键名（kq / ka / kspace），下面直接用得上
        for eid in [self.DESK, *self.PAWS.values(), *(f"k{c}" for c in KEY_CAPS)]:
            rect = self._renderer.boundsOnElement(eid)
            if not rect.isNull():
                self._bounds[eid] = rect

    def paint_desk(self, painter: QPainter, caps: Iterable[str] = ()) -> None:
        """键盘画在 body 之前（后面），按下的键帽再盖一层高亮。"""
        if not self.valid:
            return
        self._renderer.render(painter, self.DESK, self._bounds[self.DESK])

        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._highlight)
        for cap in caps:
            rect = self._bounds.get(f"k{cap}")
            if rect is not None:
                painter.drawRoundedRect(rect.adjusted(0.4, 0.4, -0.4, -0.4), 2, 2)
        painter.restore()

    def rest_center(self, screen_side: str) -> QPointF:
        """爪子没按任何可映射键时停的位置（SVG 里的原坐标）。"""
        return QPointF(self._bounds[self.PAWS[(screen_side, False)]].center())

    def cap_center(self, cap: Optional[str]) -> Optional[QPointF]:
        """键帽中心，爪子要挪到这里。没画这个键就返回 None。"""
        if not cap:
            return None
        rect = self._bounds.get(f"k{cap}")
        return QPointF(rect.center()) if rect is not None else None

    def paint_body(self, painter: QPainter) -> None:
        """整只鼠，坐标写死在 body.svg 里，这里不做缩放。"""
        if self._body.isValid():
            self._body.render(painter)

    def body_rect(self) -> QRectF:
        """body.svg 铺满整块画布，留着给外部算命中区域用。"""
        return QRectF(0.0, 0.0, RENDER_W, RENDER_H)

    def paint_arms(self, painter: QPainter, centers: Dict[str, QPointF]) -> None:
        """从肩膀拉一条手臂到爪子，爪子在哪手臂就伸到哪。

        画在 body 之后、键盘之前：手臂压在键盘上，爪子再盖在手臂末端。
        先统一描一遍粗黑边、再统一填灰色，别一手黑边一手灰——
        两只手臂交叉时后画的黑边会啃掉前一只的肉。
        """
        if not centers:
            return
        paths = []
        for side in ("l", "r"):
            end = centers.get(side)
            if end is None:
                continue
            # 复制一份：SHOULDERS 是类属性，直接拿去 quadTo 会被就地改掉
            start = QPointF(self.SHOULDERS[side])
            # 控制点往外鼓一点、按横向距离下压：去够数字行那种同高的键时，
            # 手臂本来是根笔直的水平棍，往下鼓出一道弧才像「伸手」。
            # 下压封顶 30，否则按最边上的键会弯成一张弓。
            dx = end.x() - start.x()
            # 往外鼓看肩在画布哪半边，别按 side 名字判断：
            # 键盘转 180° 后 l/r 在画面上是反的，写死会让手臂朝里拐。
            out = -1.0 if start.x() < RENDER_W / 2.0 else 1.0
            mid = QPointF(
                (start.x() + end.x()) / 2.0 + out * 5.0,
                (start.y() + end.y()) / 2.0 + min(abs(dx) * 0.16 + 6.0, 30.0),
            )
            path = QPainterPath(start)
            path.quadTo(mid, end)
            paths.append(path)

        painter.save()
        painter.setBrush(Qt.NoBrush)
        for width, color in ((self.ARM_W + 4.0, self.ARM_EDGE), (self.ARM_W, self.ARM_FILL)):
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            for path in paths:
                painter.drawPath(path)
        painter.restore()

    def paint_paws(
        self,
        painter: QPainter,
        left_down: bool,
        right_down: bool,
        centers: Optional[Dict[str, QPointF]] = None,
    ) -> None:
        """爪子画在 body 之后（前面）。

        centers 是画面左右爪当前的中心点，由 PawMotion 逐帧给出；不给就
        停在 SVG 原位。平移只改 render 的目标矩形，爪子本身不缩放。
        """
        if not self.valid:
            return
        for pet_side, down in (("left", left_down), ("right", right_down)):
            screen = self.PET_TO_SCREEN[pet_side]
            eid = self.PAWS[(screen, down)]
            rect = QRectF(self._bounds[eid])
            center = (centers or {}).get(screen)
            if center is not None:
                rect.translate(center.x() - rect.center().x(), center.y() - rect.center().y())
            self._renderer.render(painter, eid, rect)


class PawMotion(QObject):
    """让两只爪子平滑挪到「该手最近按下的那个键」上。

    SVG 里的爪子只是模板 + 休息位，这里只维护目标中心点，真正的平移在
    绘制时做——所以加按键位置不会多出任何图元，也不会多一次 SVG 解析。

    按下就出发，松手留在原地（下一个键再走），只有按到键盘上没画的键
    （数字、回车…）才飘回休息位。
    """

    changed = pyqtSignal()
    FRAME_MS = 16
    EASE = 0.4     # 每帧朝目标走 40%，60fps 下约 80ms 到位
    SNAP = 0.6     # 差这么点就直接吸附，免得尾巴抖
    # 两只手按到相邻键（g 和 h）时目标会重合，爪子挤成一坨。
    # 这个距离内就把目标互相推开——推的是目标不是当前位置，否则每帧
    # 一边朝键走一边被推开，爪子会原地抽搐。
    MIN_GAP = 28.0
    # 爪子比键帽宽（直径 22 vs 20.5），落在键帽正中会把高亮整个盖掉。
    # 往上提一点，让它只压住上沿，下半截还看得见是哪个键亮着。
    Y_OFFSET = -8.0

    def __init__(self, renderer: BongoRenderer, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._renderer = renderer
        self._cur: Dict[str, QPointF] = {}
        # _base 是「该手想按的那个键」，_tgt 是避让之后真正要去的位置。
        # 必须分开存：直接在 _tgt 上推的话，推开是永久的，后来两只手
        # 离得再远也回不到键上，越按越偏。
        self._base: Dict[str, QPointF] = {}
        self._tgt: Dict[str, QPointF] = {}
        # 这只手这一轮到底有没有按在键上。避让时要靠它区分
        # 「两只手抢相邻键」和「一只手按键、另一只手闲着」。
        self._has_goal = {"l": False, "r": False}
        for side in ("l", "r"):
            rest = renderer.rest_center(side)
            self._cur[side] = QPointF(rest)
            self._base[side] = QPointF(rest)
            self._tgt[side] = QPointF(rest)
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)

    def centers(self) -> Dict[str, QPointF]:
        return {side: QPointF(pt) for side, pt in self._cur.items()}

    def set_targets(self, left_cap: Optional[str] = None, right_cap: Optional[str] = None) -> None:
        """left_cap / right_cap 是宠物左/右手最近按下的键帽。

        None 表示这只手没按到键盘上画着的键（空格以外的数字、回车…），
        那就让它停在原地——松手就弹回休息位的话，打字时爪子会在中间
        来回甩，反而看不出是按哪儿。
        """
        for pet_side, cap in (("left", left_cap), ("right", right_cap)):
            screen = self._renderer.PET_TO_SCREEN[pet_side]
            center = self._renderer.cap_center(cap)
            if center is None:
                self._has_goal[screen] = False
                continue
            center.setY(center.y() + self.Y_OFFSET)
            self._base[screen] = QPointF(center)
            self._has_goal[screen] = True
        for side in ("l", "r"):
            self._tgt[side] = QPointF(self._base[side])
        self._separate_targets()
        if self._timer.isActive():
            return
        if any(not self._near(self._cur[s], self._tgt[s]) for s in ("l", "r")):
            self._timer.start()

    def _separate_targets(self) -> None:
        """两爪挨太近就分开，保证能看出是两只手。

        分开的时候要看是谁挡着谁：只有一只手按在键上、另一只还停在休息位
        时，让**闲着的那只**挪开。平均分摊的话，正在按 p 的爪子会被推离
        键帽十几个像素，明明按的是 p 看着却像按在 p 和 o 中间。
        """
        left, right = self._tgt["l"], self._tgt["r"]
        gap = right.x() - left.x()
        if gap >= self.MIN_GAP:
            return
        lg, rg = self._has_goal["l"], self._has_goal["r"]
        if lg and not rg:
            right.setX(left.x() + self.MIN_GAP)
            return
        if rg and not lg:
            left.setX(right.x() - self.MIN_GAP)
            return
        push = (self.MIN_GAP - gap) / 2.0
        left.setX(left.x() - push)
        right.setX(right.x() + push)

    def _near(self, a: QPointF, b: QPointF) -> bool:
        return abs(a.x() - b.x()) <= self.SNAP and abs(a.y() - b.y()) <= self.SNAP

    def _tick(self) -> None:
        moving = False
        for side in ("l", "r"):
            cur, tgt = self._cur[side], self._tgt[side]
            if self._near(cur, tgt):
                if cur != tgt:
                    self._cur[side] = QPointF(tgt)
                    moving = True
                continue
            cur.setX(cur.x() + (tgt.x() - cur.x()) * self.EASE)
            cur.setY(cur.y() + (tgt.y() - cur.y()) * self.EASE)
            moving = True
        if moving:
            self.changed.emit()
        else:
            self._timer.stop()


class BongoController(QObject):
    """按键状态机。

    - 同一只手可能同时按着多个键（如 A+S），只有全部松开才回落
    - 长按会持续收到 press，用下按集合去重，避免爪子疯狂抖动
    - 按下即落、松开即抬，不做任何延迟

    这里**不要**加「松开后延迟 N 毫秒再回落」：快速连打时，松开启动的
    定时器会被下一次 press 停掉，而落下状态仍是 True，既不 emit 也不
    回落，爪子就卡住不动了——按键越快越像没反应。
    """

    state_changed = pyqtSignal(bool, bool)  # left_down, right_down
    caps_changed = pyqtSignal(object)       # frozenset[str] 亮着的键帽

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._held: Dict[object, str] = {}
        self._held_since: Dict[object, float] = {}
        self._caps: Dict[object, str] = {}
        self._caps_snapshot = frozenset()
        self._down = {"left": False, "right": False}
        self._last_side = "right"

    @property
    def state(self):
        return self._down["left"], self._down["right"]

    @property
    def caps(self) -> frozenset:
        """当前亮着的键帽（每个物理键各算一个，重复的只留一个）。"""
        return self._caps_snapshot

    def cap_of(self, side: str) -> Optional[str]:
        """这只手最近按下的键帽，用来把爪子挪过去；没有就 None。

        同手多键时（A+S 一起按着）取最后按下的那个，松手后自动退回另一个。
        """
        best: Optional[str] = None
        best_at = -1.0
        for key_id, cap in self._caps.items():
            if self._held.get(key_id) != side:
                continue
            at = self._held_since.get(key_id, 0.0)
            if at >= best_at:
                best_at, best = at, cap
        return best

    def _resolve(self, hint: Optional[str]) -> Optional[str]:
        if hint in ("left", "right"):
            self._last_side = hint
            return hint
        if hint == "alt":
            # 空格 / 中文输入没有物理位置，左右交替，别让一只手一直敲
            side = "left" if self._last_side == "right" else "right"
            self._last_side = side
            return side
        return None

    def _emit(self) -> None:
        self.state_changed.emit(self._down["left"], self._down["right"])

    def _emit_caps(self) -> None:
        snapshot = frozenset(self._caps.values())
        if snapshot != self._caps_snapshot:
            self._caps_snapshot = snapshot
            self.caps_changed.emit(snapshot)

    def _release(self, side: str) -> None:
        if self._down[side]:
            self._down[side] = False
            self._emit()

    def _forget(self, key_id: object) -> None:
        self._held.pop(key_id, None)
        self._held_since.pop(key_id, None)
        self._caps.pop(key_id, None)

    def _press(self, key_id: object, side_hint: Optional[str], cap: Optional[str]) -> None:
        since = self._held_since.get(key_id)
        if since is not None:
            if time.monotonic() - since < _STUCK_KEY_SEC:
                return  # 长按的自动重复，忽略
            # 按住超过 5 秒还没收到 release，多半是切窗口 / Alt+Tab 把
            # release 事件弄丢了，按新的按下处理，别让爪子永久卡住
            self._forget(key_id)

        side = self._resolve(side_hint)
        if side is None:
            return
        self._held[key_id] = side
        self._held_since[key_id] = time.monotonic()
        if cap:
            self._caps[key_id] = cap
        if not self._down[side]:
            self._down[side] = True
            self._emit()
        self._emit_caps()

    def _release_key(self, key_id: object) -> None:
        side = self._held.pop(key_id, None)
        if side is None:
            return
        self._held_since.pop(key_id, None)
        self._caps.pop(key_id, None)
        self._emit_caps()
        # 这只手还有别的键按着就先不抬
        if not any(s == side for s in self._held.values()):
            self._release(side)

    def key_event(
        self,
        key_id: object,
        pressed: bool,
        side_hint: Optional[str] = None,
        cap: Optional[str] = None,
    ) -> None:
        """cap 是这次按键在键盘上对应的键帽 id（见 bongo_keys.KEY_CAPS），没有就不亮。"""
        if pressed:
            self._press(key_id, side_hint, cap)
        else:
            self._release_key(key_id)

    @pyqtSlot(str, bool, str, str)
    def on_key(self, key_id: str, pressed: bool, side_hint: str, cap: str) -> None:
        """跨线程入口：pynput 线程只能通过 queued invoke 进来。"""
        self.key_event(key_id, pressed, side_hint or None, cap or None)


class BongoOverlay(QWidget):
    """贴在宠物身上的透明叠加层：身体 + 键盘 + 爪子。

    注意：身体现在由这一层画（body.svg），接入时要把宠物本体的 lieDown
    帧藏起来，否则同一个人会有两个身子。
    """

    def __init__(self, pet, svg_path: str = _DEFAULT_SVG):
        super().__init__(None)
        self._pet = pet
        self._renderer = BongoRenderer(svg_path)
        self.motion = PawMotion(self._renderer, self)
        self.motion.changed.connect(self.update)
        self._left = False
        self._right = False
        self._caps = frozenset()

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._sync_geometry()

    def _sync_geometry(self) -> None:
        """画布比宠物窗口大，贴不住原地。

        对齐方式：键盘底边贴着宠物底边，画布中心对准宠物中心——
        键盘本来就是铺在桌面上伸向观众，不会跟着宠物一起缩小。
        """
        if self._pet is None:
            return
        self.setFixedSize(RENDER_W, RENDER_H)
        self.move(
            self._pet.x() + self._pet.width() // 2 - RENDER_W // 2,
            self._pet.y() + self._pet.height() - RENDER_H,
        )

    def follow_pet(self) -> None:
        self._sync_geometry()

    def set_state(
        self,
        left_down: bool,
        right_down: bool,
        caps: Iterable[str] = (),
        left_cap: Optional[str] = None,
        right_cap: Optional[str] = None,
    ) -> None:
        """left_cap / right_cap 传 BongoController.cap_of 的结果，爪子会挪到那个键。"""
        caps = frozenset(caps)
        if (left_down, right_down) == (self._left, self._right) and caps == self._caps:
            self.motion.set_targets(left_cap, right_cap)
            return
        self._left, self._right = left_down, right_down
        self._caps = caps
        self.motion.set_targets(left_cap, right_cap)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setWindow(0, 0, RENDER_W, RENDER_H)
        centers = self.motion.centers()
        self._renderer.paint_body(painter)
        self._renderer.paint_desk(painter, self._caps)
        self._renderer.paint_arms(painter, centers)
        self._renderer.paint_paws(painter, self._left, self._right, centers)
        painter.end()


# ============================================================
# 独立预览：python -m peko.ui.bongo
# ============================================================


class _BongoDemo(QWidget):
    """独立演示窗口：自己画身体 + 键盘 + 爪子，接真实键盘。"""

    def __init__(self, pet_dir: str, scale: int = 2):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._scale = scale
        self.setFixedSize(RENDER_W * scale, RENDER_H * scale)

        res = os.path.join(pet_dir, "resource", "bongo")
        self._renderer = BongoRenderer(
            os.path.join(res, "bongo.svg"), os.path.join(res, "body.svg")
        )

        self._drag_origin = None
        self._caps = frozenset()
        self.motion = PawMotion(self._renderer, self)
        self.motion.changed.connect(self.update)
        self.controller = BongoController()
        self.controller.state_changed.connect(self._on_state)
        self.controller.caps_changed.connect(self._on_caps)

        screen = QApplication.desktop().screenGeometry()
        self.move(screen.width() // 2 - self.width() // 2, screen.height() - self.height() - 80)

    def _on_state(self, left: bool, right: bool) -> None:
        self._sync_paw_targets()
        self.update()

    def _on_caps(self, caps: frozenset) -> None:
        self._caps = caps
        self._sync_paw_targets()
        self.update()

    def _sync_paw_targets(self) -> None:
        self.motion.set_targets(
            self.controller.cap_of("left"),
            self.controller.cap_of("right"),
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setWindow(0, 0, RENDER_W, RENDER_H)
        centers = self.motion.centers()
        # 顺序：身体 → 键盘 → 手臂 → 爪子。
        # 身体先画才会被键盘吃掉下半截，看上去是趴在键盘后面。
        self._renderer.paint_body(painter)
        self._renderer.paint_desk(painter, self._caps)
        self._renderer.paint_arms(painter, centers)
        self._renderer.paint_paws(
            painter, *self.controller.state, centers=centers
        )
        painter.end()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            QApplication.quit()
            return
        text = event.text()
        self.controller.key_event(
            ("qt", event.key()),
            True,
            side_for(char=text) if text else None,
            cap_for(char=text) if text else None,
        )
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if not event.isAutoRepeat():
            self.controller.key_event(("qt", event.key()), False)
        super().keyReleaseEvent(event)

    # 无边框窗口，得自己实现拖动，否则挡住桌面就挪不走了
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_origin is not None:
            self.move(event.globalPos() - self._drag_origin)


def _pynput_key_id(key) -> str:
    """press 与 release 必须得到同一个 id。

    别用 str(key)：字符键带 char，Shift+A 按下是 'A'，先松 Shift 再松 A
    时 release 拿到的是 'a'，pop 不到就永远抬不起来。虚拟键码不受修饰键影响。
    """
    vk = getattr(key, "vk", None)
    if vk is None:
        vk = getattr(getattr(key, "value", None), "vk", None)
    if vk is not None:
        return f"vk{vk}"
    # 少数来源拿不到 vk 时，字符也统一取小写，别让大小写把一次按键拆成两次
    char = getattr(key, "char", None)
    if char:
        return f"ch{char.lower()}"
    name = getattr(key, "name", None)
    return f"k{name}" if name else str(key)


def _start_key_listener(ctrl: BongoController) -> str:
    """接管全局键盘，返回实际用的后端名。

    pynput 是首选（跨平台），没装或没权限时退回 keyboard 库——和 main.py
    里 L+Enter 的降级顺序保持一致，别让没装 pynput 的机器直接看不到效果。
    """
    from PyQt5.QtCore import Q_ARG, QMetaObject

    def dispatch(key_id: str, pressed: bool, hint: Optional[str], cap: Optional[str]) -> None:
        # 后台线程不能直接碰 QTimer，统一排队回主线程
        QMetaObject.invokeMethod(
            ctrl, "on_key", Qt.QueuedConnection,
            Q_ARG(str, key_id), Q_ARG(bool, pressed),
            Q_ARG(str, hint or ""), Q_ARG(str, cap or ""),
        )

    try:
        from pynput import keyboard as pynput_keyboard

        def handler(pressed: bool):
            def cb(key):
                dispatch(
                    _pynput_key_id(key), pressed,
                    side_for_pynput(key), cap_for_pynput(key),
                )

            return cb

        listener = pynput_keyboard.Listener(on_press=handler(True), on_release=handler(False))
        listener.start()
        return "pynput"
    except Exception:
        pass

    if sys.platform == "win32":
        import keyboard as kb

        def on_event(ev):
            # 用扫描码而不是键名，键名同样会受修饰键影响
            name = ev.name
            single = len(name) == 1
            dispatch(
                f"sc{ev.scan_code}", ev.event_type == "down",
                side_for(char=name) if single else side_for(name=name),
                cap_for(char=name) if single else cap_for(name=name),
            )

        kb.hook(on_event)
        return "keyboard"

    return ""


def main() -> int:
    app = QApplication(sys.argv)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pet_dir = os.path.join(root, "pets", "BB")
    demo = _BongoDemo(pet_dir)
    demo.show()

    try:
        backend = _start_key_listener(demo.controller)
        if backend:
            print(f"[bongo] 已接管全局键盘（{backend}），直接敲键盘看爪子")
        else:
            raise RuntimeError("当前平台没有可用的监听后端")
    except Exception as e:
        print(f"[bongo] 全局键盘不可用（{e}）")
        print("[bongo] 请点击窗口，用窗口内按键看效果")

    print("[bongo] 拖动窗口可挪位置，Esc 退出")
    demo.setFocus()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
