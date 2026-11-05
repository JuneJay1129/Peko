"""Bongo 新造型的舞台：画布、倾斜、桌沿分割线。

为什么要有这一层：每份素材各画各的话，BB 鼠露多高、道具从哪往下长，全看
那份素材自己的手感——钢琴的琴身原本比 60% 键盘高出 21，鼠就被多遮一截。
把「一条桌沿」抽出来，新造型按同一套坐标摆，就不会再各算一遍。

钢琴定死一条线：画面绕 (210, 228) 顺时针转 8° 之后，**桌沿就是分割线**。
线以上是 BB 鼠区域（body.svg，不缩放、不位移），线以下是操作区域（琴键）。
渲染顺序 body → table → desk → head 决定了这条线怎么盖：桌面挡住鼠的下半身，
琴键再压在桌面上，头最后画，下巴压在琴身上沿。

**注意**：60% 键盘（bongo.svg）和键鼠（bongo_mouse.svg）没有用这一层，
它们仍是各自的老坐标系 + 各自的 body_dy / body_scale，动这边不影响它们。
新造型照钢琴的做法：素材沿用 420×280 + table_path()，道具从 PROP_TOP 往下摆。

素材里这些坐标都是**未倾斜**的：8° 由渲染层统一转（BongoRenderer._tilt），
素材自己不要再转一次，否则和桌沿的斜度对不上。
"""
from __future__ import annotations

CANVAS_W, CANVAS_H = 420, 280

# 渲染层的公共倾斜（BongoMode.tilt_deg / tilt_cy 必须和这里一致）
TILT_DEG = 8.0
TILT_CY = 228.0

# 桌沿：未倾斜坐标下的一条水平线，转 8° 之后就是画面里那条斜边。
# 取 168 是为了让 60% 键盘（外壳上沿 166）压住它 2px：既不留缝，
# 又不会把桌沿整个吃掉——键盘左右两侧还能看到一截桌面。
DESK_EDGE_Y = 168.0

# 道具（键盘外壳 / 琴身 / 鼠标垫）的上沿。比桌沿高 2px，压在桌沿上。
PROP_TOP = DESK_EDGE_Y - 2.0

# 桌面四边都出画：整块转 8° 之后，画布两下角仍然落在桌面里，
# 否则右下角会露出一块透明，像桌面被啃掉一角。
TABLE_OVERHANG = 70.0
TABLE_BOTTOM = 380.0

TABLE_FILL = "#F3E8D8"
TABLE_EDGE = "#DFCBB2"
TABLE_STROKE = 3.0


def table_path(edge_y: float = DESK_EDGE_Y) -> str:
    """桌面的 path：上沿就是分割线，其余三边出画。"""
    x0 = -TABLE_OVERHANG
    x1 = CANVAS_W + TABLE_OVERHANG
    return (
        f"M {x0:.1f} {edge_y:.1f} "
        f"L {x1:.1f} {edge_y:.1f} "
        f"L {x1:.1f} {TABLE_BOTTOM:.1f} "
        f"L {x0:.1f} {TABLE_BOTTOM:.1f} Z"
    )


def table_svg(edge_y: float = DESK_EDGE_Y) -> str:
    """桌面那一层，直接拼进素材最前面（所有道具之下）。"""
    return (
        f'  <path id="table" d="{table_path(edge_y)}" fill="{TABLE_FILL}" '
        f'stroke="{TABLE_EDGE}" stroke-width="{TABLE_STROKE}"/>'
    )


def prop_top() -> float:
    """道具上沿，素材脚本里的键区 / 外壳都从这里往下算。"""
    return PROP_TOP
