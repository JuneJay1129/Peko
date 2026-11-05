"""生成 bongo 模式的钢琴键盘素材（两个八度，15 白键 + 10 黑键）。

朝向和其它造型一致：**整块绕琴键区中心旋转 180°**。宠物是正对着键盘坐的，
观众看到的必然是倒过来的一面——60% 键盘那套就是这么定的（Q 区在右、
Enter 在左、键帽上的字也是倒的）。钢琴跟着转之后，黑键从白键的**下缘**
凸出来，看着像一排琴齿；这是既定朝向的必然结果，别单独把黑键翻正。

每个琴键都是独立元素，id 是 "k" + 编号：
    kw0..kw14  白键，从左到右（旋转**前**的顺序，转完画面左右是反的）
    kb0..kb9   黑键，压在相邻两个白键的交界上
运行时按下哪颗琴键就点亮哪颗，爪子按 boundsOnElement 挪过去。
黑键压在白键上面，高亮时白键的整块高亮会盖掉黑键——重绘顺序见
BongoRenderer.paint_desk 和 BongoMode.raise_caps。

舞台（画布尺寸、8° 倾斜、桌沿分割线）全部来自 bongo_stage：
琴体上沿压在 PROP_TOP 上，白键从桌沿 + PAD 往下长。画布和倾斜与 60% 键盘
一致，但键盘 / 键鼠的素材没有改成这一层，它们保持各自原有的坐标。钢琴的
桌面是自己画的一层（table_svg）、由 BongoRenderer.paint_table 渲染。

用法：python scripts/gen_bongo_piano.py
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

from bongo_stage import CANVAS_H, CANVAS_W, prop_top, table_svg  # noqa: E402
from gen_bongo_keyboard import paw_svg  # noqa: E402

PAD = 6.0                    # 琴身四周留的边
WHITE_N = 15                 # 两个八度 C4–C6 的白键数
U = 24.8                     # 白键宽：15 × 24.8 = 372，画布左右各留 24
GAP = 1.4                    # 白键之间的缝，露出底下的深色，看着像分键线
# 琴体上沿＝桌沿（166，和 60% 键盘同一个高度），键区顶再往下让 PAD。
# 白键高从 96 收到 74：74 + PAD*2 的琴身转 8° 之后右下角落在 278.5，
# 刚好不出画布。以前是 96 高 + 整块抬到 151，比键盘高 21，BB 鼠就被多
# 遮一截——现在从桌沿这条分割线往下长，鼠露出的高度和键盘那套对得上。
KB_TOP = prop_top() + PAD
WHITE_H = 74.0
BLACK_W = 14.0
BLACK_H = 44.0
# 一个八度里黑键跟在哪些白键后面（C D _ F G A _），第二个八度 +7
BLACK_AFTER = (0, 1, 3, 4, 5)

# 深色琴身 + 奶白琴键。键面比琴身亮得多，缩到桌宠尺寸也分得清黑白键；
# 侧壁各压深一档当「厚度」，和 60% 那套键帽同一个做法。
COLORS = {
    "shell": "#1F1F27",
    "shell_in": "#2E2E38",
    "white": "#FFFCF6",
    "white_side": "#DBD3C4",
    "black": "#22222A",
    "black_side": "#3E3E4A",
}

_OX = (CANVAS_W - WHITE_N * U) / 2.0
# 旋转中心＝琴键区正中（白键区矩形中心）。转 180° 等价于
# x' = 2cx - (x + w)、y' = 2cy - (y + h)。
_CX = _OX + WHITE_N * U / 2.0
_CY = KB_TOP + WHITE_H / 2.0


def rot(x: float, y: float, w: float, h: float) -> tuple:
    """绕琴键区中心转 180° 之后的左上角。

    坐标必须逐键算成画布坐标，不能用外层 <g transform>：QSvgRenderer 的
    boundsOnElement 拿的是元素局部坐标、**不含祖先变换**，包一层的话
    高亮和爪子落点会整体偏移到没旋转的位置。
    """
    return 2.0 * _CX - (x + w), 2.0 * _CY - (y + h)


def white_key_svg(i: int) -> str:
    x = _OX + i * U + GAP / 2.0
    w = U - GAP
    rx, ry = rot(x, KB_TOP, w, WHITE_H)
    inset = 1.4
    return (
        f'  <g id="kw{i}">\n'
        f'    <rect x="{rx:.2f}" y="{ry:.2f}" width="{w:.2f}" height="{WHITE_H:.2f}" '
        f'rx="2.6" fill="{COLORS["white_side"]}"/>\n'
        f'    <rect x="{rx + inset:.2f}" y="{ry + inset:.2f}" '
        f'width="{w - inset * 2:.2f}" height="{WHITE_H - inset * 2:.2f}" '
        f'rx="1.8" fill="{COLORS["white"]}"/>\n'
        f'  </g>'
    )


def black_key_svg(i: int, bx: float) -> str:
    """bx 是黑键左边界（相对 _OX，旋转前）。"""
    x = _OX + bx
    rx, ry = rot(x, KB_TOP, BLACK_W, BLACK_H)
    inset = 1.1
    return (
        f'  <g id="kb{i}">\n'
        f'    <rect x="{rx:.2f}" y="{ry:.2f}" width="{BLACK_W:.2f}" height="{BLACK_H:.2f}" '
        f'rx="3.2" fill="{COLORS["black_side"]}"/>\n'
        f'    <rect x="{rx + inset:.2f}" y="{ry + inset:.2f}" '
        f'width="{BLACK_W - inset * 2:.2f}" height="{BLACK_H - inset * 2:.2f}" '
        f'rx="2.2" fill="{COLORS["black"]}"/>\n'
        f'  </g>'
    )


def black_positions() -> list:
    """黑键左边界（相对 _OX，旋转前）：压在相邻两个白键的交界上。"""
    out = []
    for octave in (0.0, 7.0):
        for i in BLACK_AFTER:
            edge = (octave + i + 1.0) * U
            out.append(edge - BLACK_W / 2.0)
    return out


def build() -> str:
    shell_x = _OX - PAD
    shell_y = KB_TOP - PAD
    shell_w = WHITE_N * U + PAD * 2
    shell_h = WHITE_H + PAD * 2
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" width="{CANVAS_W}" height="{CANVAS_H}">',
        "",
        "  <!--",
        "    钢琴键盘，绕琴键区中心旋转 180°（正对宠物，观众看到的是倒的）：",
        "    黑键从白键下缘凸出、右手边的白键在画面左侧。",
        "",
        "    琴键 id：白键 kw0..kw14、黑键 kb0..kb9（前缀 k + 白/黑编号）。",
        "    黑键必须排在白键之后——它压在白键上，顺序反了黑键会被啃掉一半。",
        "  -->",
        "",
        # 和 60% 键盘同一张桌面：上沿就是分割线，琴身压住它 2px
        table_svg(),
        "",
        '  <g id="desk">',
        f'    <rect x="{shell_x:.2f}" y="{shell_y:.2f}" width="{shell_w:.2f}" '
        f'height="{shell_h:.2f}" rx="14" fill="{COLORS["shell"]}"/>',
        f'    <rect x="{shell_x + 2.5:.2f}" y="{shell_y + 2.5:.2f}" '
        f'width="{shell_w - 5:.2f}" height="{shell_h - 5:.2f}" '
        f'rx="11.5" fill="{COLORS["shell_in"]}"/>',
    ]
    for i in range(WHITE_N):
        parts.append(white_key_svg(i))
    for i, bx in enumerate(black_positions()):
        parts.append(black_key_svg(i, bx))
    parts.append("  </g>")
    parts += paw_svg()
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "pets", "BB", "resource", "bongo", "piano.svg",
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(build())
    print(f"{WHITE_N} white + {len(black_positions())} black keys -> {out}")


if __name__ == "__main__":
    main()
