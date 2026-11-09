"""把宠物的 PNG 帧转成 bongocat 用的 body.svg。

用法：
    python scripts/trace_body.py                  # 默认取 drag/0-0.png
    python scripts/trace_body.py path/to/x.png

为什么转矢量而不是在 SVG 里嵌 PNG：桌宠窗口本身要整体缩到 86%，碰上
高 DPI 屏还要再放大一次，1000px 的位图落到屏幕上被重采样两遍，描边和
眼睛边缘都会糊；路径在任意尺寸下都锐利。

输出的头身是**一整块**，不拆 head：这只鼠头身连着，硬切会在脖子那里
留下一道缝。<g id="head"/> 留空占位即可，BongoRenderer 对空组拿到的是
null rect，会直接跳过。
"""
import os
import re
import sys
import tempfile

import vtracer
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(ROOT, "pets", "BB", "resource", "drag", "0-0.png")
)
OUT = os.path.join(ROOT, "pets", "BB", "resource", "bongo", "body.svg")

CANVAS_W, CANVAS_H = 420, 280
# 尺寸按"整张脸要露在键盘上沿之上、下巴以下被键盘挡住"来倒推。
# 现在是 165 = 248 的 2/3：键盘已经缩到 240 宽，宠物还是 248 高就显得
# 头重脚轻，整只鼠把键盘压没了。
# TOP_Y 给 78：键盘为了腾出旋转余量整体上抬了 22，上沿从 194 升到 172，
# 头不跟着让就会只剩一个圆顶露在外面、鼻子被键帽啃掉。跟着上移 18，
# 露出高度回到 88。
# 78 这个值同时是「抱胸的粉手」的下限：源图里那双原画的粉手落在角色
# 60%~74% 高度，也就是 177~200，必须整双落在键盘上沿 172 之下，否则会跟
# 运行时那两只爪子凑成四只手。再往上抬（TOP_Y 更小）手就会露出来。
# 调大一点鼻子会被键帽啃掉，调小整只鼠会浮起来。
PET_H = 165.0
TOP_Y = 78.0
CENTER_X = CANVAS_W / 2.0

# hierarchical 必须用 cutout，不能用 stacked。
# stacked 输出的每块都是**完整填充**（不挖洞），后画的盖住先画的；白口鼻
# 这么小一块夹在灰身体中间，会在量化时被并进灰色层，整个消失——之前
# 爪子里那圈白底就是这么丢的，只剩黑鼻子和嘴悬在灰底上。
# cutout 每块互不重叠、各自独立，白圈、粉爪、耳朵内侧白条全都留得住。
#
# color_precision 给 6：4 会把 #F4F4F4 的白和 #CDCACA 的灰并成一类。
# layer_difference 给 8 才分得开相邻的灰阶；再往下降（试过 4）色带会爆到
# 几千条 path，既慢又大，肉眼还看不出区别。
# filter_speckle 给 4 就够，10 会把白圈边缘的抗锯齿啃出毛边。
TRACE = dict(
    colormode="color",
    hierarchical="cutout",
    mode="spline",
    filter_speckle=4,
    color_precision=6,
    layer_difference=8,
    corner_threshold=60,
    length_threshold=3.0,
    max_iterations=10,
    splice_threshold=45,
    path_precision=2,
)

# 源图肚子上还有两团原画粉手（含黑描边）落在角色 59%~71% 高度。
# 键盘造型靠「整双落在键盘上沿之下」把它挡住（见上面 TOP_Y 的注释），
# 键鼠造型 body_scale=1.3 把身体放大上移，手就从桌子底下钻出来了，
# 跟运行时那两只爪子凑成四只手。描摹前先把这块刷成身体灰——cutout
# 分层下那里本来就是一层灰底，刷掉等于从源头去掉，生成出来的 svg
# 里不会再有那两团粉色和黑圈。脚和耳朵里的粉点都在这个框外，别动。
# 比例按源图边长给，换分辨率的同款素材也能对上（左, 上, 右, 下）。
ERASE_HANDS = (0.385, 0.588, 0.629, 0.707)
BODY_GRAY = (204, 203, 203, 255)  # 身体主色，从手四周采样


def erase_hands(im: Image.Image) -> Image.Image:
    """把肚子上那两只原画粉手刷成身体灰，返回新图（不改原对象）。"""
    w, h = im.size
    l, t, r, b = ERASE_HANDS
    clean = im.copy()
    clean.paste(BODY_GRAY, (int(l * w), int(t * h), int(r * w), int(b * h)))
    return clean


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    bbox = im.getbbox()
    if bbox is None:
        raise SystemExit("源图是全透明的，没有可描的内容")
    left, top, right, bottom = bbox
    bw, bh = right - left, bottom - top
    print("源图 %dx%d，角色内容 %dx%d @ (%d,%d)" % (im.width, im.height, bw, bh, left, top))

    scale = PET_H / bh
    tx = CENTER_X - (left + bw / 2.0) * scale
    ty = TOP_Y - top * scale
    print("缩放 %.4f，平移 (%.2f, %.2f)，落到画布上宽 %.1f" % (scale, tx, ty, bw * scale))

    # 刷掉肚子上的原画粉手再描摹（键鼠造型放大后那双手会露出来，见
    # ERASE_HANDS 的注释）。存成临时 PNG 给 vtracer 读。
    tmp_png = os.path.join(tempfile.gettempdir(), "bongo_body_nohand.png")
    erase_hands(im).save(tmp_png)
    tmp = os.path.join(tempfile.gettempdir(), "bongo_body_raw.svg")
    vtracer.convert_image_to_svg_py(tmp_png, tmp, **TRACE)
    raw = open(tmp, encoding="utf-8").read()

    paths = re.findall(r"<path\b[^>]*?/>", raw)
    if not paths:
        raise SystemExit("vtracer 没产出路径，调低 filter_speckle 试试")
    fills = sorted(set(re.findall(r'fill="(#[0-9a-fA-F]{3,6})"', raw)))
    print("路径 %d 条，配色 %s" % (len(paths), " ".join(fills)))

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d">' % (CANVAS_W, CANVAS_H, CANVAS_W, CANVAS_H),
        "  <!-- 由 scripts/trace_body.py 从 %s 生成，别手改 -->"
        % os.path.relpath(SRC, ROOT).replace(os.sep, "/"),
        '  <g id="body" transform="translate(%.2f %.2f) scale(%.5f)">' % (tx, ty, scale),
    ]
    out += ["    " + p for p in paths]
    out += ["  </g>", '  <g id="head"/>', "</svg>", ""]

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))
    print("写入 %s，%d bytes" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
