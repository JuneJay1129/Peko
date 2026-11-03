"""生成 bongo 模式里那只鼠的身体（趴姿），替代原来的 lieDown 逐帧 PNG。

造型参考「头身一体的胖梨形」：头和身体**不是两个圆拼的**，是一条连续轮廓，
耳朵是轮廓上鼓出来的两个包，两耳之间有一段浅浅的凹。这样看着才像一个实心
的软糖团，而不是雪人。

**分成 #body 和 #head 两个元素**，不是一个整体：
    #body  下半身，画在键盘**后面**（大部分被键盘盖掉）
    #head  上半身 + 五官，画在键盘**前面**
bongocat 里猫的头是压在键盘上沿的（头在近处、键盘在远处），整体画成一层的话
头会被键盘吃掉下巴，看着像从键盘后面缩着脖子。绘制顺序见
peko/ui/bongo.py 的 BongoOverlay.paintEvent。

**分层最麻烦的地方：接缝处不能有黑线。**
轮廓在 y=168 被切成上下两段，两段各自只描自己的那半圈，谁都不画水平的那一刀；
填色由 #head 闭合到 y=168 的弦上补齐。这样切下去是一片连续的颜色，
看不到"头被切了一刀"。

三条比例规矩，改坐标前先看一遍：
1. **上半身压在键盘上沿**。键盘外壳顶边 y=158，切口 168 越过去 10px，
   由上半身盖住键盘（不是反过来），下巴才像搁在键盘上。
2. **腰只比头宽一点点**。参考图里头 540、腰 575，几乎是等宽的直筒，
   鼓太多就成雪人了。
3. **耳朵不许出画布**。耳顶留够 40px 余量。

**不在这里做倾斜**：旋转统一由渲染层的 BongoRenderer._tilt() 做，身体和键盘
共用同一份 TILT_DEG。写进 SVG 的外层 <g transform> 会让 boundsOnElement 取到
没旋转的坐标，头会跟键盘错开。

用法：python scripts/gen_bongo_cat.py
"""
from __future__ import annotations

import os

CANVAS_W, CANVAS_H = 420, 280

BODY_FILL = "#C9C9C9"
EDGE = "#1A1A1A"
PINK = "#F2A8A8"
MUZZLE = "#F7F7F7"

# 中轴。故意写成 196 而不是画布中线 210：整只鼠是绕键盘中心 (210, 213) 转 8° 的，
# 它离旋转中心约 100px，转完会往右飘 100*sin8 ≈ 14px。这里先左移抵掉，
# 转过来才正好压在键盘中线上——写 210 的话看着是歪的。
CX = 196.0

# 轮廓在 y=168 切成上下两段，左右两侧的切点 x（贴着曲线取，别偏太多会露缝）
SPLIT_Y = 168.0
SPLIT_LX, SPLIT_RX = 91.0, 301.0

# —— 侧面参数：想「再侧一点」就调这三个，注意别超过 0.15 ——
# 五官整体相对中轴的左移量（正值 = 往观众左边偏）
FACE_SHIFT = 5.0
# 远侧（画面右）眼睛相对近侧缩小到多少
FAR_EYE = 0.90

# 上半身轮廓：从左侧切点 (86,168) 起，向上绕过头顶，落到右侧切点 (308,168)。
# 两耳之间在 (196,62) 有一个很浅的凹（参考图里只凹下去 25px/1000，别做深，
# 做深了头顶变 M 形，像猫不像熊）。耳朵是轮廓自己鼓出来的包，半径约 27。
TOP_PATH = (
    "M 91 168 "
    "C 90 150 93 128 98 106 "
    "C 99 90 103 72 110 58 "
    "A 32 32 0 0 1 156 57 "
    "C 172 55 184 55 196 56 "
    "C 208 55 220 55 236 57 "
    "A 31 31 0 0 1 280 58 "
    "C 287 72 291 90 292 106 "
    "C 297 128 300 150 301 168"
)

# 下半身轮廓：从右侧切点接着往下，绕到屁股再回到左侧切点。
# 腰只比头宽 12px（参考图 575 对 540），几乎是直筒，鼓了就成雪人。
BOTTOM_PATH = (
    "M 301 168 "
    "C 306 192 306 214 304 236 "
    "C 302 268 294 294 278 306 "
    "C 248 322 144 322 112 306 "
    "C 96 294 88 268 87 236 "
    "C 85 214 86 192 91 168 "
    "Z"
)


def build() -> str:
    # 五官基准点：鼻子略微偏左，其余都相对它派生，改 FACE_SHIFT 整张脸一起转
    nose_x = CX - FACE_SHIFT
    eye_near_x = nose_x - 40.0
    eye_far_x = nose_x + 40.0
    eye_near_rx, eye_near_ry = 14.0, 19.0
    eye_far_rx, eye_far_ry = eye_near_rx * FAR_EYE, eye_near_ry * FAR_EYE
    eye_y = 116.0
    # 眼睛是竖椭圆，跟参考图一样细长
    eye_far_y = eye_y - 2.0

    ear_near = {"cx": CX - 63.0, "cy": 57.0}
    ear_far = {"cx": CX + 62.0, "cy": 56.0}

    return "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" width="{CANVAS_W}" height="{CANVAS_H}">',
        "",
        "  <!-- BB 鼠 · bongo 版：头身一体的梨形，拆成 #body / #head 两层。",
        "       改了轮廓记得重跑脚本，别手改。 -->",
        "",
        "  <!-- 下半身：画在键盘后面，绝大部分由键盘盖掉 -->",
        '  <g id="body">',
        f'    <path d="{BOTTOM_PATH}" fill="{BODY_FILL}"/>',
        f'    <path d="{BOTTOM_PATH}" fill="none" stroke="{EDGE}" stroke-width="8.5" '
        'stroke-linejoin="round"/>',
        "    <!-- 尾巴：从右后侧甩出去 -->",
        '    <path d="M 300 214 C 340 212 356 190 350 168" fill="none" '
        f'stroke="{EDGE}" stroke-width="13" stroke-linecap="round"/>',
        '    <path d="M 300 214 C 340 212 356 190 350 168" fill="none" '
        f'stroke="{PINK}" stroke-width="7" stroke-linecap="round"/>',
        "  </g>",
        "",
        "  <!-- 上半身：画在键盘前面，下巴压在键盘上沿。",
        "       填色闭合到 y=168 的弦上，但描边只走上面的轮廓——",
        "       这样切口是一条直线，不会多出一道黑边。 -->",
        '  <g id="head">',
        f'    <path d="{TOP_PATH} L {SPLIT_RX:.0f} {SPLIT_Y:.0f} '
        f'L {SPLIT_LX:.0f} {SPLIT_Y:.0f} Z" fill="{BODY_FILL}"/>',
        f'    <path d="{TOP_PATH}" fill="none" stroke="{EDGE}" stroke-width="8.5" '
        'stroke-linejoin="round" stroke-linecap="round"/>',
        "",
        "    <!-- 耳朵内侧：同色系压深的粉，远侧那只小一号 -->",
        f'    <ellipse cx="{ear_near["cx"]:.1f}" cy="{ear_near["cy"] + 2:.1f}" '
        f'rx="11" ry="12" fill="{PINK}"/>',
        f'    <ellipse cx="{ear_far["cx"]:.1f}" cy="{ear_far["cy"] + 2:.1f}" '
        f'rx="8" ry="9" fill="{PINK}"/>',
        "",
        "    <!-- 眼睛：竖椭圆 + 左上高光，参考图就是这个形状 -->",
        f'    <ellipse cx="{eye_near_x:.1f}" cy="{eye_y:.1f}" '
        f'rx="{eye_near_rx:.1f}" ry="{eye_near_ry:.1f}" fill="{EDGE}"/>',
        f'    <ellipse cx="{eye_far_x:.1f}" cy="{eye_far_y:.1f}" '
        f'rx="{eye_far_rx:.1f}" ry="{eye_far_ry:.1f}" fill="{EDGE}"/>',
        f'    <ellipse cx="{eye_near_x - 3:.1f}" cy="{eye_y - 6:.1f}" rx="4" ry="5.5" '
        'fill="#FFFFFF"/>',
        f'    <ellipse cx="{eye_far_x - 2.5:.1f}" cy="{eye_far_y - 5.5:.1f}" rx="3.6" ry="5" '
        'fill="#FFFFFF"/>',
        "",
        "    <!-- 口鼻：一整块白色椭圆，里面偏上放一个黑鼻头。",
        "         参考图没有再画嘴线，只有这一个黑椭圆，加了反而老气。",
        "         椭圆底边压在 y=164，留 4px 给切口，别让白边被切平。 -->",
        f'    <ellipse cx="{nose_x:.1f}" cy="150" rx="25" ry="17" fill="{MUZZLE}"/>',
        f'    <ellipse cx="{nose_x:.1f}" cy="142" rx="6.5" ry="4.6" fill="{EDGE}"/>',
        "",
        "    <!-- 胡须：每侧两条短横线，不要画长，长了像猫 -->",
        f'    <path d="M {nose_x - 29:.1f} 145 L {nose_x - 49:.1f} 143 '
        f'M {nose_x - 30:.1f} 154 L {nose_x - 50:.1f} 156" fill="none" '
        f'stroke="{EDGE}" stroke-width="2.4" stroke-linecap="round"/>',
        f'    <path d="M {nose_x + 29:.1f} 145 L {nose_x + 49:.1f} 143 '
        f'M {nose_x + 30:.1f} 154 L {nose_x + 50:.1f} 156" fill="none" '
        f'stroke="{EDGE}" stroke-width="2.4" stroke-linecap="round"/>',
        "  </g>",
        "</svg>",
    ])


def main() -> None:
    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "pets", "BB", "resource", "bongo", "body.svg",
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(build())
    print(f"body -> {out}")


if __name__ == "__main__":
    main()
