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
import random
import sys
import time
from typing import Dict, Iterable, Optional, Tuple

from PyQt5.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PyQt5.QtWidgets import QApplication, QWidget

if not __package__:
    # 直接 python peko/ui/bongo.py 跑时项目根不在 sys.path，补上再走绝对导入。
    # 统一用绝对导入（而不是 try 相对导入 + except 补 sys.path）：只有一条
    # 路径，静态检查看得懂，也不会出现「包内能跑、脚本直跑 import 失败」。
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

from peko.core.bongo_keys import (
    KEY_CAPS,
    cap_for,
    cap_for_pynput,
    side_for,
    side_for_pynput,
)
from peko.core.bongo_modes import (
    BongoMode,
    asset_path,
    get_mode,
    has_mode,
    list_modes,
    next_mode,
    set_mode,
)
from peko.ui.pet_anim import (
    BUBBLE_BANG,
    BUBBLE_SLEEP,
    EYE_BLINK,
    EYE_CLOSED,
    EYE_HALF,
    EYE_OPEN,
    EYE_WIDE,
    NEUTRAL,
    PetAnim,
    Pose,
)

# 画布尺寸已经搬进 BongoMode（canvas_w / canvas_h，默认 420x280）：
# 420x280 装 60% 键盘（15u，1u=16px），身体铺满整块画布（坐标写死在
# body.svg 里），下半截由键盘盖掉。要取当前尺寸就用 renderer.canvas_w。

# 整个画面（宠物 + 键盘）相对 420x280 画布的缩放，同时决定**窗口尺寸**
# （见 BongoOverlay._sync_geometry），不再是窗口内留白。
# 0.573 那版是「0.86 再缩 2/3」，实际只有 240x160，比桌宠本体（200x200）
# 还小一圈，趴键盘的观感全没了。0.86 出 361x241，约本体 1.8 倍宽，
# 和键盘的实际比例接近。要调就动这一个数，别去改 viewBox。
# viewBox 仍然写死 420x280：爪子落点、透视矩阵、body.svg 的坐标全建立在
# 这个坐标系上，改 viewBox 会让它们同时错位。
CONTENT_SCALE = 0.86

# 按住超过这个秒数还没收到 release，就当作 release 丢了
_STUCK_KEY_SEC = 5.0

# 默认素材目录（宠物包 BB）。素材文件名不再写死在这里，而是由模式给出
# （BongoMode.desk_svg / body_svg），这样换个键盘布局只要加模式条目。
_RES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "pets", "BB", "resource", "bongo",
)


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
    HIGHLIGHT = "#FFD166"

    # 倾斜角 / 旋转中心 / 透视收窄量全部搬到 BongoMode 里了
    # （tilt_deg、tilt_cy、persp_inset），这里只留样式常量。
    #
    # 那几个几何值不是随手抽走的：小键盘只有 4 列，画布窄、重心不在 210，
    # 转多少度、绕哪里转，全和 60% 不一样。留在类常量上的话
    # 「加一个模式」就得回来改绘制代码，模式层就白做了。
    #
    # 手臂整体砍掉了：60% 键盘只有 252 宽却要够到最左的 Backspace 和最右
    # 的 Enter，两条灰杆斜穿整块键盘；40% / 钢琴更窄，问题一样。爪子直接
    # 浮在键帽 / 垫子上，靠接触阴影贴住，比拉两条长杆耐看。

    # ---- 表情 ----
    # 眼睛是**按 body.svg 的 bbox 比例**给的，不是死像素：body 元素在
    # viewBox 里被 translate+scale 包了一层，渲染出来的实际范围只有
    # 141,78~278,243（137x165），跟 420x280 的画布差着三倍。写绝对坐标
    # 的后果是换一份素材就全歪。这四组数是渲染成位图后扫黑色连通块量出来的。
    # 注意：这四组数必须量在**未倾斜**的身体位图上。身体整体有 8° 的公共倾斜，
    # 拿倾斜之后的位置反算比例，画出来的眼会整体偏 13px（实测踩过）。
    EYE_BOXES = (
        (0.3396, 0.2607, 0.1022, 0.1333),   # 左眼 x/y/w/h，相对 body bbox
        (0.5950, 0.2607, 0.1022, 0.1272),   # 右眼
    )
    FACE_GRAY = "#cac8c8"   # 抹掉原眼珠用的脸灰（实测 px 取样）
    INK = "#0d0d0d"
    PAPER = "#f1f1f1"
    PAW_PINK = "#F0A0A0"    # 爪子那颗粉（body.svg 肉垫同色）
    # 气泡钉在头的右上外侧，同样按画布比例给
    BUBBLE_POS = (0.685, 0.275)
    BUBBLE_R = (30.0, 22.0)

    def frame_transform(self, painter: QPainter) -> None:
        """每帧绘制的统一入口：抗锯齿 + viewBox + 整体缩放。

        放在这里而不是各个 paintEvent 自己拼——真身和预览两个绘制入口都得
        用同一套，漏一处就会出现「预览正常、实机顶满窗口」。

        viewBox 取模式里的画布尺寸而不是模块常量：换个布局（小键盘）画布
        比例会变，窗口那边也是按 renderer.canvas_* 算尺寸的。
        """
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setWindow(0, 0, int(self.canvas_w), int(self.canvas_h))

    def __init__(
        self,
        svg_path: Optional[str] = None,
        body_path: Optional[str] = None,
        mode: Optional[BongoMode] = None,
    ):
        """素材路径不给就按模式解析；mode 不给取用户当前选中的那一种。

        显式传 svg_path / body_path 仍可用（老调用点和单测都靠它指定素材），
        这时其余行为字段（mouse_hand 之类）来自模式。
        """
        from PyQt5.QtSvg import QSvgRenderer

        self.mode = mode or get_mode()
        # 有鼠标手的造型：这只手不走按键逻辑，跟着真光标在垫子上滑。
        # 变量先按模式赋值，素材里没有 paw_mouse 时会关掉（见 bounds 收集之后）。
        self.mouse_hand = self.mode.mouse_hand
        # 几何全部从模式取，renderer 不自带任何布局假设。
        # 60% 键盘和小键盘的画布比例、旋转中心都不一样，
        # 写死在这里的话「加一个模式」就得改绘制代码。
        self.canvas_w = float(self.mode.canvas_w)
        self.canvas_h = float(self.mode.canvas_h)
        self.tilt_deg = float(self.mode.tilt_deg)
        self.tilt_cy = float(self.mode.tilt_cy)
        self.persp_inset = float(self.mode.persp_inset)
        # 整个宠物上下挪多少：键鼠造型要把它抬到桌沿上，只露上半身。
        self.body_dy = float(getattr(self.mode, "body_dy", 0.0))
        self.body_scale = float(getattr(self.mode, "body_scale", 1.0))
        svg_path = svg_path or os.path.join(_RES_DIR, self.mode.desk_svg)
        body_path = body_path or os.path.join(_RES_DIR, self.mode.body_svg)

        self._renderer = QSvgRenderer(svg_path)
        # 身体单独一个文件：绘制顺序是 身体 → 键盘 → 爪子，
        # 塞进同一个 SVG 就没法把键盘插在中间了。
        self._body = QSvgRenderer(body_path)
        self.valid = self._renderer.isValid()
        self._highlight = QColor(self.HIGHLIGHT)
        # 表情姿态：宿主每帧 set_pose 进来，默认中立（不歪、不呼吸）
        self._pose: Pose = NEUTRAL
        self._bounds = {}
        if not self.valid:
            return
        # 键帽 id 统一是 "k" + 键名（kq / ka / kspace），下面直接用得上。
        # 键名表按模式取：钢琴的琴键是 w0/b3，和 QWERTY 那套没有交集。
        cap_ids = tuple(getattr(self.mode, "caps", ()) or ()) or KEY_CAPS
        extra = ["table", "pad", "mouse", "mouse_l", "mouse_r", "paw_mouse", "kb_shadow"]
        for eid in [self.DESK, *self.PAWS.values(), *extra,
                    *(f"k{c}" for c in cap_ids), *(f"h{c}" for c in cap_ids)]:
            # 必须先 elementExists：boundsOnElement 对**不存在**的 id 不返回空
            # 矩形，而是把整幅文档的 bbox 给你。40% 这套键盘没有数字行和
            # Backspace，照单全收的话它们各自拿到一个「画布左下角」的假位置，
            # 按 1 或退格时爪子就飞去桌布上一个根本不存在的键上。
            if not self._renderer.elementExists(eid):
                continue
            rect = self._renderer.boundsOnElement(eid)
            if not rect.isNull():
                self._bounds[eid] = rect
        # 素材里没画鼠标（60% 那套）就别装成有鼠标手，否则那只爪子会消失
        if self.mouse_hand and "paw_mouse" not in self._bounds:
            self.mouse_hand = ""

    def _tilt(self) -> QTransform:
        """键盘和身体的公共倾斜变换：绕 (画布中线, TILT_CY) 转 TILT_DEG。

        键盘、身体、手臂根部、爪子落点全走这同一个变换，位置关系才不会错开。
        单独返回 QTransform（而不是只在 painter 上转）是因为爪子落点要拿去当
        运动目标，得能对**点**做映射。
        """
        t = QTransform()
        cx = self.canvas_w / 2.0
        t.translate(cx, self.tilt_cy)
        t.rotate(self.tilt_deg)
        t.translate(-cx, -self.tilt_cy)
        return t

    def _persp(self) -> QTransform:
        """把外壳矩形映射成梯形：上边左右各收 PERSP_INSET，下边不动。

        缩放是**透视**不是垂直拉伸——用 quadToQuad 而不是 scale，键帽才会
        越往远处越窄，靠近自己的一排仍然是原宽。
        """
        shell = self._bounds[self.DESK]
        if shell.isNull():
            return QTransform()
        inset = self.persp_inset
        src = QPolygonF([
            shell.topLeft(), shell.topRight(), shell.bottomRight(), shell.bottomLeft(),
        ])
        dst = QPolygonF([
            QPointF(shell.left() + inset, shell.top()),
            QPointF(shell.right() - inset, shell.top()),
            QPointF(shell.right(), shell.bottom()),
            QPointF(shell.left(), shell.bottom()),
        ])
        t = QTransform()
        QTransform.quadToQuad(src, dst, t)
        return t

    def _desk_matrix(self) -> QTransform:
        """键盘的完整变换：先透视、再旋转。

        Qt 的行向量约定下 A * B 表示「先 A 后 B」，所以 persp 写在左边。
        顺序反了会变成「先转再压扁上边」，梯形会跟着歪，键帽和爪子一起错位。
        """
        return self._persp() * self._tilt()

    def _tilted(self, painter: QPainter) -> None:
        """只旋转，给身体用（身体不参与键盘的透视）。"""
        cx = self.canvas_w / 2.0
        painter.translate(cx, self.tilt_cy)
        painter.rotate(self.tilt_deg)
        painter.translate(-cx, -self.tilt_cy)

    def paint_desk(self, painter: QPainter, caps: Iterable[str] = ()) -> None:
        """键盘 / 琴键画在 body 之后、手臂之前，按下的键帽再盖一层高亮。

        整块道具绕公共中心倾斜 8°，四个角转出去之后仍然要落在画布内，
        所以每份素材各自把外壳摆进画布：60% 键盘在 SVG 里整体上抬了 22
        （见 gen_bongo_keyboard.py 的 KB_LIFT），琴键则从桌沿往下摆
        （见 gen_bongo_piano.py 的 KB_TOP）。外壳只留一圈 PAD 边，转完是
        一条完整的圆角矩形，不会在角上被窗口切出直角。
        """
        if not self.valid:
            return
        # 键盘本体（外壳 + 40 个键帽 + 阴影）是不随光标变的死图层，但每帧
        # 重渲要 ~19ms——40Hz 下就是 CPU 吃满、鼠标手跟不动的主因。烘成一张
        # 位图后每帧只剩一次 blit，高亮元素照旧单独画（它们是独立元素）。
        base = self._desk_base(painter)
        if base is not None:
            # 目标矩形显式给画布尺寸：缓存图是按设备像素比放大的，
            # drawImage(x, y, img) 会按 img 自己的尺寸画成 2 倍大。
            painter.drawImage(QRectF(0.0, 0.0, self.canvas_w, self.canvas_h), base)
        else:
            painter.save()
            # 第二个参数必须给 True（叠加）。setTransform 默认是**替换**：直接把
            # 调用方的 worldTransform 冲掉，上层要是用过 scale()/translate() 排版，
            # 键盘就会按 1:1 画到别处去，和身体差一倍大小。
            painter.setTransform(self._desk_matrix(), True)
            self._render_desk_base(painter)
            painter.restore()

        painter.save()
        painter.setTransform(self._desk_matrix(), True)
        # 高亮分两层画：普通键（白键）先亮，压在它们上面的键（钢琴黑键）
        # 之后再把键体重绘一遍、最后亮自己。混在一起按集合顺序画的话，
        # 白键那整块高亮会把叠在它上沿的黑键抹掉，一眼看去像掉了几颗键。
        raise_caps = frozenset(getattr(self.mode, "raise_caps", ()) or ())
        for cap in caps:
            if cap in raise_caps:
                continue
            self._paint_cap_highlight(painter, cap)
        for cap in caps:
            if cap not in raise_caps:
                continue
            rect = self._bounds.get(f"k{cap}")
            if rect is not None:
                # 重绘键体本身：它本来就是压在白键上的那一层
                self._renderer.render(painter, f"k{cap}", rect)
            self._paint_cap_highlight(painter, cap)
        painter.restore()

    def _paint_cap_highlight(self, painter: QPainter, cap: str) -> None:
        """点亮一颗键帽。

        素材自带高亮元素（透视键帽的 AABB 盖不住形状）就直接渲染它，
        没有才退回盖圆角矩形——60% 那套键帽是正矩形，矩形就对得上。
        """
        hl = self._bounds.get(f"h{cap}")
        if hl is not None:
            self._renderer.render(painter, f"h{cap}", hl)
            return
        rect = self._bounds.get(f"k{cap}")
        if rect is None:
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._highlight)
        painter.drawRoundedRect(rect.adjusted(0.4, 0.4, -0.4, -0.4), 2, 2)

    def _render_desk_base(self, painter: QPainter) -> None:
        """键盘本体：阴影 + 外壳 + 键帽，不含高亮。"""
        # 键盘阴影是独立元素（塞进 #desk 会撑大 bbox，而 bbox 是渲染目标矩形）
        shadow = self._bounds.get("kb_shadow")
        if shadow is not None:
            self._renderer.render(painter, "kb_shadow", shadow)
        self._renderer.render(painter, self.DESK, self._bounds[self.DESK])

    def _device_ratio(self, painter: QPainter) -> float:
        """painter 的设备宽度 / 画布宽度，也就是窗口相对画布放大了几倍。

        量化到 0.5 一档：窗口尺寸抖动（拖到不同 DPI 的屏）时不必为了一点
        零头整张重建。
        """
        device = painter.device()
        width = float(device.width()) if device is not None else 0.0
        if width <= 0 or not self.canvas_w:
            return 1.0
        return max(1.0, round(width / self.canvas_w * 2.0) / 2.0)

    def _desk_base(self, painter: QPainter) -> Optional[QImage]:
        """把键盘本体渲染进一张按设备像素比放大的 QImage，缓存复用。

        用 QImage 而不是 QPixmap：单测和离屏预览里经常没有 QGuiApplication，
        QPixmap 在那种环境下直接构造失败。
        """
        key = (int(self.canvas_w), int(self.canvas_h), self._device_ratio(painter))
        cached = getattr(self, "_desk_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        ratio = key[2]
        img = QImage(
            int(self.canvas_w * ratio),
            int(self.canvas_h * ratio),
            QImage.Format_ARGB32_Premultiplied,
        )
        if img.isNull():
            return None
        img.fill(Qt.transparent)
        q = QPainter(img)
        if not q.isActive():
            return None
        q.setRenderHint(QPainter.Antialiasing, True)
        q.setRenderHint(QPainter.SmoothPixmapTransform, True)
        q.setWindow(0, 0, int(self.canvas_w), int(self.canvas_h))
        q.setTransform(self._desk_matrix(), True)
        self._render_desk_base(q)
        q.end()
        self._desk_cache = (key, img)
        return img

    def paint_pad(
        self,
        painter: QPainter,
        left_down: bool = False,
        right_down: bool = False,
        offset: Optional[QPointF] = None,
    ) -> None:
        """桌面 + 鼠标垫 + 鼠标，画在身体和键盘**之前**（这几样在最底层）。

        只跟公共倾斜走、**不吃键盘的 persp**：persp 是按 #desk 的 bbox 算的，
        垫子套上去会被压成跟键盘一样的梯形。键鼠造型的透视已经烘在素材坐标里，
        persp 是恒等变换，两层自然对齐。

        光标位移只 translate 鼠标本体和左右键高亮，不动垫子。高亮是独立元素
        而不是事后盖一层矩形，跟着同一个 translate 走，坐标不用再算一遍。
        """
        if not self.valid or not self.mouse_hand:
            return
        pad = self._bounds.get("pad")
        if pad is None:
            return
        painter.save()
        self._tilted(painter)
        self._renderer.render(painter, "pad", pad)
        if offset is not None:
            painter.translate(offset.x(), offset.y())
        mouse = self._bounds.get("mouse")
        if mouse is not None:
            self._renderer.render(painter, "mouse", mouse)
        for eid, down in (("mouse_l", left_down), ("mouse_r", right_down)):
            rect = self._bounds.get(eid)
            if down and rect is not None:
                self._renderer.render(painter, eid, rect)
        painter.restore()

    def paint_table(self, painter: QPainter) -> None:
        """桌面单独一层，画在 body **之后**。

        桌面是实体：宠物坐在桌沿后面，桌子挡住它的下半身，只露上半身。
        和身体一起画的后果是猫整个浮在桌面上，像贴纸。也不吃 persp——
        桌面不是键盘的一部分。
        """
        if not self.valid:
            return
        table = self._bounds.get("table")
        if table is None:
            return
        painter.save()
        self._tilted(painter)
        self._renderer.render(painter, "table", table)
        painter.restore()

    def mouse_center(self) -> Optional[QPointF]:
        """握鼠标那只手的基准中心（倾斜后的画面坐标，不含光标位移）。"""
        rect = self._bounds.get("paw_mouse")
        if rect is None:
            return None
        return self._tilt().map(QPointF(rect.center()))

    def rest_center(self, screen_side: str) -> QPointF:
        """爪子没按任何可映射键时停的位置（已过透视+倾斜，是画面坐标）。

        模式给了 rest_cap_* 就落到那个键帽上，走的是和按键完全相同的
        cap_center + paw_y_offset：待机 = 真按一下再松手，位置一模一样。
        给了 paw_rest_* 则用桌面上的点，而且**只走倾斜、不套键盘透视**：
        那个点根本不在键盘 bbox 里，persp 是绕着键盘算的，外推出去会偏几像素。
        都没给就退回键盘模板位置（60% 那套键盘的老行为）。
        """
        mode = getattr(self, "mode", None)
        cap = getattr(mode, "rest_cap_r" if screen_side == "r" else "rest_cap_l", None)
        if cap:
            center = self.cap_center(cap)
            if center is not None:
                center.setY(center.y() + float(getattr(mode, "paw_y_offset", 0.0)))
                return center
        rest = getattr(mode, "paw_rest_r" if screen_side == "r" else "paw_rest_l", None)
        if rest:
            return self._tilt().map(QPointF(rest[0], rest[1]))
        raw = QPointF(self._bounds[self.PAWS[(screen_side, False)]].center())
        return self._desk_matrix().map(raw)

    def cap_center(self, cap: Optional[str]) -> Optional[QPointF]:
        """键帽中心，爪子要挪到这里。没画这个键就返回 None。

        返回的是**透视+倾斜后**的画面坐标。键盘一斜、一收窄，键帽整体就往
        中线挤了；还拿着 SVG 原始坐标的话爪子会落在键帽外侧，差得最远的是
        最上面一排。所以这里必须走 _desk_matrix，不能只走 _tilt。
        """
        if not cap:
            return None
        rect = self._bounds.get(f"k{cap}")
        if rect is None:
            return None
        return self._desk_matrix().map(QPointF(rect.center()))

    def set_pose(self, pose: Pose) -> None:
        """宿主每帧喂一次表情姿态。只存字段，不做任何绘制工作。"""
        self._pose = pose or NEUTRAL

    def pose_matrix(self, pose: Pose) -> QTransform:
        """整只鼠的姿态：绕脖子转 → 绕身体底部缩放 → 上下挪。

        旋转支点取在脖子上而不是画布中心：绕中心转的话脚会跟着扫，
        看起来像整只在地上翻滚；绕脖子转，被键盘和桌沿盖住的下半身
        几乎不动，只有头在偏。
        """
        t = QTransform()
        cx = self.canvas_w / 2.0
        pivot_y = self.canvas_h * 0.60      # 脖子
        foot_y = self.canvas_h * 0.77       # 缩放支点压在身体底部
        if pose.rot:
            t.translate(cx, pivot_y)
            t.rotate(pose.rot)
            t.translate(-cx, -pivot_y)
        if pose.scale != 1.0:
            t.translate(cx, foot_y)
            t.scale(pose.scale, pose.scale)
            t.translate(-cx, -foot_y)
        if pose.dy:
            t.translate(0.0, pose.dy)
        return t

    def _eye_boxes(self):
        """眼睛在**画布坐标**下的矩形（body bbox 按比例展开）。"""
        rect = self._body.boundsOnElement("body")
        if rect.isNull():
            return ()
        return tuple(
            (
                rect.x() + fx * rect.width(),
                rect.y() + fy * rect.height(),
                fw * rect.width(),
                fh * rect.height(),
            )
            for fx, fy, fw, fh in self.EYE_BOXES
        )

    def _paint_eyes(self, painter: QPainter) -> None:
        """先抹掉原眼珠，再按当前状态重画。

        原素材里眼睛是「黑眼珠 + 一点白高光」，闭眼/眨眼没有对应素材，
        叠贴纸会在眼睛周围留一圈原图的抗锯齿边。所以宁可盖一层脸灰
        再把整只眼重画——多出的 0.5 就是拿来吃掉那圈边的。
        """
        ink = QColor(self.INK)
        paper = QColor(self.PAPER)
        gray = QColor(self.FACE_GRAY)
        eye = self._pose.eye

        for x, y, w, h in self._eye_boxes():
            # 睁眼直接用原素材：原图的眼珠自带高光，重画一遍只会显得
            # 全黑（高光怎么摆都还原不了原味）。只有换表情才动它。
            if eye == EYE_OPEN:
                continue

            painter.setPen(Qt.NoPen)
            painter.setBrush(gray)
            painter.drawRect(QRectF(x - 0.6, y - 0.6, w + 1.2, h + 1.2))

            cx, cy = x + w / 2.0, y + h / 2.0
            line = max(2.0, h * 0.17)

            if eye == EYE_CLOSED:
                # 闭眼：一道下弯的弧（笑眼），两端收在里面
                path = QPainterPath(QPointF(x + 1.0, cy - h * 0.06))
                path.quadTo(
                    QPointF(cx, cy + h * 0.36), QPointF(x + w - 1.0, cy - h * 0.06)
                )
                painter.setPen(QPen(ink, line, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
                continue

            if eye == EYE_BLINK:
                # 眨眼：压成一条略鼓的粗杠
                path = QPainterPath(QPointF(x + 1.2, cy + h * 0.04))
                path.quadTo(
                    QPointF(cx, cy - h * 0.14), QPointF(x + w - 1.2, cy + h * 0.04)
                )
                painter.setPen(QPen(ink, line * 1.15, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
                continue

            if eye == EYE_HALF:
                # 半睁：比闭眼浅、比眨眼细的一道弧（困倦眯眼）。
                # 别画黑块——半截黑豆看着像整只眼被涂黑了。
                path = QPainterPath(QPointF(x + 1.4, cy - h * 0.02))
                path.quadTo(
                    QPointF(cx, cy + h * 0.16), QPointF(x + w - 1.4, cy - h * 0.02)
                )
                painter.setPen(QPen(ink, max(1.8, h * 0.11), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
                continue

            # 瞪大（惊醒）：照受惊表情包改的「全眼白」——黑豆放大会只显
            # 黑，表情包里受惊是眼白整个撑大、没有瞳孔。白底描黑边就够，
            # 嘴不用另画：body.svg 原素材常态就是张嘴吐舌。
            rx, ry = w * 0.5 * 1.06, h * 0.5 * 1.04
            painter.setPen(QPen(ink, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(paper)
            painter.drawEllipse(QPointF(cx, cy), rx, ry)

    def _body_bitmap(self, painter: QPainter) -> Optional[QImage]:
        """身体 + 眼睛合成一张位图，姿态变换只作用在这张图上。

        不能每帧直接 render 到已经带姿态的 painter 上：QSvgRenderer.render
        会自己设置 viewBox / viewport，外部那套 translate+rotate 会被打回
        原形（表现是身体跑到画布左上角、眼睛留在原地）。先离屏合一张，
        再整张 drawImage，位置和表情就不可能对不上。

        缓存分两层：身体按设备像素比烘一次，眼睛按表情状态各留一张。
        姿态每帧都在变，只能留在 drawImage 的变换里，不烘进位图。
        """
        ratio = self._device_ratio(painter)
        base_key = (int(self.canvas_w), int(self.canvas_h), ratio)
        base = getattr(self, "_body_base_cache", None)
        if base is None or base[0] != base_key:
            rect = self._body.boundsOnElement("body")
            if rect.isNull():
                return None
            img = QImage(
                int(self.canvas_w * ratio),
                int(self.canvas_h * ratio),
                QImage.Format_ARGB32_Premultiplied,
            )
            if img.isNull():
                return None
            img.fill(Qt.transparent)
            q = QPainter(img)
            if not q.isActive():
                return None
            q.setRenderHint(QPainter.Antialiasing, True)
            q.setRenderHint(QPainter.SmoothPixmapTransform, True)
            q.setWindow(0, 0, int(self.canvas_w), int(self.canvas_h))
            self._body.render(q, "body", rect)
            q.end()
            base = (base_key, img)
            self._body_base_cache = base

        key = (base_key, self._pose.eye)
        cached = getattr(self, "_body_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        # 睁眼就用原素材那张底图，连拷贝都省了 —— 眼珠是原图的，
        # 重画只会失真（高光还原不了原味）。
        if self._pose.eye == EYE_OPEN:
            return base[1]
        out = base[1].copy()
        q = QPainter(out)
        q.setRenderHint(QPainter.Antialiasing, True)
        q.setWindow(0, 0, int(self.canvas_w), int(self.canvas_h))
        self._paint_eyes(q)
        q.end()
        self._body_cache = (key, out)
        return out

    def _paint_body_layer(self, painter: QPainter, eid: str) -> None:
        """按元素画 body.svg 的一层，外面套身体那份倾斜（不含键盘透视）。"""
        if not self._body.isValid():
            return
        rect = self._body.boundsOnElement(eid)
        if rect.isNull():
            return
        painter.save()
        self._tilted(painter)
        self._body_scaled(painter)
        if self.body_dy:
            painter.translate(0.0, self.body_dy)
        self._body.render(painter, eid, rect)
        painter.restore()

    def _body_scaled(self, painter: QPainter) -> None:
        """身体整体放大，绕「画布水平中心 + tilt_cy」这一点。

        锚点压在底部而不是正中：身体是从桌沿后面冒出来的，往上长才像坐近
        了一点；绕正中放大会连下身一起长大，桌沿就盖不住了。
        身体和头共用这一份变换，不然下巴会和躯干错位。
        """
        if self.body_scale == 1.0:
            return
        cx = self.canvas_w / 2.0
        painter.translate(cx, self.tilt_cy)
        painter.scale(self.body_scale, self.body_scale)
        painter.translate(-cx, -self.tilt_cy)

    def paint_body(self, painter: QPainter) -> None:
        """躯干 + 尾巴 + 五官，画在键盘**后面**。

        走位图而不是直接 render：只有整张位图能做姿态变换（歪头 / 呼吸），
        眼睛也必须和身体用同一个变换画，否则一歪头眼睛就漂在原来的位置。
        """
        if not self._body.isValid():
            return
        img = self._body_bitmap(painter)
        if img is None:
            self._paint_body_layer(painter, "body")
            return
        painter.save()
        self._tilted(painter)
        self._body_scaled(painter)
        matrix = self.pose_matrix(self._pose)
        if not matrix.isIdentity():
            # 第二个参数必须 True：setTransform 默认替换，会把上面的倾斜冲掉
            painter.setTransform(matrix, True)
        if self.body_dy:
            painter.translate(0.0, self.body_dy)
        painter.drawImage(QRectF(0.0, 0.0, self.canvas_w, self.canvas_h), img)
        painter.restore()

    def paint_bubble(self, painter: QPainter, pose: Optional[Pose] = None) -> None:
        """气泡最后画：不吃倾斜、不吃身体缩放，所以位置要自己跟一遍。

        造型里的 body_scale / body_dy 是「把宠物抬到桌沿后面」用的，
        气泡要是按画布绝对坐标钉死，键鼠造型下就飘到头外面去了。
        """
        pose = pose or self._pose
        if not pose.bubble or pose.bub <= 0.1:
            return
        k = max(0.0, min(1.2, pose.bub))
        cx = self.canvas_w * self.BUBBLE_POS[0]
        cy = self.canvas_h * self.BUBBLE_POS[1]
        if self.body_scale != 1.0:
            cx = self.canvas_w / 2.0 + (cx - self.canvas_w / 2.0) * self.body_scale
            cy = self.tilt_cy + (cy - self.tilt_cy) * self.body_scale
        cy += self.body_dy

        rx, ry = self.BUBBLE_R[0] * k, self.BUBBLE_R[1] * k
        if rx < 2.0:
            return

        if pose.bubble == BUBBLE_BANG:
            # 惊吓的「!」直接立在头边，不装气泡壳 —— 表情包里就是一颗
            # 裸的红色感叹号，包进白圈反而像对话框、弱了受惊的意思。
            # bub 控制弹出：从锚点缩放，弹出来有个小 pop。
            hgt, wdt = 46.0 * k, 12.0 * k
            bar = QPainterPath()
            bar.addRoundedRect(
                QRectF(cx - wdt / 2.0, cy - hgt / 2.0, wdt, hgt * 0.60),
                wdt / 2.0, wdt / 2.0,
            )
            dot = QPainterPath()
            dot.addEllipse(QPointF(cx, cy + hgt * 0.32), wdt * 0.62, wdt * 0.62)
            painter.save()
            # 不描边：深红一圈套在红底上看着像又包了个框
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#e25b5b"))
            painter.drawPath(bar.united(dot))
            painter.restore()
            return

        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), rx, ry)
        tail = QPainterPath()
        tail.moveTo(cx - rx * 0.52, cy + ry * 0.82)
        tail.lineTo(cx - rx * 1.02, cy + ry * 1.40)
        tail.lineTo(cx + rx * 0.14, cy + ry * 0.94)
        tail.closeSubpath()
        path = path.united(tail).simplified()

        painter.save()
        painter.setPen(QPen(QColor("#3a3a3a"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(QColor(self.PAPER))
        painter.drawPath(path)

        text = "z z" if pose.bubble == BUBBLE_SLEEP else "!"
        # 「!」照表情包用红色，受惊的语义靠它
        painter.setPen(
            QColor("#e25b5b") if pose.bubble == BUBBLE_BANG else QColor("#2a2a2a")
        )
        font = QFont("Microsoft YaHei")
        font.setPixelSize(max(6, int((15 if pose.bubble == BUBBLE_SLEEP else 22) * k)))
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        painter.drawText(
            QPointF(
                cx - metrics.width(text) / 2.0,
                cy + (metrics.ascent() - metrics.descent()) / 2.0,
            ),
            text,
        )
        painter.restore()

    def paint_head(self, painter: QPainter) -> None:
        """头 + 耳朵 + 五官，画在键盘**前面**。

        bongocat 里猫头是压在键盘上沿的（头在近处、键盘在远处）。整体一层画在
        键盘后面的话，下巴会被键帽啃掉一截，看着像缩着脖子从键盘后探出来。
        """
        self._paint_body_layer(painter, "head")

    def body_rect(self) -> QRectF:
        """body.svg 铺满整块画布，留着给外部算命中区域用。"""
        return QRectF(0.0, 0.0, self.canvas_w, self.canvas_h)

    def paint_paws(
        self,
        painter: QPainter,
        left_down: bool,
        right_down: bool,
        centers: Optional[Dict[str, QPointF]] = None,
    ) -> None:
        """爪子画在 body 之后（前面）。

        centers 是画面左右爪当前的中心点，由 PawMotion 逐帧给出，已经是倾斜后的
        坐标；不给就落回 SVG 原位（同样要过一遍倾斜，否则爪子会跳到没斜的位置）。
        平移只改 render 的目标矩形，爪子本身不缩放。
        """
        if not self.valid:
            return
        for pet_side, down in (("left", left_down), ("right", right_down)):
            screen = self.PET_TO_SCREEN[pet_side]
            if self.mouse_hand and screen == self.mouse_hand:
                # 握鼠标那只手：一直是「按在鼠标上」的形状，位置由光标位移决定
                eid = "paw_mouse"
            else:
                eid = self.PAWS[(screen, down)]
            if eid not in self._bounds:
                continue
            rect = QRectF(self._bounds[eid])
            center = (centers or {}).get(screen)
            if center is None:
                center = self._tilt().map(QPointF(rect.center()))
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
    # 爪子直径 34，间距给到 42 才留得出 8 的空隙；再小两拳边缘只差几个像素，
    # 按键位相近的两只手指（q 和 a）会看着像叠在一起。
    MIN_GAP = 42.0
    # 光标位移上限（画布坐标），分轴给：垫子 140×84、鼠标 36×54，水平富余
    # 55、垂直只剩 15，两边共用一个 ±12 等于把水平方向也锁死了——手只能在
    # 垫子中间一小块里蹭。原来 ±12 是照旧版小垫子算的，垫子收小之后更憋。
    MOUSE_MAX_X = 20.0
    MOUSE_MAX_Y = 12.0
    # 爪子比键帽宽（直径 28 vs 18），落在键帽正中会把高亮整个盖掉。
    # 往上提一点，让它只压住上沿，下半截还看得见是哪个键亮着。
    Y_OFFSET = -5.0
    # 闲置时爪子往上的抬起量。
    # 这个值加到 Y_OFFSET 之上：从键帽中心算起共 -38，打字时上下一趟看得清。
    # 爪子从 22 加粗到 28 之后这里从 34 收到 30：手变大，同样的位移会让
    # 整只手顶进身体轮廓里，手臂反而被吃掉。
    LIFT = 28.0
    # 抬手**只动 y**，不往两侧张。
    # 张开的话每次松手 x 就横移一段、再按又弹回键上，
    # 连续打同一个键时爪子会左右来回摆，看着眼晕。
    # 停手多久把打字手收回休息位。按键会不停重置这个计时器，所以连打时
    # 根本触发不到——只有真的停下来，手才离开键盘回到身体边上。
    # 5000 是「发呆」不是「换气」：700ms 那档在一句话的词间就把爪子甩回
    # 键盘下沿，打字全程手在飞；拉长之后只在真的停手时动一次，这个动作
    # 同时充当待机提示（配合 IdleGlow 的键帽心跳）。
    IDLE_MS = 5000

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
        # 抬没抬起来。松手后位置留在最后一个键上不动，只把 y 往上收，
        # 所以「落脚点」和「当前该在哪」必须分开记。
        self._lifted = {"l": True, "r": True}
        # 鼠标手（造型里 mouse_hand 指定的那侧）：不参与按键躲避，也不抬起来，
        # 位置 = 鼠标中心 + 光标位移
        self._frozen = getattr(renderer, "mouse_hand", "") or ""
        # 爪子的纵向落点按模式给：40% 键帽只有 15 高，沿用 60% 的 -5
        # 会把键帽高亮整个盖住。
        mode = getattr(renderer, "mode", None)
        self._y_offset = float(getattr(mode, "paw_y_offset", self.Y_OFFSET))
        self._mouse_offset = QPointF(0.0, 0.0)
        for side in ("l", "r"):
            if side == self._frozen:
                rest = renderer.mouse_center() or renderer.rest_center(side)
                self._base[side] = QPointF(rest)
                self._cur[side] = QPointF(rest)
                self._tgt[side] = QPointF(rest)
                self._lifted[side] = False
                continue
            rest = renderer.rest_center(side)
            self._base[side] = QPointF(rest)
            if self._has_rest():
                # 有休息位的造型一上来就是闲置态：手直接搁在桌面上，别做个
                # 「先抬起来再落下去」的开场动画。
                self._lifted[side] = False
                self._cur[side] = QPointF(rest)
                self._tgt[side] = QPointF(rest)
            else:
                # 没有休息位的（60% 那套键盘）保持抬着，等着接第一个键。
                lifted = QPointF(rest)
                lifted.setY(lifted.y() - self.LIFT)
                self._cur[side] = QPointF(lifted)
                self._tgt[side] = QPointF(lifted)
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)
        # 闲置计时器：松手后开始跑，中途再按一下就重置，超时才回休息位。
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(self.IDLE_MS)
        self._idle.timeout.connect(self._go_rest)

    def centers(self) -> Dict[str, QPointF]:
        out = {side: QPointF(pt) for side, pt in self._cur.items()}
        if self._frozen:
            base = self._renderer.mouse_center()
            if base is not None:
                out[self._frozen] = QPointF(
                    base.x() + self._mouse_offset.x(),
                    base.y() + self._mouse_offset.y(),
                )
        return out

    def set_mouse_offset(self, dx: float, dy: float) -> None:
        """光标位移（已平滑过），单位是画布坐标，由 MouseTracker 每帧喂进来。

        夹在 ±MOUSE_MAX：幅度给大了手会滑出垫子，看着像贴纸被拖走；
        给小了在桌宠尺寸下又看不出在动。
        """
        if not self._frozen:
            return
        dx = max(-self.MOUSE_MAX_X, min(dx, self.MOUSE_MAX_X))
        dy = max(-self.MOUSE_MAX_Y, min(dy, self.MOUSE_MAX_Y))
        if abs(dx - self._mouse_offset.x()) < 0.05 and abs(dy - self._mouse_offset.y()) < 0.05:
            return
        self._mouse_offset = QPointF(dx, dy)
        self.changed.emit()

    def mouse_offset(self) -> Optional[QPointF]:
        """当前光标位移，给 paint_pad 平移鼠标用；没有鼠标手时返回 None。"""
        if not self._frozen:
            return None
        return QPointF(self._mouse_offset)

    def set_targets(self, left_cap: Optional[str] = None, right_cap: Optional[str] = None) -> None:
        """left_cap / right_cap 是宠物左/右手最近按下的键帽。

        None 表示这只手没按到键盘上画着的键（空格以外的数字、回车…），
        或者刚松开：位置留在最后一次落下的地方，只往上抬 LIFT，不回休息位。
        弹回原位的话打字时爪子会在画面中间来回甩，反而看不出是按哪儿。
        """
        goal = {}
        for pet_side, cap in (("left", left_cap), ("right", right_cap)):
            goal[self._renderer.PET_TO_SCREEN[pet_side]] = cap
        if self._frozen:
            # 只剩一只手按键盘，左右手分工没意义：另一侧的键也交给它。
            # 不合并的话按 Q（映射到画面右）时两只手都不动——一只被冻结，
            # 另一只收到的目标是 None。
            other = "r" if self._frozen == "l" else "l"
            goal[other] = goal.get(other) or goal.get(self._frozen)
        for screen in ("l", "r"):
            if screen == self._frozen:
                continue
            cap = goal.get(screen)
            center = self._renderer.cap_center(cap)
            if center is None:
                self._has_goal[screen] = False
                # 松手（cap 为 None）才抬手。cap 有值却找不到键帽，说明键盘素材
                # 上根本没画这个键（数字行、F 区、退格…），那就什么都不做——
                # 换目标会飞到假位置，抬手等于凭空给一个「按到了」的反馈。
                if cap is None:
                    self._lifted[screen] = True
                continue
            center.setY(center.y() + self._y_offset)
            self._base[screen] = QPointF(center)
            self._has_goal[screen] = True
            self._lifted[screen] = False
        for side in ("l", "r"):
            tgt = QPointF(self._base[side])
            if self._lifted[side]:
                tgt.setY(tgt.y() - self.LIFT)
            self._tgt[side] = tgt
        self._separate_targets()
        # 有手落在键上＝还在打字，把回位计时器按掉；两只手都悬空才起表。
        # 只对配了 paw_rest_* 的造型生效：60% 那套键盘手就该一直在键上。
        if any(self._has_goal[s] for s in ("l", "r")):
            self._idle.stop()
        elif self._has_rest():
            self._idle.start()
        if self._timer.isActive():
            return
        if any(not self._near(self._cur[s], self._tgt[s]) for s in ("l", "r")):
            self._timer.start()

    def _has_rest(self) -> bool:
        """闲置要不要把打字手收回去。由造型的 idle_rest 决定，默认开。

        早先的判据是「配了休息位才收」：60% 那套键盘没配 paw_rest_*，手就一直
        赖在最后按下的键上，永远不会离开键盘。现在统一收回——rest_center 对
        没配的造型会回退到键盘模板里 paw_*_rest 的位置，不需要每款都填坐标。

        注意 60% 这套的 paw_*_rest 和 paw_*_down 是同一个中心点，收回去只是
        手形从按扁变回圆，没有位移。真正看得见的待机反馈是 IdleGlow 的扫光。
        """
        mode = getattr(self._renderer, "mode", None)
        return bool(getattr(mode, "idle_rest", True))

    def _go_rest(self) -> None:
        """停手够久：打字手离开键盘，落回身体边上的休息位。

        松手就弹回去的话，一句话里每两个词之间爪子都要飞一趟；一直停在
        最后按下的那个键上又像在等下一条指令。折中就是等 IDLE_MS。
        """
        for side in ("l", "r"):
            if side == self._frozen:
                continue
            rest = self._renderer.rest_center(side)
            self._base[side] = QPointF(rest)
            self._has_goal[side] = False
            # 落下而不是悬着：待机就是手搁在桌面上，抬 LIFT 会让它浮在
            # 键盘前沿上方，看着像还没松手。
            self._lifted[side] = False
            self._tgt[side] = QPointF(rest)
        if not self._timer.isActive():
            self._timer.start()

    def _separate_targets(self) -> None:
        """两爪挨太近就分开，保证能看出是两只手。

        分开的时候要看是谁挡着谁：只有一只手按在键上、另一只还停在休息位
        时，让**闲着的那只**挪开。平均分摊的话，正在按 p 的爪子会被推离
        键帽十几个像素，明明按的是 p 看着却像按在 p 和 o 中间。
        """
        if self._frozen:
            # 键盘上只有一只手，没有「两爪挤在一起」这回事
            return
        left, right = self._tgt["l"], self._tgt["r"]
        gap = right.x() - left.x()
        # 用绝对值比：两只手「交叉」时 gap 是个大负数，拿有符号的比会被
        # 当成「挨得太近」。按 Backspace 就是这种情形——它是最左边的键，
        # 由屏幕上右边那只手去够，一路跑到闲着那只手的左边，gap 变成 -58，
        # 于是闲着的手被甩到按键手的旁边 38，两条胳膊一起动。
        if abs(gap) >= self.MIN_GAP:
            return
        lg, rg = self._has_goal["l"], self._has_goal["r"]
        # 推开的方向跟着实际左右顺序走。交叉时还是按「left 往左、right
        # 往右」的话，推的是按在键上的那只，爪子会被顶离键帽。
        sign = 1.0 if gap >= 0 else -1.0
        if lg and not rg:
            right.setX(left.x() + self.MIN_GAP * sign)
            return
        if rg and not lg:
            left.setX(right.x() - self.MIN_GAP * sign)
            return
        push = (self.MIN_GAP - abs(gap)) / 2.0
        left.setX(left.x() - push * sign)
        right.setX(right.x() + push * sign)

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


class IdleGlow(QObject):
    """停手 5 秒后的待机提示：整盘键帽一起亮三下，然后收工。

    为什么是键盘灯而不是让宠物做动作：body.svg 的头身是一整块（见
    scripts/trace_body.py 的说明），头单独转会在脖子留断口；爪子收回的
    位移只有 20px，肉眼几乎看不出来。键帽高亮是现成的绘制路径
    （paint_desk 的 caps 参数），不新增素材、不碰宠物姿态，是眼下唯一
    能「动起来」又不违和的层。

    计时器归宿主所有：key 状态一变就 poke() 重置 5 秒倒计时；到点后
    _beat 定时器亮/灭交替 BEATS 次，宿主每次重绘时把 caps() 并进高亮集合。
    """

    changed = pyqtSignal()

    IDLE_MS = 5000     # 停手多久开始
    BEAT_MS = 70       # 每帧时长
    BEATS = 26         # 26 帧 ≈ 1.8s，正好从键盘左边扫到右边
    SPAN_DIV = 6       # 同时亮几颗 = 全盘 / 6，全亮太刺眼，只留一道光

    def __init__(self, renderer: "BongoRenderer", parent: Optional[QObject] = None):
        super().__init__(parent)
        self._renderer = renderer
        self._pool: Tuple[str, ...] = ()
        self._seq: Tuple[str, ...] = ()
        self._lit: frozenset = frozenset()
        self._beats = 0
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(self.IDLE_MS)
        self._idle.timeout.connect(self._start)
        self._beat = QTimer(self)
        self._beat.setInterval(self.BEAT_MS)
        self._beat.timeout.connect(self._tick)

    def set_renderer(self, renderer: "BongoRenderer") -> None:
        """换造型后键帽集合跟着换，不然会去点亮一堆不存在的 id。"""
        self._renderer = renderer
        self._pool = ()
        self._seq = ()
        self.stop()

    def pool(self) -> Tuple[str, ...]:
        """这一款造型画出来的全部键帽（钢琴是 w0/b3 那套）。"""
        if not self._pool:
            caps = tuple(getattr(getattr(self._renderer, "mode", None), "caps", ()) or ())
            self._pool = caps or tuple(KEY_CAPS)
        return self._pool

    def poke(self) -> None:
        """有按键发生：掐掉正在跳的灯，重新数 5 秒。"""
        self._idle.stop()
        if self._beat.isActive() or self._lit:
            self.stop()
        self._idle.start()

    def stop(self) -> None:
        self._idle.stop()
        self._beat.stop()
        self._beats = 0
        if self._lit:
            self._lit = frozenset()
            self.changed.emit()

    def caps(self) -> frozenset:
        return self._lit

    def _sequence(self) -> Tuple[str, ...]:
        """按键帽中心的 x 排一遍，扫光才有方向。

        不按素材里 id 的顺序：那是描图输出的顺序，换一份键盘就对不上了。
        """
        if self._seq:
            return self._seq
        pairs = []
        for cap in self.pool():
            pt = self._renderer.cap_center(cap)
            if pt is not None:
                pairs.append((pt.x(), cap))
        pairs.sort()
        self._seq = tuple(cap for _, cap in pairs)
        return self._seq

    def _start(self) -> None:
        if not self._sequence():
            return
        self._beats = 0
        self._beat.start()
        self._tick()

    def _tick(self) -> None:
        seq = self._sequence()
        self._beats += 1
        if self._beats > self.BEATS or not seq:
            self.stop()
            return
        span = max(2, len(seq) // self.SPAN_DIV)
        # 从左侧外面扫进来再扫出去：位置换算成 float 再取窗口，边界不会跳
        pos = (self._beats - 1) / float(self.BEATS) * (len(seq) + span) - span
        lo = max(0, int(pos))
        hi = min(len(seq), int(pos) + span)
        self._lit = frozenset(seq[lo:hi])
        self.changed.emit()


class MouseTracker(QObject):
    """把真鼠标翻译成「鼠标在垫子上滑一点」，外加左右键状态。

    pynput 的 on_move 在 Windows 上每秒能到几百次：回调里**只累加位移**，
    不碰 UI。真正的重绘交给 30Hz 的 QTimer 取样——直接在回调里 emit 信号
    会把主线程刷爆。

    位移不是 1:1 映射光标坐标（那样手早滑出垫子了），而是「朝移动方向偏一点、
    停手后慢慢回中」：累积位移 → 每帧衰减 → 平滑逼近。所以鼠标往右甩，手
    和鼠标一起往右偏一小段，停下来再自己滑回垫子中间。
    """

    moved = pyqtSignal(float, float)
    buttons = pyqtSignal(bool, bool)

    # 33ms(30Hz) 在桌宠这个尺寸上已经能看到格子；25ms 是 40Hz，重绘开销
    # 还压得住（一帧就 body/table/pad/desk/head/paws 六个元素）。
    FRAME_MS = 25
    # 屏幕像素 / 画布单位。稳态偏移 ≈ 每帧像素 / (1 - DECAY) / 这个数：
    # 取 9 时，每秒甩 300px（约 7.5px/帧）手偏 6 个单位，快甩能到 20+。
    PIXELS_PER_UNIT = 9.0
    DECAY = 0.86      # 每帧回中比例，约 15 帧衰减到 10%
    # 0.35 在 30Hz 下时间常数接近 100ms，视觉上是「手追着鼠标跑」；
    # 0.5 跟手得多，代价是停下时的回中尾巴稍硬。
    EASE = 0.5

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._last = None
        self._acc = [0.0, 0.0]
        self._raw = [0.0, 0.0]
        self._cur = [0.0, 0.0]
        self._btn = (False, False)
        self._handle = None
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ---- 下面两个由 pynput 的监听线程调用 ----
    def on_move(self, x, y) -> None:
        if self._last is not None:
            self._acc[0] += x - self._last[0]
            self._acc[1] += y - self._last[1]
        self._last = (x, y)

    def on_click(self, x, y, button, pressed) -> None:
        name = str(button).lower()
        if "left" in name:
            self._btn = (pressed, self._btn[1])
        elif "right" in name:
            self._btn = (self._btn[0], pressed)
        else:
            return
        # 跨线程 emit，Qt 默认走队列连接，槽在主线程执行
        self.buttons.emit(*self._btn)

    def start(self) -> None:
        # 监听线程可能从上次 stop 起一直在累加，这里清干净再计时，
        # 否则重新开启的第一帧会「啪」地跳一下
        self._last = None
        self._acc = [0.0, 0.0]
        self._raw = [0.0, 0.0]
        self._cur = [0.0, 0.0]
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._acc = [0.0, 0.0]
        self._raw = [0.0, 0.0]
        self._cur = [0.0, 0.0]
        self._last = None
        if self._btn != (False, False):
            self._btn = (False, False)
            self.buttons.emit(False, False)

    def _tick(self) -> None:
        for i in (0, 1):
            self._raw[i] = self._raw[i] * self.DECAY + self._acc[i] / self.PIXELS_PER_UNIT
            # 先夹住「目标」，再平滑过去：夹当前值的话猛甩一下就是硬贴到边上
            target = max(-30.0, min(self._raw[i], 30.0))
            self._cur[i] += (target - self._cur[i]) * self.EASE
            if abs(self._cur[i]) < 0.05 and abs(self._raw[i]) < 0.05:
                self._cur[i] = 0.0
                self._raw[i] = 0.0
        self._acc = [0.0, 0.0]
        self.moved.emit(self._cur[0], self._cur[1])


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
        # 「按下就随机落键」的造型（钢琴）非空：每次 press 从这里抽一颗，
        # 真实键位不再参与。空 = 按真实键帽（60% / 键鼠那两套）。
        self.cap_pool: Tuple[str, ...] = ()
        self._rng = random.Random()

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
        if hint is None and self.cap_pool:
            # 随机落键的造型（钢琴）不看键位，F 区、Esc 这些没有左右归属、
            # bongo_keys 也不认识的键照样要弹：按无位置键处理，左右交替。
            hint = "alt"
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
        # 随机落键只在**按下**抽签：抽到的 cap 存进 _caps，松手时跟着这条
        # 记录一起清掉，不会出现「手抬起来之前那一下又换了个键」。
        if self.cap_pool:
            cap = self._rng.choice(self.cap_pool)
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


def _cap_pool_for(mode: Optional[BongoMode]) -> Tuple[str, ...]:
    """造型要求「按下随机落键」时返回琴键池，否则空元组。

    控制器本身不认识造型（纯状态机，方便单测），池子由宿主在换造型时喂进去。
    """
    if not getattr(mode, "random_caps", False):
        return ()
    return tuple(getattr(mode, "caps", ()) or ())


class BongoOverlay(QWidget):
    """贴在宠物身上的透明叠加层：身体 + 键盘 + 爪子。

    注意：身体现在由这一层画（body.svg），接入时要把宠物本体的 lieDown
    帧藏起来，否则同一个人会有两个身子。
    """

    def __init__(
        self,
        pet,
        svg_path: Optional[str] = None,
        mode: Optional[BongoMode] = None,
    ):
        super().__init__(None)
        self._pet = pet
        # 不给 mode 就用用户选中的那一款（config/bongo.json），
        # 造型开关不再是一个写死的类常量。
        self._renderer = BongoRenderer(svg_path, mode=mode)
        self.motion = PawMotion(self._renderer, self)
        self.motion.changed.connect(self.update)
        self._left = False
        self._right = False
        self._caps = frozenset()
        # 鼠标左右键是否按着（只有键鼠造型用得上）
        self._mouse_l = False
        self._mouse_r = False
        self._drag_offset = None
        # 待机提示：停手 5 秒后键帽亮三下（和 PawMotion 的收手同时发生）
        self._glow = IdleGlow(self._renderer, self)
        self._glow.changed.connect(self.update)
        # 表情姿态：呼吸 / 歪头 / 眨眼 / 打瞌睡 / 惊醒 / 打字气泡
        self._anim = PetAnim(self)
        self._anim.changed.connect(self.update)

        # 不吃 WindowTransparentForInput / WA_TransparentForMouseEvents 了：
        # 开着模式时宠物本体是藏着的，叠加层要是也不收鼠标，这块画面就彻底
        # 拖不动。键盘按键走的是全局监听，不靠窗口焦点，收鼠标不影响敲击。
        # macOS 上 Qt.Tool 是 NSPanel：窗口一失焦就被系统隐藏（pet.py 的
        # bubble_window 已经踩过这个坑），半透明 NSPanel 在部分 Intel 机器
        # 上还会直接把进程带走。mac 改用普通无边框窗口 + 置顶，和桌宠一致。
        if sys.platform == "darwin":
            self.setWindowFlags(
                Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
            )
        else:
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
            )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.OpenHandCursor)
        self._sync_geometry()

    def _sync_geometry(self) -> None:
        """窗口尺寸 = 画布 × CONTENT_SCALE，贴着宠物底边、水平居中。

        这里缩**窗口**而不是缩内容：早先的做法是窗口留 420×280、内容只用
        中间的 57%，桌面上就摊着一大块透明区，宠物实际被挤到窗口下半部，
        拖起来也怪。现在 setWindow 把整块 420×280 映射进小窗口，内容顶满、
        没有死区，缩放比例还是同一个数。
        """
        if self._pet is None:
            return
        w = max(1, int(self._renderer.canvas_w * CONTENT_SCALE))
        h = max(1, int(self._renderer.canvas_h * CONTENT_SCALE))
        self.setFixedSize(w, h)
        self.move(
            self._pet.x() + self._pet.width() // 2 - w // 2,
            self._pet.y() + self._pet.height() - h,
        )

    def follow_pet(self) -> None:
        self._sync_geometry()

    # ---- 拖动 ----
    # 拖的是叠加层，但位置记在**宠物**身上：宠物虽然藏起来了，
    # 关掉模式后它还得回到用户拖到的地方，不能白拖。

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        target = event.globalPos() - self._drag_offset
        # 夹在屏幕可用区内，别一拖就拖到看不见的地方去
        screen = QApplication.desktop().availableGeometry()
        target.setX(max(screen.x(), min(target.x(), screen.x() + screen.width() - self.width())))
        target.setY(max(screen.y(), min(target.y(), screen.y() + screen.height() - self.height())))
        delta = target - self.pos()
        if self._pet is not None and not delta.isNull():
            self._pet.move(self._pet.x() + delta.x(), self._pet.y() + delta.y())
        self._sync_geometry()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def apply_mode(self, mode: BongoMode) -> None:
        """运行时换造型：重建 renderer 和运动器，窗口尺寸与位置不变。

        不能只换 renderer 的模式字段就完事——换模式可能连素材（键盘布局）都
        换了，键帽 id 和爪子落点全得重算，运动器也跟着换一份干净的。
        旧 motion 用 deleteLater 收尾：它是本窗口的子对象，连带把内部那个
        QTimer 一起停掉，不然两只爪子会各跑一个定时器。
        """
        self._renderer = BongoRenderer(mode=mode)
        self._mouse_l = False
        self._mouse_r = False
        self._glow.set_renderer(self._renderer)
        old = getattr(self, "motion", None)
        self.motion = PawMotion(self._renderer, self)
        self.motion.changed.connect(self.update)
        if old is not None:
            old.deleteLater()
        self.update()

    def set_state(
        self,
        left_down: bool,
        right_down: bool,
        caps: Iterable[str] = (),
        left_cap: Optional[str] = None,
        right_cap: Optional[str] = None,
        mouse_l: bool = False,
        mouse_r: bool = False,
    ) -> None:
        """left_cap / right_cap 传 BongoController.cap_of 的结果，爪子会挪到那个键。

        mouse_l / mouse_r 只有键鼠造型用：控制鼠标上左右键的高亮。
        """
        caps = frozenset(caps)
        hand_changed = (left_down, right_down) != (self._left, self._right)
        same = (
            not hand_changed
            and caps == self._caps
            and (mouse_l, mouse_r) == (self._mouse_l, self._mouse_r)
        )
        self._left, self._right = left_down, right_down
        self._caps = caps
        self._mouse_l, self._mouse_r = mouse_l, mouse_r
        self.motion.set_targets(left_cap, right_cap)
        # 只有手的按下/抬起算「还在打字」：鼠标移动也会走到这里，不能让它把
        # 待机倒计时一次次顶回去，否则鼠标一直在动就永远等不到待机灯。
        if hand_changed:
            self._glow.poke()
            self._anim.note_key()
        if not same:
            self.update()

    def showEvent(self, event) -> None:
        # 表情动画只在窗口可见时跑：藏起来的窗口还按 25fps 重绘纯属烧 CPU
        self._anim.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._anim.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        self._renderer.set_pose(self._anim.pose())
        self._renderer.frame_transform(painter)
        centers = self.motion.centers()
        # 桌面盖在身体上：桌子是实体，它挡住宠物下半身，只露上半身。
        # 顺序只能是 身体 → 桌面 → 垫子 → 键盘，桌面排到垫子后面的话
        # 整张桌布会把鼠标垫和鼠标一起糊掉。
        self._renderer.paint_body(painter)
        self._renderer.paint_table(painter)
        self._renderer.paint_pad(
            painter, self._mouse_l, self._mouse_r, self.motion.mouse_offset()
        )
        self._renderer.paint_desk(painter, self._caps | self._glow.caps())
        self._renderer.paint_head(painter)
        self._renderer.paint_paws(painter, self._left, self._right, centers)
        # 气泡不吃任何变换，永远压在嘴上
        self._renderer.paint_bubble(painter)
        painter.end()


class BongoKeyboardMode(QObject):
    """托盘「敲键盘模式」的宿主：全局键盘监听 + 透明叠加层。

    BongoOverlay 自己不接键盘（WindowTransparentForInput），按键全靠全局监听，
    这里把 controller 的两个信号转给叠加层，并管住监听钩子和跟随定时器。

    宠物本体在开启期间藏起来：身体由叠加层画（body.svg），两套身子叠着会
    看到四只手。代价是藏起来之后没法拖着宠物挪位置——要挪先关模式。
    """

    def __init__(self, pet):
        super().__init__(pet)
        self._pet = pet
        self.overlay = BongoOverlay(pet)
        self.controller = BongoController()
        self.controller.state_changed.connect(self._on_state)
        self.controller.caps_changed.connect(self._on_caps)
        self._backend = ""
        self._saved = None  # 进入前的移动模式快照，退出时还原
        self._caps = frozenset()
        self._mouse = None  # MouseTracker，只有键鼠造型才建
        self._mouse_btns = (False, False)
        # 80ms 跟一次位置。比 hook 宠物 moveEvent 省事，且只在开启期间跑；
        # 拖动、换分辨率、任务栏挪位置都能自动跟上。
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(80)
        self._follow_timer.timeout.connect(self._follow)
        # 钢琴造型：按什么键都行，落哪颗琴键交给控制器抽签
        self.controller.cap_pool = _cap_pool_for(self.overlay._renderer.mode)

    def start(self) -> str:
        """开启并返回键盘后端名；空串表示这台机器拿不到全局键盘。

        PyQt5 里从槽函数逃出去的异常会把整个进程 abort —— 用户看到的
        就是「一打开键盘模式就闪退」，连报错都来不及看。这里兜住一切，
        失败就把已经做了一半的现场回滚干净，让托盘把开关弹回去。
        """
        try:
            return self._start()
        except Exception as exc:
            print(f"[Peko] 键盘模式启动失败: {exc!r}")
            try:
                self.stop()
            except Exception:
                pass
            return ""

    def _start(self) -> str:
        if not self._backend:
            self._backend = _start_key_listener(self.controller)
        if not self._backend:
            # 拿不到全局键盘就别摆画面了：冻住宠物又立刻解冻，中间会闪一下
            return ""
        # 记下进入前的模式：用户可能本来就勾着「停止移动」，退出时要原样还回去
        self._saved = {
            "control": getattr(self._pet, "control_mode", False),
            "follow": getattr(self._pet, "follow_mouse_mode", False),
            "allow": getattr(self._pet, "allow_movement", True),
        }
        # 宠物本体的可见性从现在起归叠加层管：macOS 的可见性守卫每 2 秒
        # 会把隐藏的宠物拉回来（见 pet._ensure_visible），3 秒宽限一过就
        # 和叠加层叠成两个身子。stop() 里交还。
        setattr(self._pet, "_bongo_owns_visibility", True)
        self._freeze_pet()
        self._pet.hide()
        self.overlay.show()
        self._follow()
        self._follow_timer.start()
        self._start_mouse()
        return self._backend

    def stop(self) -> None:
        self._follow_timer.stop()
        self._stop_mouse()
        _stop_key_listener(self.controller)
        self._backend = ""
        self._caps = frozenset()
        self.overlay.hide()
        self._thaw_pet()
        setattr(self._pet, "_bongo_owns_visibility", False)
        self._pet.show()

    def _freeze_pet(self) -> None:
        """把宠物钉在原地：操控/跟随全关、自动动作停掉。

        不钉住的话宠物本体还在跑 walk_left / walk_right，位置一直在变，
        叠加层跟着它跑——看起来就是「开了敲键盘还在自动移动」。
        """
        pet = self._pet
        try:
            pet.set_control_mode(False)
            pet.set_follow_mouse_mode(False)
            pet.set_allow_movement(False)
            # set_allow_movement(False) 只是让 on_state_tick 开头 return，
            # 已经排上的那一次不会立刻消掉，这里直接掐掉定时器
            actions = getattr(pet, "_auto_actions", None)
            if actions is not None:
                actions.stop()
        except Exception:
            pass

    def _thaw_pet(self) -> None:
        """还原进入前的模式；没存快照（异常路径）就放回自动模式。"""
        saved = self._saved or {}
        self._saved = None
        pet = self._pet
        try:
            pet.set_allow_movement(saved.get("allow", True))
            if saved.get("control"):
                pet.set_control_mode(True)
            elif saved.get("follow"):
                pet.set_follow_mouse_mode(True)
            elif getattr(pet, "allow_movement", True):
                pet._auto_actions.resume()
        except Exception:
            pass

    def apply_mode(self, mode: BongoMode) -> None:
        """换造型：叠加层重建，位置立刻跟上，不用关掉再开。

        切进/切出键鼠造型要跟着挂/摘鼠标监听，否则切回 60% 之后光标一动
        还在给一只已经不存在的鼠标手喂位移。
        """
        self.overlay.apply_mode(mode)
        # 换造型可能切换到「随机落键」（钢琴）或切回来，池子要跟着换，
        # 否则切回 60% 之后爪子还在乱弹不存在的琴键。
        self.controller.cap_pool = _cap_pool_for(mode)
        if self._follow_timer.isActive():
            if getattr(self.overlay._renderer, "mouse_hand", ""):
                self._start_mouse()
            else:
                self._stop_mouse()
        self._follow()

    def _follow(self) -> None:
        self.overlay.follow_pet()

    # ---- 鼠标 ----

    def _start_mouse(self) -> None:
        """键鼠造型才挂鼠标监听；拿不到 pynput.mouse 就只画一只静止的鼠标。"""
        if not getattr(self.overlay._renderer, "mouse_hand", ""):
            return
        if self._mouse is None:
            self._mouse = MouseTracker(self)
            self._mouse.moved.connect(self._on_mouse_move)
            self._mouse.buttons.connect(self._on_mouse_btn)
            _start_mouse_listener(self._mouse)
        self._mouse.start()

    def _stop_mouse(self) -> None:
        if self._mouse is not None:
            self._mouse.stop()
        self._mouse_btns = (False, False)

    def shutdown(self) -> None:
        """彻底拆掉：停模式 + 摘鼠标监听线程。

        stop() 只停采样定时器，pynput 的监听线程还在跑——没人摘的话进程退不掉。
        """
        self.stop()
        _stop_mouse_listener(self._mouse)
        self._mouse = None

    def _on_mouse_move(self, dx: float, dy: float) -> None:
        self.overlay.motion.set_mouse_offset(dx, dy)

    def _on_mouse_btn(self, left: bool, right: bool) -> None:
        self._mouse_btns = (bool(left), bool(right))
        self._push()

    def _push(self) -> None:
        left, right = self.controller.state
        ml, mr = self._mouse_btns
        self.overlay.set_state(
            left,
            right,
            self._caps,
            self.controller.cap_of("left"),
            self.controller.cap_of("right"),
            mouse_l=ml,
            mouse_r=mr,
        )

    def _on_state(self, _left: bool, _right: bool) -> None:
        # 信号带的两个值不直接用：控制器那边已经是最新的了，
        # 统一走 _push 读一次，免得两处取值时机不同步
        self._push()

    def _on_caps(self, caps: frozenset) -> None:
        self._caps = frozenset(caps)
        self._push()


# ============================================================
# 独立预览：python -m peko.ui.bongo
# ============================================================

# Qt 的功能键没有文字，event.text() 给的是 '\x08' 这种控制字符，
# 既查不到键帽、也会被 side_for 当成「未知字符」。这里把 key() 翻译回
# pynput 风格的键名，走上和全局监听同一条判定路径。
# 只收有键帽的键：方向键 / F 区在这块 60% 键盘上没有位置，映射了也落不下去。
_QT_KEY_NAMES = {
    Qt.Key_Backspace: "backspace",
    Qt.Key_Tab: "tab",
    Qt.Key_Return: "enter",
    Qt.Key_Enter: "enter",
    Qt.Key_Space: "space",
    Qt.Key_CapsLock: "caps_lock",
}


class _BongoDemo(QWidget):
    """独立演示窗口：自己画身体 + 键盘 + 爪子，接真实键盘。"""

    def __init__(self, pet_dir: str, scale: int = 2, mode: Optional[BongoMode] = None):
        super().__init__(None)
        # macOS 上 Qt.Tool 是 NSPanel：窗口一失焦就被系统隐藏（pet.py 的
        # bubble_window 已经踩过这个坑），半透明 NSPanel 在部分 Intel 机器
        # 上还会直接把进程带走。mac 改用普通无边框窗口 + 置顶，和桌宠一致。
        if sys.platform == "darwin":
            self.setWindowFlags(
                Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
            )
        else:
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
            )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._scale = scale
        self._pet_dir = pet_dir
        self._renderer = self._build_renderer(mode or get_mode())
        # 尺寸按 renderer 的画布定，不能再用模块常量：换模式时画布可能变
        self.setFixedSize(
            int(self._renderer.canvas_w) * scale, int(self._renderer.canvas_h) * scale
        )

        self._drag_origin = None
        self._caps = frozenset()
        self.motion = PawMotion(self._renderer, self)
        self.motion.changed.connect(self.update)
        self._glow = IdleGlow(self._renderer, self)
        self._glow.changed.connect(self.update)
        self._anim = PetAnim(self)
        self._anim.changed.connect(self.update)
        self.controller = BongoController()
        self.controller.state_changed.connect(self._on_state)
        self.controller.caps_changed.connect(self._on_caps)
        self.controller.cap_pool = _cap_pool_for(self._renderer.mode)

        screen = QApplication.desktop().screenGeometry()
        self.move(screen.width() // 2 - self.width() // 2, screen.height() - self.height() - 80)

    def _build_renderer(self, mode: BongoMode) -> BongoRenderer:
        """按模式解析素材：不同模式可能连键盘布局都不一样。"""
        return BongoRenderer(
            asset_path(mode, self._pet_dir, "desk"),
            asset_path(mode, self._pet_dir, "body"),
            mode=mode,
        )

    def _cycle_mode(self) -> None:
        """M 键循环切换造型并记住选择，下次启动还是这一款。

        全局监听接管键盘时这个键也会被它收到，但这里是窗口的本地事件，
        放在 _global_keys 判断之前，所以焦点在窗口上时仍然管用。
        """
        mode = next_mode(self._renderer.mode.key)
        set_mode(mode.key)
        self._renderer = self._build_renderer(mode)
        self._glow.set_renderer(self._renderer)
        self.controller.cap_pool = _cap_pool_for(mode)
        old = self.motion
        self.motion = PawMotion(self._renderer, self)
        self.motion.changed.connect(self.update)
        old.deleteLater()
        self._sync_paw_targets()
        self.update()
        print(f"[bongo] 造型切换为「{mode.label}」（{mode.key}）")

    def _on_state(self, left: bool, right: bool) -> None:
        self._glow.poke()
        self._anim.note_key()
        self._sync_paw_targets()
        self.update()

    def _on_caps(self, caps: frozenset) -> None:
        self._caps = caps
        self._glow.poke()
        self._anim.note_key()
        self._sync_paw_targets()
        self.update()

    def _sync_paw_targets(self) -> None:
        self.motion.set_targets(
            self.controller.cap_of("left"),
            self.controller.cap_of("right"),
        )

    def showEvent(self, event) -> None:
        self._anim.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._anim.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        self._renderer.set_pose(self._anim.pose())
        self._renderer.frame_transform(painter)
        centers = self.motion.centers()
        # 顺序：躯干 → 桌面 → 垫子 → 键盘 → 头 → 手臂 → 爪子。
        # 躯干先画，下半截被桌面和键盘吃掉，看着才像坐在桌子后面；
        # 头夹在键盘之后画，下巴压在键盘上沿，是「头在近处」不是「缩在后面」。
        self._renderer.paint_body(painter)
        self._renderer.paint_table(painter)
        self._renderer.paint_pad(painter, False, False, self.motion.mouse_offset())
        self._renderer.paint_desk(painter, self._caps | self._glow.caps())
        self._renderer.paint_head(painter)
        self._renderer.paint_paws(
            painter, *self.controller.state, centers=centers
        )
        self._renderer.paint_bubble(painter)
        painter.end()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            QApplication.quit()
            return
        # M 换造型要放在 _global_keys 判断之前：那一关会让本地路径整体让路，
        # 放到后面就永远收不到。
        if event.key() == Qt.Key_M and not event.isAutoRepeat():
            self._cycle_mode()
            return
        # 全局监听（pynput / keyboard）已经在跑的时候这条路径就多余了：
        # 同一个物理键会被两条路径各报一次，Qt 这边还只有 '\x08' 这种
        # 不带键位信息的 text，分不出是哪只手。让全局监听独占。
        if getattr(self, "_global_keys", False):
            super().keyPressEvent(event)
            return
        name = _QT_KEY_NAMES.get(event.key())
        if name is not None:
            side, cap = side_for(name=name), cap_for(name=name)
        else:
            text = event.text()
            side = side_for(char=text) if text else None
            cap = cap_for(char=text) if text else None
        self.controller.key_event(("qt", event.key()), True, side, cap)
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


def _mac_keyboard_trusted() -> bool:
    """macOS 上全局键盘监听是否已被系统放行。

    pynput 在 mac 上靠 CGEventTap 收键。没有「输入监控」授权时 tap 建不
    起来，但它照样 start() 成功、一个事件都不给——画面开着、爪子不动，
    用户只会觉得「开了没用」。这里先问系统一次（辅助功能授权），问不到
    （比如没打包 HIServices）就当已授权，交给 pynput 自己兜。
    """
    if sys.platform != "darwin":
        return True
    try:
        import HIServices  # pyobjc-framework-HIServices，装 pynput 时会一起带上

        return bool(HIServices.AXIsProcessTrusted())
    except Exception:
        return True


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

        # macOS：没授权就别起监听。tap 建不起来时 pynput 不抛异常、也不
        # 给事件，静默失败最难排查，不如在这里直接判定「拿不到」。
        if not _mac_keyboard_trusted():
            return ""

        def handler(pressed: bool):
            def cb(key):
                dispatch(
                    _pynput_key_id(key), pressed,
                    side_for_pynput(key), cap_for_pynput(key),
                )

            return cb

        listener = pynput_keyboard.Listener(on_press=handler(True), on_release=handler(False))
        listener.start()
        # 句柄挂在 controller 上，给 _stop_key_listener 用（关模式时要摘钩子，
        # 不然监听线程一直活着，托盘关掉了爪子还在按）
        ctrl._key_handle = listener
        ctrl._key_backend = "pynput"
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

        ctrl._key_handle = kb.hook(on_event)
        ctrl._key_backend = "keyboard"
        return "keyboard"

    return ""


def _stop_key_listener(ctrl: BongoController) -> None:
    """摘掉 _start_key_listener 挂上的钩子，可以反复调。

    只 unhook 自己挂的那一个：keyboard 库的 unhook_all 会把 main.py 里
    L+Enter 那条回退链路一起干掉，别图省事。
    """
    handle = getattr(ctrl, "_key_handle", None)
    backend = getattr(ctrl, "_key_backend", "")
    ctrl._key_handle = None
    if handle is None:
        return
    try:
        if backend == "keyboard":
            import keyboard as kb

            kb.unhook(handle)
        else:
            handle.stop()
            handle.join(timeout=1.0)
    except Exception:
        pass


def _start_mouse_listener(tracker: MouseTracker) -> bool:
    """挂全局鼠标监听，成功返回 True。

    拿不到 pynput.mouse（没装库 / 权限不足）不算致命：鼠标和垫子照画，
    只是不跟着光标动。键鼠造型的画面主体是键盘，缺了跟随还能用。
    """
    try:
        from pynput import mouse as pynput_mouse
    except Exception:
        return False
    try:
        listener = pynput_mouse.Listener(
            on_move=tracker.on_move,
            on_click=tracker.on_click,
        )
        listener.start()
        tracker._handle = listener
        return True
    except Exception:
        return False


def _stop_mouse_listener(tracker: Optional[MouseTracker]) -> None:
    handle = getattr(tracker, "_handle", None)
    if tracker is not None:
        tracker._handle = None
    if handle is None:
        return
    try:
        handle.stop()
    except Exception:
        pass


def _parse_mode_arg(argv) -> Optional[str]:
    """--mode <key> / --mode=<key>：本次运行临时指定造型。

    只对这次进程生效，不写回 config/bongo.json——调素材时来回试几种造型，
    不该把用户的选择冲掉。要持久化就进预览按 M。
    """
    for i, arg in enumerate(argv):
        if arg == "--mode" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--mode="):
            return arg.split("=", 1)[1]
    return None


def main() -> int:
    if "--list-modes" in sys.argv:
        for m in list_modes():
            print(f"{m.key:<10} {m.label}")
        return 0

    app = QApplication(sys.argv)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pet_dir = os.path.join(root, "pets", "BB")

    forced = _parse_mode_arg(sys.argv)
    if forced is not None and not has_mode(forced):
        print(f"[bongo] 没有「{forced}」这个造型，可用: {', '.join(m.key for m in list_modes())}")
        forced = None
    mode = get_mode(forced)
    demo = _BongoDemo(pet_dir, mode=mode)
    demo.show()
    print(f"[bongo] 造型「{mode.label}」（{mode.key}）")

    try:
        backend = _start_key_listener(demo.controller)
        if backend:
            # 全局监听接管之后，窗口内的 keyPressEvent 会因为抢到焦点而
            # 再报一次同一个物理键，两边各算一只手，Backspace 就会两只手
            # 一起过来。标记一下，让本地路径让路。
            demo._global_keys = True
            print(f"[bongo] 已接管全局键盘（{backend}），直接敲键盘看爪子")
        else:
            raise RuntimeError("当前平台没有可用的监听后端")
    except Exception as e:
        print(f"[bongo] 全局键盘不可用（{e}）")
        print("[bongo] 请点击窗口，用窗口内按键看效果")

    print("[bongo] 拖动窗口可挪位置，M 换造型，Esc 退出")
    demo.setFocus()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
