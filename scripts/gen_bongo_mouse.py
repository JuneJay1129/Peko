"""生成「键鼠同摆」素材：强透视小键盘（右下）+ 鼠标垫鼠标（左下）+ 斜切桌面。

布局照 bongocat 原版 mouse 版：鼠标在画面左、键盘在画面右，斜切的桌面接住
下半个画面。三处和 60% 不一样：

- 键盘被单应投影压进梯形（远边 87 宽、近边 139 宽），行往右上斜、列往左下
  斜。投影在生成阶段就烘进坐标，不在绘制时用 quadToQuad——那样
  boundsOnElement 给的 bbox 是未变换的矩形，键帽高亮和爪子落点全会偏。
- 键位仍是 12.5u × 4 排 40 键，但每颗只有十来个像素，键帽上的字母在这个尺寸
  下是噪点，所以不画字，只留一圈 side 色当厚度。
- 键位绕键帽区中心**转 180°**（Tab 行在近边），和 60% 那套同构；鼠标长轴
  则改成朝远端（头朝屏幕方向），按键在远端、手压住后半截。
- 键盘、鼠标、爪子都带落地阴影，且整块构图的旋转交给渲染层的 tilt_deg=8。

用法：python scripts/gen_bongo_mouse.py
"""
from __future__ import annotations

import html
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

# 配色和键帽画法复用 60% 那套，切造型不能像换了皮
from gen_bongo_keyboard import COLORS, SIDE, PAW_EDGE, PAW_FILL, PAW_PAD  # noqa: E402

CANVAS_W, CANVAS_H = 420, 280
COLS, ROWS = 12.5, 4.0

# 桌面：一条从左上往右下斜的边，下面全是桌面。
# 四边都出画（-70 / 490 / y=380）：整体转 8° 之后画布两下角仍在桌面里，
# 否则右下角会露出一块透明，像桌面被啃掉一角。
TABLE_EDGE = ((-70.0, 128.0), (490.0, 170.0))
TABLE_ANGLE = math.degrees(
    math.atan2(TABLE_EDGE[1][1] - TABLE_EDGE[0][1], TABLE_EDGE[1][0] - TABLE_EDGE[0][0])
)
_T = math.radians(TABLE_ANGLE)
# 桌沿方向（沿桌边往右）和它的法线（指向画布下方 = 靠近观众）。
D_AXIS = (math.cos(_T), math.sin(_T))
N_AXIS = (-math.sin(_T), math.cos(_T))


def _quad(cx, cy, near_w, far_w, depth):
    """在桌沿坐标系里摆一块「远窄近宽」的矩形，近边自动和桌沿平行。

    键盘、垫子、鼠标全都用这一支摆：手写四角坐标的话，任何一次微调都会
    把平行关系调歪——键盘底边和桌沿之间差 3° 就已经很显眼了。
    """
    nx, ny = cx + N_AXIS[0] * depth / 2.0, cy + N_AXIS[1] * depth / 2.0
    fx, fy = cx - N_AXIS[0] * depth / 2.0, cy - N_AXIS[1] * depth / 2.0
    dx, dy = D_AXIS
    return [
        (fx - dx * far_w / 2.0, fy - dy * far_w / 2.0),
        (fx + dx * far_w / 2.0, fy + dy * far_w / 2.0),
        (nx + dx * near_w / 2.0, ny + dy * near_w / 2.0),
        (nx - dx * near_w / 2.0, ny - dy * near_w / 2.0),
    ]


def _at(cx, cy, forward=0.0, side=0.0):
    """在桌沿坐标系里相对某点取位置：forward 正 = 靠近观众，side 正 = 沿桌沿往右。"""
    return (
        cx + N_AXIS[0] * forward + D_AXIS[0] * side,
        cy + N_AXIS[1] * forward + D_AXIS[1] * side,
    )


# 三块板用同一个「远边 : 近边」收窄比。沿桌沿的那两条边本来就平行，
# 收窄比再一致，左右两条侧边就朝同一个灭点倒，看着才像同一张桌上的一组
# 东西——之前键盘 0.64、垫子 0.91，几块板各倒各的，怎么摆都别扭。
NEAR_FAR = 0.76

# 键盘：整块贴到桌沿内侧（靠近观众这一侧），底边（空格那条）和桌沿平行。
# 比上一版小一圈（近边 172 vs 206）：40% 键盘本来就小，占半个画面太抢戏。
KB_CENTER = (300.0, 185.0)
KB_QUAD = _quad(*KB_CENTER, near_w=166.0, far_w=166.0 * NEAR_FAR, depth=66.0)

# 鼠标垫：左下，**上沿压在桌沿上**（和键盘一个待遇），右沿到宠物身侧。
# 之前垫子浮在桌面中间、离桌沿还有半块垫子的距离，看着像悬空的贴纸。
# 尺寸再收一圈、整体右移靠向身体：原来的垫子占掉左下整个角，离宠物还有
# 一段桌面空隙，看着像两件不相干的东西各摆一处。
PAD_CENTER = (108.0, 184.0)
PAD_QUAD = _quad(*PAD_CENTER, near_w=140.0, far_w=140.0 * NEAR_FAR, depth=84.0)

# 鼠标：长轴顺着桌沿法线（头朝观众、尾朝宠物），平放俯视。
# 宠物视角下手指在前端按左右键、手掌压住靠身体那一半，所以按键在近端。
# 前端比尾端宽——反过来就是一支甜筒，一眼认不出是鼠标。
# 中心和垫子同一个点：鼠标在垫子正中，上下各留 15，不会爬到桌沿上。
MOUSE_CENTER = (108.0, 184.0)
MOUSE_QUAD = _quad(*MOUSE_CENTER, near_w=36.0, far_w=36.0 * NEAR_FAR, depth=54.0)
# 按键占鼠标高度的比例（0 是远端/尾部，1 是近端/头部）。手盖住这个比例以下。
KEY_BAND = (0.48, 0.90)

# 压在鼠标上的手：比普通爪大一圈，但不能大过鼠标本身——21×18 时
# 手几乎盖满整个鼠标，只剩一个黄块露在外面，看着像贴在胶囊上的球。
HAND_RX, HAND_RY = 17.0, 14.0
HAND_CX, HAND_CY = _at(*MOUSE_CENTER, forward=-18.0)

TABLE_FILL = "#F3E8D8"
TABLE_EDGE_COLOR = "#DFCBB2"
PAD_FILL = "#D6C5AE"
PAD_EDGE = "#BCA386"
SHELL_FILL = "#E7D5BE"

KEY_GAP = 1.3      # 键帽间隙（画面像素，远排再乘透视补偿系数）
SHELL_PAD = 4.5    # 外壳比键区外扩多少（单层，不再套第二圈）
HIGHLIGHT = "#FFD166"
SHADOW = "#000000"
SHADOW_OPACITY = 0.07

# 40% 布局里 Enter 用共用色 #F2A6BC 太扎眼（一整块高饱和粉孤零零在键区），
# 压一档饱和度，和奶咖底子还能对上。
FILL_OVERRIDE = {"enter": "#F0B7C4"}

# 打字手和握鼠标那只手**同一个尺寸**。原来 12/12 对 17/14，画面里一眼能
# 看出两只手一大一小——同一个身体上的两只手不该有大小差。
PAW_RX, PAW_RY = HAND_RX, HAND_RY
# 休息位：画面坐标，l/r 永远指画面左/右那只爪。画面左那只被鼠标手顶掉，
# 但 #paw_l_* 仍要画——渲染层按 id 取模板，缺了这个 id 会直接报错。
# 画面右手（打字那只）待机就搭在空格键上：取 #kspace 的 bbox 中心（键位转了
# 180°，空格落在远边）。
# 真正决定落点的是 mode 的 rest_cap_r="space"，走 cap_center + paw_y_offset，
# 和真按空格同一个点；这里只是素材模板位置，别让 fallback 偏出去。
PAW_REST = {
    "l": (HAND_CX, HAND_CY),
    "r": (299.0, 159.0),
}

KEYS: list[tuple] = []


def add(label, cap, x, row, w=1.0, kind="alpha"):
    KEYS.append((label, cap, x, float(row), w, kind))


add("Tab", "tab", 0.0, 0, 1.5, "func")
for i, k in enumerate("QWERTYUIOP"):
    add(k, k.lower(), 1.5 + i, 0)
add("\\", "backslash", 11.5, 0)

add("Caps", "caps", 0.0, 1, 1.75, "func")
for i, k in enumerate("ASDFGHJKL"):
    add(k, k.lower(), 1.75 + i, 1)
add("Enter", "enter", 10.75, 1, 1.75, "enter")

add("Shift", "lshift", 0.0, 2, 2.5, "func")
for i, k in enumerate("ZXCVBNM"):
    add(k, k.lower(), 2.5 + i, 2)
for i, (label, cap) in enumerate(((",", "comma"), (".", "period"), ("/", "slash"))):
    add(label, cap, 9.5 + i, 2)

add("Ctrl", "lctrl", 0.0, 3, 1.5, "func")
add("Win", "lwin", 1.5, 3, 1.25, "func")
add("Alt", "lalt", 2.75, 3, 1.25, "func")
add("", "space", 4.0, 3, 5.0, "space")
add("Alt", "ralt", 9.0, 3, 1.25, "func")
add("Ctrl", "rctrl", 10.25, 3, 2.25, "func")


# ---- 透视 ----
def homography(quad):
    """单位正方形 -> 任意四边形的单应矩阵，返回 map(u, v) -> (x, y)。

    只用仿射（平行四边形）的话远排和近排一样宽，键盘像一块斜放贴纸；
    单应才有真正的近大远小，梯形外壳和键帽的收缩是自洽的。
    """
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    dx1, dx2 = x1 - x2, x3 - x2
    dy1, dy2 = y1 - y2, y3 - y2
    sx, sy = x0 - x1 + x2 - x3, y0 - y1 + y2 - y3
    den = dx1 * dy2 - dy1 * dx2
    if abs(den) < 1e-9:
        g = h = 0.0
    else:
        g = (sx * dy2 - dx2 * sy) / den
        h = (dx1 * sy - sx * dy1) / den
    a, b, c = x1 - x0 + g * x1, x3 - x0 + h * x3, x0
    d, e, f = y1 - y0 + g * y1, y3 - y0 + h * y3, y0

    def map_uv(u, v):
        w = g * u + h * v + 1.0
        return ((a * u + b * v + c) / w, (d * u + e * v + f) / w)

    return map_uv


def quad_path(pts) -> str:
    p = " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
    return f"M {p} Z"


def round_quad(mp, u0, v0, u1, v1, k=0.22) -> str:
    """把 [u0,u1]×[v0,v1] 这块映射后的四边形画成圆角 path。

    圆角是在 uv 空间切角再二次贝塞尔过角点：透视之后四个角的角度都不一样，
    直接在画布坐标里按半径倒角会一边圆一边尖。
    """
    tl, tr = mp(u0, v0), mp(u1, v0)
    br, bl = mp(u1, v1), mp(u0, v1)
    corners = [(tl, tr, bl), (tr, br, tl), (br, bl, tr), (bl, tl, br)]
    out = []
    for i, (corner, nxt, prv) in enumerate(corners):
        ax = corner[0] + (prv[0] - corner[0]) * k
        ay = corner[1] + (prv[1] - corner[1]) * k
        bx = corner[0] + (nxt[0] - corner[0]) * k
        by = corner[1] + (nxt[1] - corner[1]) * k
        if i == 0:
            out.append(f"M {ax:.2f} {ay:.2f}")
        else:
            out.append(f"L {ax:.2f} {ay:.2f}")
        out.append(
            f"Q {corner[0]:.2f} {corner[1]:.2f} {bx:.2f} {by:.2f}"
        )
    out.append("Z")
    return " ".join(out)


def shrink(pts, px):
    """四边形四角朝质心收 px 像素，做出键帽之间的缝。"""
    cx = sum(p[0] for p in pts) / 4.0
    cy = sum(p[1] for p in pts) / 4.0
    out = []
    for x, y in pts:
        dx, dy = cx - x, cy - y
        d = (dx * dx + dy * dy) ** 0.5 or 1.0
        s = max(0.0, (d - px)) / d
        out.append((cx - dx * s, cy - dy * s))
    return out


def _label_svg(face, label):
    """键帽上的字母：绕自己中心转 180°，并且跟键盘一起斜。

    键盘是**宠物视角**（键位整体转 180°），所以字母对观众是倒着的；
    键帽本身又相对桌沿倾了 TABLE_ANGLE，两样叠加才是「和键盘同样的倾斜」。
    字号按键帽实际尺寸自适应：近排键帽 15 高、远排只有 10，写死 9 会把
    远排的字顶出键帽，写死 6 近排又是一片糊。
    """
    if not label:
        return ""
    cx = sum(p[0] for p in face) / 4.0
    cy = sum(p[1] for p in face) / 4.0
    fmid_x = (face[0][0] + face[1][0]) / 2.0
    fmid_y = (face[0][1] + face[1][1]) / 2.0
    nmid_x = (face[2][0] + face[3][0]) / 2.0
    nmid_y = (face[2][1] + face[3][1]) / 2.0
    h = math.hypot(nmid_x - fmid_x, nmid_y - fmid_y)
    w = math.hypot(face[1][0] - face[0][0], face[1][1] - face[0][1])
    size = min(h * 0.66, w * 2.0 / max(1, len(label)), 9.5)
    size = max(5.4, size)
    return (
        f'    <text x="{cx:.2f}" y="{cy + size * 0.36:.2f}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{size:.2f}" '
        f'font-weight="bold" fill="{COLORS["text"]}" text-anchor="middle" '
        f'transform="rotate({180.0 + TABLE_ANGLE:.2f} {cx:.2f} {cy:.2f})">'
        f"{html.escape(label)}</text>\n"
    )


def key_svg(label, cap, x, row, w, kind):
    """返回 (键帽, 高亮) 两段 SVG。

    高亮是**独立元素**、不放进 #desk：键帽是透视后的梯形，渲染层只拿得到
    boundsOnElement 的 AABB，拿 AABB 盖一层圆角矩形会把空格键（5u 宽、
    AABB 64×36）涂成一大块黄斑，压住旁边七八个键。独立元素按自身 bbox
    1:1 渲染，形状跟键帽严丝合缝。

    键位**绕键帽区中心转 180°**（和 gen_bongo_keyboard.py 同一个语义）：
    u、v 同时镜像，Tab 行落到近边、空格落到远边。这里在 uv 空间翻，
    透视会自动跟着走，不用逐键算画布坐标。
    """
    u0, u1 = (COLS - x - w) / COLS, (COLS - x) / COLS
    v0, v1 = (ROWS - row - 1.0) / ROWS, (ROWS - row) / ROWS
    quad = [KB_MAP(u0, v0), KB_MAP(u1, v0), KB_MAP(u1, v1), KB_MAP(u0, v1)]
    # 键缝按透视补偿：远排被单应缩到 0.63，固定 1.3px 的缝到上面只剩 0.8，
    # 一片糊。按 v 中心线性加粗：近排 1.4、远排 1.06。
    vc = (v0 + v1) / 2.0
    gap = KEY_GAP * (1.0 + 0.5 * vc)
    face = shrink(quad, gap * 0.5)
    # 键帽厚度：整块往下挪 1.4px 垫在下面，露出的那一圈就是 side 色。
    # 180° 只翻键位不翻键帽朝向，厚度仍然朝画面下方（近端）。
    side = shrink([(px, py + 1.4) for px, py in quad], gap * 0.5)
    cap_svg = (
        f'  <g id="k{cap}">\n'
        f'    <path d="{quad_path(side)}" fill="{SIDE[kind]}"/>\n'
        f'    <path d="{quad_path(face)}" fill="{FILL_OVERRIDE.get(cap, COLORS[kind])}"/>\n'
        f"{_label_svg(face, label)}"
        f"  </g>"
    )
    hl = f'  <path id="h{cap}" d="{quad_path(face)}" fill="{HIGHLIGHT}"/>'
    return cap_svg, hl


KB_MAP = homography(KB_QUAD)
PAD_MAP = homography(PAD_QUAD)
MOUSE_MAP = homography(MOUSE_QUAD)


def _mx(u, v):
    return MOUSE_MAP(u, v)[0]


def _my(u, v):
    return MOUSE_MAP(u, v)[1]


def build() -> str:
    (tx0, ty0), (tx1, ty1) = TABLE_EDGE
    # 桌面四边都出画（x 已经取到 ±70/490，底边再压到 380）：
    # 整块绕 (210,228) 转 8° 之后，画布两下角仍然落在桌面里。
    table = quad_path([(tx0, ty0), (tx1, ty1), (tx1, 380.0), (tx0, 380.0)])

    # 外壳四角（单层，外扩 4.5）：键盘阴影直接用它偏移，绕开圆角——
    # 阴影本来就只在键盘底下露出 2~5px 的边。
    shell = [
        KB_MAP(u, v)
        for u, v in ((-0.031, -0.062), (1.031, -0.062), (1.031, 1.062), (-0.031, 1.062))
    ]
    kb_shadow = quad_path([(x + 2.5, y + 5.0) for x, y in shell])
    mouse_shadow = quad_path([(x + 2.0, y + 4.0) for x, y in MOUSE_QUAD])

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" width="{CANVAS_W}" height="{CANVAS_H}">',
        "",
        "  <!-- 键鼠同摆：鼠标垫（左下）+ 强透视键盘（右下）+ 斜切桌面。",
        "       投影直接烘在坐标里，不使用祖先 transform。 -->",
        "",
        f'  <path id="table" d="{table}" fill="{TABLE_FILL}" '
        f'stroke="{TABLE_EDGE_COLOR}" stroke-width="3"/>',
        "",
        f'  <path id="pad" d="{round_quad(PAD_MAP, 0.0, 0.0, 1.0, 1.0, 0.07)}" '
        f'fill="{PAD_FILL}" stroke="{PAD_EDGE}" stroke-width="2.5"/>',
        "",
        "  <!-- 鼠标：头朝观众（近端窄）、尾朝宠物，手掌从远端压住后半截。",
        "       中缝 + 滚轮是「这是个鼠标」的唯一线索，没有它们一块白板挂两个黄块",
        "       只会被当成耗材。滚轮在中缝靠身体那一头，按键才朝向观众。 -->",
        '  <g id="mouse">',
        f'    <path d="{mouse_shadow}" fill="{SHADOW}" opacity="{SHADOW_OPACITY}"/>',
        f'    <path d="{round_quad(MOUSE_MAP, 0.0, 0.0, 1.0, 1.0, 0.28)}" '
        f'fill="#FFFCF4" stroke="{COLORS["text"]}" stroke-width="2"/>',
        "    <!-- 左右键的「键面」常驻：不然不按的时候就是一块白板，",
        "         看不出这是个鼠标。按下时再由 mouse_l / mouse_r 盖成黄色 -->",
        f'    <path d="{round_quad(MOUSE_MAP, 0.07, 0.46, 0.47, 0.92, 0.18)}" '
        f'fill="#F7F0E3" stroke="{COLORS["text"]}" stroke-width="0.9"/>',
        f'    <path d="{round_quad(MOUSE_MAP, 0.53, 0.46, 0.93, 0.92, 0.18)}" '
        f'fill="#F7F0E3" stroke="{COLORS["text"]}" stroke-width="0.9"/>',
        f'    <ellipse cx="{_mx(0.5, 0.47):.2f}" cy="{_my(0.5, 0.47):.2f}" '
        f'rx="2.2" ry="3.0" fill="{COLORS["func"]}" stroke="{COLORS["text"]}" '
        'stroke-width="1.1"/>',
        "  </g>",
        "",
        "  <!-- 左右键：只画在露出来的那段（近端 40%），按下才 render -->",
        f'  <path id="mouse_l" d="{round_quad(MOUSE_MAP, 0.07, KEY_BAND[0], 0.47, KEY_BAND[1], 0.18)}" '
        'fill="#FFD166"/>',
        f'  <path id="mouse_r" d="{round_quad(MOUSE_MAP, 0.53, KEY_BAND[0], 0.93, KEY_BAND[1], 0.18)}" '
        'fill="#FFD166"/>',
        "",
        "  <!-- 键盘阴影独立成元素：塞进 #desk 里会把 desk 的 bbox 撑大，",
        "       而 paint_desk 用 bbox 当目标矩形，整块键盘会跟着变位置 -->",
        f'  <path id="kb_shadow" d="{kb_shadow}" fill="{SHADOW}" opacity="{SHADOW_OPACITY}"/>',
        "",
        '  <g id="desk">',
        f'    <path d="{round_quad(KB_MAP, -0.031, -0.062, 1.031, 1.062, 0.10)}" '
        f'fill="{SHELL_FILL}"/>',
    ]
    highlights = []
    for label, cap, x, y, w, kind in KEYS:
        cap_svg, hl = key_svg(label, cap, x, y, w, kind)
        parts.append(cap_svg)
        highlights.append(hl)
    parts.append("  </g>")
    # 高亮放在 #desk 外面：只有按下时才由渲染层单独 render
    parts.append("")
    parts.append("  <!-- 键帽高亮：平时不画，按下才 render -->")
    parts += highlights
    parts += paw_svg()
    parts.append("</svg>")
    return "\n".join(parts)


def _paw(rid: str, cx: float, cy: float, rx: float, ry: float) -> list[str]:
    # 没有手臂之后，手和键帽之间只剩一圈描边，看着是贴纸。
    # 描边底下垫一层同心的软阴影，手就"压"在键帽上了。
    # 阴影跟爪同组：渲染层平移卷组时会一起走，不用另算坐标。
    return [
        f'  <g id="{rid}">',
        f'    <ellipse cx="{cx + 0.8:.1f}" cy="{cy + 1.8:.1f}" '
        f'rx="{rx * 0.96:.1f}" ry="{ry * 0.9:.1f}" '
        f'fill="{SHADOW}" opacity="{SHADOW_OPACITY}"/>',
        f'    <ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
        f'fill="{PAW_FILL}" stroke="{PAW_EDGE}" stroke-width="2.4"/>',
        f'    <ellipse cx="{cx:.1f}" cy="{cy + ry * 0.18:.1f}" rx="{rx * 0.52:.1f}" '
        f'ry="{ry * 0.44:.1f}" fill="{PAW_PAD}"/>',
        "  </g>",
    ]


def paw_svg() -> list[str]:
    out = []
    for side, (cx, cy) in PAW_REST.items():
        for down in (False, True):
            rid = f"paw_{side}_{'down' if down else 'rest'}"
            rx, ry = (PAW_RX, PAW_RY - 2.0) if down else (PAW_RX, PAW_RY)
            out += _paw(rid, cx, cy, rx, ry)
    # 握鼠标的手：比普通爪大一圈，压住鼠标下半截
    out += _paw("paw_mouse", HAND_CX, HAND_CY, HAND_RX, HAND_RY)
    return out


def main() -> None:
    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "pets", "BB", "resource", "bongo", "bongo_mouse.svg",
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(build())
    print(f"{len(KEYS)} keys -> {out}")


if __name__ == "__main__":
    main()
