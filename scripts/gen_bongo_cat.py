"""生成 bongo 模式里那只鼠的身体（趴姿），替代原来的 lieDown 逐帧 PNG。

原素材是正面端坐的证件照姿势，放进键盘场景里像被人拎着；bongocat 那套
是**趴在桌面上、头扁扁地压在键盘后面探出来**，所以这里重画一版。

三条比例规矩，改坐标前先看一遍：
1. **头必须压在键盘上**。键盘外壳顶边 y=158（KB_TOP 164 减 PAD 6），头的
   下缘要越过这条线，让键盘吃掉一截，否则下巴和键盘之间留一条缝，
   整只鼠像被吊在半空。
2. **肩膀只露一窄条**。身体比头宽得有限（每侧约 30px），再宽就成雪人了；
   身体顶边压在头中线附近，剩下的全被键盘盖掉。
3. **耳朵不许出画布**。耳朵顶端至少留 20px 余量，耳朵底边要压进头上缘
   以内，否则圆会浮在头顶旁边，像被剪下来贴上去的。

侧面靠三个小差值叠出来（不大改轮廓）：远耳小一点、远眼小一点、五官整体
往左让一点。差太大会显得头是歪的，所以三个值都压在 15% 以内。

描边用「先给所有形状描一圈粗边、再整体填色」，头和身体交界处不会留黑线，
合并成一条外轮廓。

用法：python scripts/gen_bongo_cat.py
"""
from __future__ import annotations

import os

CANVAS_W, CANVAS_H = 420, 280

BODY_FILL = "#C9C9C9"
EDGE = "#1A1A1A"
PINK = "#F2A8A8"
MUZZLE = "#F7F7F7"

# —— 侧面参数：想「再侧一点」就调这三个，注意别超过 0.15 ——
# 五官整体相对头中心的左移量（正值 = 往观众左边偏）
FACE_SHIFT = 7.0
# 远侧（画面右）眼睛相对近侧缩小到多少
FAR_EYE = 0.88
# 远侧耳朵相对近侧缩小到多少
FAR_EAR = 0.84

# 头：宽 252、高 120。键盘外壳宽 342，头要占到大半，才有 bongocat 那种
# 「脸怼在屏幕上」的压迫感；小头配大键盘会显得鼠坐得很远。
# 下缘 165 压过键盘外壳顶 158，键盘吃掉一截，下巴贴在键盘上；上缘 45 留耳朵。
HEAD_CX, HEAD_CY, HEAD_RX, HEAD_RY = 210.0, 100.0, 126.0, 65.0

# 近侧（画面左）耳朵
EAR_NEAR = {"cx": 118.0, "cy": 46.0, "r": 29.0}
# 远侧（画面右）耳朵：小一点、靠上一点，圆心略往头里收，
# 让耳朵底边压进头上缘（x=302 处上缘 y≈57），才连得住。
EAR_FAR = {"cx": 302.0, "cy": 42.0, "r": 29.0 * FAR_EAR}

# 身体：56..364，每侧比头（84..336）只宽 28。
# rx 取 64，让 y=158 那一行基本还是全宽——可见的就这 40px，
# 圆角再大就成了斜肩，肩膀会显得很窄。
BODY = {"x": 56, "y": 110, "width": 308, "height": 180, "rx": 64}

# 外轮廓（会先整体描边再整体填充）
SILHOUETTE = [
    ("rect", BODY),
    ("ellipse", {"cx": HEAD_CX, "cy": HEAD_CY, "rx": HEAD_RX, "ry": HEAD_RY}),
    ("circle", EAR_NEAR),
    ("circle", EAR_FAR),
]


def _attr(attrs: dict, extra: str = "") -> str:
    body = " ".join(
        f'{k}="{v:.2f}"' if isinstance(v, float) else f'{k}="{v}"'
        for k, v in attrs.items()
    )
    return f"{body} {extra}".strip()


def _shape(kind: str, attrs: dict, extra: str = "") -> str:
    return f"    <{kind} {_attr(attrs, extra)}/>"


def build() -> str:
    # 五官基准点：鼻子略微偏左，其余都相对它派生，改 FACE_SHIFT 整张脸一起转
    nose_x = HEAD_CX - FACE_SHIFT
    eye_near_x = nose_x - 42.0
    eye_far_x = nose_x + 42.0
    eye_near_rx, eye_near_ry = 17.5, 21.0
    eye_far_rx, eye_far_ry = eye_near_rx * FAR_EYE, eye_near_ry * FAR_EYE
    eye_y = 103.0
    # 远侧眼睛略高一点点，透视上像被"收"进去
    eye_far_y = eye_y - 3.0

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" width="{CANVAS_W}" height="{CANVAS_H}">',
        "",
        "  <!-- BB 鼠 · bongo 版：趴姿。改了轮廓记得重跑脚本，别手改。 -->",
        "",
        "  <!-- 1. 合并外轮廓：先把所有形状描一圈粗边… -->",
        '  <g fill="none" stroke="' + EDGE + '" stroke-width="7" stroke-linejoin="round">',
    ]
    for kind, attrs in SILHOUETTE:
        parts.append(_shape(kind, attrs))
    parts += [
        "  </g>",
        "",
        "  <!-- 2. …再整体填色，把内部的边盖掉，头和身体就长成一体了 -->",
        '  <g fill="' + BODY_FILL + '">',
    ]
    for kind, attrs in SILHOUETTE:
        parts.append(_shape(kind, attrs))
    parts += [
        "  </g>",
        "",
        "  <!-- 3. 耳朵内侧：远侧那只小一号 -->",
        f'  <ellipse cx="{EAR_NEAR["cx"]:.1f}" cy="{EAR_NEAR["cy"] + 2:.1f}" '
        f'rx="14" ry="15" fill="{PINK}"/>',
        f'  <ellipse cx="{EAR_FAR["cx"]:.1f}" cy="{EAR_FAR["cy"] + 2:.1f}" '
        f'rx="9" ry="9.5" fill="{PINK}"/>',
        "",
        "  <!-- 4. 尾巴：从身体右后侧甩出去，别贴着键盘边缘横过来 -->",
        '  <path d="M 338 206 C 380 202 398 180 392 156" fill="none" '
        f'stroke="{EDGE}" stroke-width="15" stroke-linecap="round"/>',
        '  <path d="M 338 206 C 380 202 398 180 392 156" fill="none" '
        f'stroke="{PINK}" stroke-width="9" stroke-linecap="round"/>',
        "",
        "  <!-- 5. 口鼻部：跟着鼻子左移，右半边留得比左半边多才是侧面 -->",
        f'  <ellipse cx="{nose_x:.1f}" cy="136" rx="33" ry="19" fill="{MUZZLE}" '
        f'stroke="{EDGE}" stroke-width="3"/>',
        "",
        "  <!-- 6. 腮红：远侧更小更靠上 -->",
        f'  <ellipse cx="{nose_x - 72:.1f}" cy="135" rx="16" ry="9" fill="{PINK}" '
        f'opacity="0.65"/>',
        f'  <ellipse cx="{nose_x + 70:.1f}" cy="129" rx="12" ry="7.5" fill="{PINK}" '
        f'opacity="0.65"/>',
        "",
        "  <!-- 7. 眼睛：近侧略大、远侧略小略高，差太大就看着像画歪了 -->",
        f'  <ellipse cx="{eye_near_x:.1f}" cy="{eye_y:.1f}" '
        f'rx="{eye_near_rx:.1f}" ry="{eye_near_ry:.1f}" fill="{EDGE}"/>',
        f'  <ellipse cx="{eye_far_x:.1f}" cy="{eye_far_y:.1f}" '
        f'rx="{eye_far_rx:.1f}" ry="{eye_far_ry:.1f}" fill="{EDGE}"/>',
        f'  <circle cx="{eye_near_x + 5:.1f}" cy="{eye_y - 8:.1f}" r="5.0" '
        'fill="#FFFFFF"/>',
        f'  <circle cx="{eye_far_x + 4:.1f}" cy="{eye_far_y - 7:.1f}" r="4.4" '
        'fill="#FFFFFF"/>',
        "",
        "  <!-- 8. 鼻头 + 嘴：鼻子偏左，整张脸就跟着偏过去了 -->",
        f'  <ellipse cx="{nose_x:.1f}" cy="125" rx="7.5" ry="5.5" fill="{EDGE}"/>',
        f'  <path d="M {nose_x:.1f} 131 L {nose_x:.1f} 137 '
        f'M {nose_x:.1f} 137 C {nose_x - 7:.1f} 144 {nose_x - 16:.1f} 144 '
        f'{nose_x - 21:.1f} 139 '
        f'M {nose_x:.1f} 137 C {nose_x + 7:.1f} 144 {nose_x + 16:.1f} 144 '
        f'{nose_x + 21:.1f} 139" fill="none" stroke="{EDGE}" '
        f'stroke-width="3.2" stroke-linecap="round"/>',
        "",
        "  <!-- 9. 胡须：左边短、右边长，符合侧身的透视；起点贴在口鼻边缘 -->",
        f'  <path d="M {nose_x - 31:.1f} 132 L {nose_x - 80:.1f} 124 '
        f'M {nose_x - 31:.1f} 142 L {nose_x - 82:.1f} 146" fill="none" '
        f'stroke="{EDGE}" stroke-width="2.4" stroke-linecap="round" opacity="0.75"/>',
        f'  <path d="M {nose_x + 31:.1f} 132 L {nose_x + 88:.1f} 122 '
        f'M {nose_x + 31:.1f} 142 L {nose_x + 92:.1f} 144" fill="none" '
        f'stroke="{EDGE}" stroke-width="2.4" stroke-linecap="round" opacity="0.75"/>',
        "</svg>",
    ]
    return "\n".join(parts)


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
