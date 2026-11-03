"""生成 bongo 模式的 60% 键盘 SVG（61 键，5 行）。

朝向是用户定死的：**键盘整体绕中心旋转 180°**。键盘正对着鼠摆（鼠坐在
键盘后面低头看），于是观众看到的是完全倒过来的——Q 区在右、Enter 在左、
数字行跑到底部、底排（空格那排）跑到最上面，键帽上的字也是倒的。

别"优化"成只翻左右：那样字还正着，看着像一把正常键盘被拼错了位置。
字必须跟着倒，所以每个 <text> 都带 rotate(180) 绕键帽中心转。

外壳是中心对称的圆角矩形，转了跟没转一样，不用动；只有键帽区翻。
KEYS 表里写的是宠物视角坐标，py/px 在 key_svg 里一次算完，
手算容易错，也别用外层 <g transform> 包——boundsOnElement 不认祖先变换。

每个键帽都有 id（k 加键名），运行时按下的键能点亮、爪子也能挪过去。
键名表和 `peko/core/bongo_keys.py` 是同一份，别在这里另起一套。

用法：python scripts/gen_bongo_keyboard.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peko.core.bongo_keys import CHAR_CAPS, NAME_CAPS  # noqa: E402

U = 16.0                      # 1u 的像素宽（420 画布下 15u 占 240）
COLS = 15                     # 60% 键盘宽 15u
ROWS = 5.0                    # 五排主键区，不含 F 区
PAD = 6.0                     # 外壳内边距
CANVAS_W, CANVAS_H = 420, 280
# 键盘整体上抬 22。渲染时整块绕 (210, 228) 顺时针转 8°，贴着画布底放的
# 外壳右下角会被甩到 y≈297，超出 280 被窗口切平，看着像多出一个角。
# 抬 22 之后那个角落到 275，四角全在画布内。
# 注意 TILT_CY 保持 228 不动：只要旋转中心跟着一起抬，相对位置就不变，
# 抬多少都白抬。上抬的是键盘，不是旋转中心。
KB_LIFT = 22
# 外壳底边贴着画布底：留一条空隙的话猫屁股会从键盘下面漏出来
KB_TOP = CANVAS_H - int(ROWS * U) - int(PAD) - KB_LIFT
GAP = 2.0                     # 键帽之间留的缝
# 外壳四周一律只留 PAD 这一圈边，不再往底边多拖一截「下巴」。
# 早先这里是 26：担心转 8° 后左下角甩出画布、露出透明三角，就在底边加厚
# 垫住。结果是键盘底下糊着一大片塑料，转完右下角照样被切，反而更像多长出
# 一个角。外壳只要包住键帽区就够，去掉之后是一个规整的圆角矩形。
SHELL_DROP = 0.0

ROW_Y = {"num": 0.0, "qwe": 1.0, "asd": 2.0, "zxc": 3.0, "bottom": 4.0}

# 键帽分类 -> 颜色。奶油糖果风：近白奶油键帽压在奶咖底板上，
# 只留 Enter（草莓粉）和空格（天空蓝）两个大键跳色，像玩具键盘。
#
# 底板一定要比键帽**明显深一档**（#EBD8C2 vs #FFFCF4）。两者都做浅色的话，
# 键帽和底板糊成一片，缩小到桌宠尺寸根本看不出键位。
COLORS = {
    "alpha": "#FFFCF4",     # 字母数字：近白奶油
    "func": "#D5EBDD",      # 功能键：薄荷
    "enter": "#FFC2D1",     # 回车：草莓粉
    "space": "#BFE3F5",     # 空格：天空蓝
    "shell": "#D8C3AB",     # 外壳：深奶咖（露出 2.5px 当描边）
    "shell_in": "#EFE2D2",  # 底板：浅奶咖
    "text": "#8A7460",      # 键帽字：暖灰棕，别用纯黑，太硬
}

# 键帽侧壁：同色系压深一档。键面内缩 1.6px 盖在上面，露出的一圈就是
# 「键帽的厚度」，一颗颗看起来像积木，比纯色块可爱得多。
SIDE = {
    "alpha": "#E5D0B7",
    "func": "#B3D6C2",
    "enter": "#F2A6BC",
    "space": "#9DCDE8",
}

# (label, cap, x, y, w, h, kind)  —— 宠物视角，x/w 单位 u
KEYS: list[tuple] = []


def add(label, x, row, w=1.0, h=1.0, kind="alpha", cap=None):
    """cap 不给就从 label 推：单字符查 CHAR_CAPS，长名字查 NAME_CAPS。"""
    if cap is None:
        if label == "":
            cap = "space"
        else:
            cap = CHAR_CAPS.get(label) or CHAR_CAPS.get(label.lower()) or NAME_CAPS[label.lower()]
    KEYS.append((label, cap, x, ROW_Y[row], w, h, kind))


# 数字行：` 1-0 - = + Backspace（13u + 2u）
for i, k in enumerate("`1234567890-="):
    add(k, i, "num")
add("Backspace", 13, "num", w=2.0, kind="func")

# QWERTY：Tab 1.5 + 12 键 + \ 1.5
add("Tab", 0, "qwe", w=1.5, kind="func")
for i, k in enumerate("QWERTYUIOP[]"):
    add(k, 1.5 + i, "qwe")
add("\\", 13.5, "qwe", w=1.5)

# ASDF：Caps 1.75 + 11 键 + Enter 2.25
add("Caps", 0, "asd", w=1.75, kind="func", cap="caps")
for i, k in enumerate("ASDFGHJKL;'"):
    add(k, 1.75 + i, "asd")
add("Enter", 12.75, "asd", w=2.25, kind="enter")

# ZXCV：Shift 2.25 + 10 键 + Shift 2.75
add("Shift", 0, "zxc", w=2.25, kind="func", cap="lshift")
for i, k in enumerate("ZXCVBNM,./"):
    add(k, 2.25 + i, "zxc")
add("Shift", 12.25, "zxc", w=2.75, kind="func", cap="rshift")

# 底行：1.25 × 3 + 空格 6.25 + 1.25 × 4
add("Ctrl", 0, "bottom", w=1.25, kind="func", cap="lctrl")
add("Win", 1.25, "bottom", w=1.25, kind="func", cap="lwin")
add("Alt", 2.5, "bottom", w=1.25, kind="func", cap="lalt")
add("", 3.75, "bottom", w=6.25, kind="space", cap="space")
add("Alt", 10, "bottom", w=1.25, kind="func", cap="ralt")
add("Win", 11.25, "bottom", w=1.25, kind="func", cap="rwin")
add("Menu", 12.5, "bottom", w=1.25, kind="func", cap="menu")
add("Ctrl", 13.75, "bottom", w=1.25, kind="func", cap="rctrl")


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def key_svg(label: str, cap: str, x: float, y: float, w: float, h: float, kind: str, ox: float, oy: float) -> str:
    # 坐标直接算成画布坐标，**不能**用外层 <g transform> 兜住：
    # QSvgRenderer.boundsOnElement 拿的是元素局部坐标、不含祖先变换，
    # 高亮会盖到别处去。所以 180° 旋转也得在这里逐键算。
    #
    # 绕键帽区中心转 180°：x 和 y 同时镜像。键帽区中心是
    # (ox + COLS*U/2, oy + ROWS*U/2)，所以 x' = COLS - x - w、y' = ROWS - y - h。
    px = (COLS - x - w) * U + ox
    py = (ROWS - y - h) * U + oy
    pw, ph = w * U - GAP, h * U - GAP
    color = COLORS[kind]
    # 长名字要缩字号，否则 Backspace 会顶出键帽
    size = 10.0 if len(label) == 1 else (7.5 if len(label) <= 4 else 7.0)
    if label == "":
        txt = ""
    else:
        # 别用 dominant-baseline="central"：Qt 的 SVG 渲染器不认，字符会整体
        # 跑出键帽；手动按字号下移约 0.36em 才是视觉居中。
        # font-family 也不要写逗号分隔的列表，Qt 会把整串当字体名，直接不出字。
        #
        # rotate 绕**键帽中心**：x/y 不用重算，位置和字形一起转，
        # 转完仍以键帽中心居中，只是字倒过来了。
        cx, cy = px + pw / 2, py + ph / 2
        txt = (
            f'<text x="{cx:.2f}" y="{cy + size * 0.36:.2f}" '
            f'transform="rotate(180 {cx:.2f} {cy:.2f})" '
            f'font-size="{size}" font-family="Segoe UI" fill="{COLORS["text"]}" '
            f'text-anchor="middle">{esc(label)}</text>'
        )
    # 圆角按短边取：宽键（空格 6.25u）跟着用 5 会像一根长条，圆角比例得一致
    rx = min(5.5, ph * 0.28)
    side = SIDE[kind]
    inset = 1.6
    # 三层的顺序：侧壁 → 键面 → 顶部高光。
    # **全部必须落在键帽矩形内**：超出去 boundsOnElement 的 bbox 就变大，
    # 按下时的高亮矩形跟着放大、盖到隔壁键上，爪子定位也会偏。
    return (
        f'  <g id="k{cap}">\n'
        f'    <rect x="{px:.2f}" y="{py:.2f}" width="{pw:.2f}" height="{ph:.2f}" '
        f'rx="{rx:.2f}" fill="{side}"/>\n'
        f'    <rect x="{px + inset:.2f}" y="{py + inset:.2f}" '
        f'width="{pw - inset * 2:.2f}" height="{ph - inset * 2:.2f}" '
        f'rx="{max(rx - 1.2, 1.1):.2f}" fill="{color}"/>\n'
        f'    <rect x="{px + 2.9:.2f}" y="{py + 2.7:.2f}" width="{pw - 5.8:.2f}" '
        f'height="{ph * 0.24:.2f}" rx="{max(rx - 2.0, 1.0):.2f}" '
        f'fill="#FFFFFF" opacity="0.72"/>\n'
        f'    {txt}\n'
        f'  </g>'
    )


def build() -> str:
    kb_w = COLS * U
    kb_h = ROWS * U
    ox = (CANVAS_W - kb_w) / 2
    oy = KB_TOP

    shell_x = ox - PAD
    shell_y = KB_TOP - PAD
    shell_w = kb_w + PAD * 2
    # SHELL_DROP 是旋转后盖住键帽下缘的「下巴」，现在整块键盘上移了，
    # 它完整落在画布里，不再靠窗口裁边藏起来
    shell_h = kb_h + PAD * 2 + SHELL_DROP

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" width="{CANVAS_W}" height="{CANVAS_H}">',
        "",
        "  <!--",
        "    60% 键盘，绕中心旋转 180°（正对宠物，观众看到的是倒的）：",
        "    Q 区在右、Enter 在左、数字行在最下面、空格那排在最上面。",
        "",
        "    每个键 id 是 \"k\"+键名：字母数字用字符本身（ka/k1），符号用英文名",
        "    （ksemicolon/kslash），功能键带左右（klshift/krshift）。同名表见",
        "    peko/core/bongo_keys.py 的 CHAR_CAPS / NAME_CAPS，两边必须一致。",
        "  -->",
        "",
        '  <g id="desk">',
        # 双层做「描边」：外层深奶咖 + 内层奶咖，中间露出一圈 2.5px 的边。
        # 不用 stroke——描边会把 boundsOnElement 撑大，_persp() 的梯形边界
        # 直接按这个 bbox 算，外壳一变宽透视跟着变形。
        f'    <rect x="{shell_x:.2f}" y="{shell_y:.2f}" width="{shell_w:.2f}" '
        f'height="{shell_h:.2f}" rx="19" fill="{COLORS["shell"]}"/>',
        f'    <rect x="{shell_x + 2.5:.2f}" y="{shell_y + 2.5:.2f}" '
        f'width="{shell_w - 5:.2f}" height="{shell_h - 5:.2f}" '
        f'rx="16.5" fill="{COLORS["shell_in"]}"/>',
    ]
    for label, cap, x, y, w, h, kind in KEYS:
        parts.append(key_svg(label, cap, x, y, w, h, kind, ox, oy))
    parts.append("  </g>")
    parts += paw_svg()
    parts.append("</svg>")
    return "\n".join(parts)


# 爪子：SVG 里只是休息位，运行时 BongoRenderer 按 bbox 整体平移，
# 所以改这里等于改「不按键时手放哪」，不影响跟随。
# 直径 30：纯按原图比例算出来是 19（手 77px / 角色 671px × 宠物高 165），
# 但宠物缩到 2/3 后键盘还是 240 宽，19 的爪子落在上面只剩一个小点。
# 30 对键帽 14 是 2.1 倍，会压住一颗半键——这是刻意的：手臂加粗到 13
# （含描边 17）之后，拳头再跟手臂差不多粗，看着就成了「胳膊上套了两个环」，
# 而不是「手」。拳必须明显比臂粗，比例才立得住。
PAW_R = 15.0
# 休息位是**画面坐标**，l/r 永远指画面左边/右边那只爪，不跟键盘一起换。
# 键帽转了 180°，休息位跟着转（原来 160/226，转完是 260/194），
# 再按「l=画面左」把标签换回来就是下面这两个。
# 别直接写 260/194 而不换标签：那样左手会在画面右休息、却去按画面左的键，
# 两条手臂横穿整个键盘交叉成 X。
# y 取 254，比键帽区中线（234）低 20。爪子在 234 时整只手正好贴在键盘
# 上沿上，直径一盖，肩到爪只剩十几像素，手臂完全看不见，像身体上
# 粘了两个圆片。往下沉到第二排，闲置时手臂才露出一截。
# x 以画布中线 210 左右对称各 35：旧值 194/260 的中心落在 227、整体偏右
# 17px，左臂看着贴在身子中间、右臂却快甩到轮廓外。
PAW_REST = {"l": (168.0, 254.0 - KB_LIFT), "r": (252.0, 254.0 - KB_LIFT)}

# 拳头本色取原图那双抱胸圆手的主色 #EEB8B7（扫 560~780 行统计出来的最高频
# 颜色），不是从身体灰里调的——鼠的手本来就是粉的，之前用 #C9C9C9 让人以为
# 是两根粗管子插了两个灰球。
# 肉垫用比本色深一档的 #DD8F8E：本色浅，垫子再浅就糊成一片，看不出哪只按下去。
# 这里只管拳头。手臂（BongoRenderer.ARM_FILL）是身体灰 #C9C9C9——胳膊归身体、
# 手归原图那双粉手，两者刻意不同色，别为了「接缝」把手臂也刷成粉。
PAW_FILL = "#EEB8B7"
PAW_PAD = "#DD8F8E"
PAW_EDGE = "#1A1A1A"


def paw_svg() -> list[str]:
    out = []
    for side, (cx, cy) in PAW_REST.items():
        for down in (False, True):
            rid = f"paw_{side}_{'down' if down else 'rest'}"
            rx, ry = (PAW_R + 2.0, PAW_R - 3.0) if down else (PAW_R, PAW_R)
            out += [
                f'  <g id="{rid}">',
                f'    <ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
                f'fill="{PAW_FILL}" stroke="{PAW_EDGE}" stroke-width="2.4"/>',
                f'    <ellipse cx="{cx}" cy="{cy + ry * 0.18:.1f}" rx="{rx * 0.52:.1f}" '
                f'ry="{ry * 0.44:.1f}" fill="{PAW_PAD}"/>',
                "  </g>",
            ]
    return out


def main() -> None:
    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "pets", "BB", "resource", "bongo", "bongo.svg",
    )
    svg = build()
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"{len(KEYS)} keys -> {out}")


if __name__ == "__main__":
    main()
