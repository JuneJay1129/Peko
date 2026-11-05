"""导出 BB 鼠的表情姿态预览（直接复用运行时那套渲染和状态机）。

以前这里自己写了一份 draw_eyes / 姿态表，和 peko/ui 里的实现各走各的，
结果预览比例和真机对不上（body.svg 的 body 元素渲染范围只有 137x165，
自己那份把元素拉伸到了满画布，看起来大了一圈）。现在统一走
BongoRenderer + PetAnim，预览就是真机。

用法：
    python scripts/preview_pet_anim.py            # 静帧对照图 docs/pet-poses.png
    python scripts/preview_pet_anim.py --gif      # 另外导出 docs/pet-anim.gif
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtCore import QRectF, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from peko.core.bongo_modes import get_mode  # noqa: E402
from peko.ui.bongo import BongoRenderer  # noqa: E402
from peko.ui.pet_anim import (  # noqa: E402
    BUBBLE_BANG,
    BUBBLE_SLEEP,
    EYE_BLINK,
    EYE_CLOSED,
    EYE_HALF,
    EYE_WIDE,
    IDLE_CYCLE,
    IDLE_KEYS,
    WAKE_KEYS,
    PetAnim,
    Pose,
    sample_keys,
)

BG = "#232323"
SCALE = 2          # 导出 2 倍图，看起来才不糊
FPS = 12

# 静帧：钉住几个关键状态，方便一眼对比
STILLS = [
    ("open", Pose()),
    ("breath", Pose(dy=-1.8, scale=1.012)),
    ("tilt-L", Pose(rot=-6.0)),
    ("tilt-R", Pose(rot=5.0, eye=EYE_HALF)),
    ("blink", Pose(eye=EYE_BLINK)),
    ("zzz", Pose(eye=EYE_CLOSED, bubble=BUBBLE_SLEEP, bub=1.0)),
    ("wake-top", sample_keys(WAKE_KEYS, 0.3)),    # 窜起悬停（卡顿段）
    ("wake-fall", sample_keys(WAKE_KEYS, 0.72)),  # 落回途中
]


def _load_fonts(app: QApplication) -> None:
    """offscreen 平台的 fontconfig 是空的，不手动加载字体全是豆腐块。"""
    for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf"):
        path = os.path.join("C:/Windows/Fonts", name)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)
    app.setFont(QFont("Microsoft YaHei"))


def render_frame(renderer: BongoRenderer, pose: Pose) -> QImage:
    """照 BongoOverlay.paintEvent 的顺序画一帧，尺寸就是真机画布。"""
    cw, ch = int(renderer.canvas_w), int(renderer.canvas_h)
    img = QImage(cw * SCALE, ch * SCALE, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(BG))
    p = QPainter(img)
    renderer.set_pose(pose)
    renderer.frame_transform(p)
    renderer.paint_body(p)
    renderer.paint_table(p)
    renderer.paint_pad(p, False, False, 0.0)
    renderer.paint_desk(p, frozenset())
    renderer.paint_head(p)
    renderer.paint_paws(p, False, False, {})
    renderer.paint_bubble(p)
    p.end()
    return img


def build_sheet(renderer: BongoRenderer, path: str) -> None:
    cols = 4
    rows = (len(STILLS) + cols - 1) // cols
    cw, ch = int(renderer.canvas_w) * SCALE, int(renderer.canvas_h) * SCALE
    sheet = QImage(cw * cols, ch * rows, QImage.Format_ARGB32_Premultiplied)
    sheet.fill(QColor(BG))
    p = QPainter(sheet)
    for i, (label, pose) in enumerate(STILLS):
        p.drawImage(QRectF((i % cols) * cw, (i // cols) * ch, cw, ch), render_frame(renderer, pose))
        p.setPen(QColor("#8a8a8a"))
        p.drawText((i % cols) * cw + 14, (i // cols) * ch + 26, label)
    p.end()
    sheet.save(path)
    print(f"[preview] {path}  {sheet.width()}x{sheet.height()}")


def build_gif(renderer: BongoRenderer, path: str) -> None:
    """待机循环 + 惊醒抽帧成 gif。尺寸就是画布尺寸，不做任何额外放大。

    结构照运行时的时间轴来：一圈待机循环，接一段入睡渐入 + 惊醒四拍，
    再回待机 —— 和真机里「打瞌睡 16s → 被敲醒」的故事一致。
    """
    from PIL import Image

    def capture(pose: Pose):
        img = render_frame(renderer, pose).scaled(
            int(renderer.canvas_w), int(renderer.canvas_h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        buf = img.convertToFormat(QImage.Format_RGBA8888)
        # constBits() 返回的是裸指针，sip 不知道长度，得先 setsize
        bits = buf.constBits()
        bits.setsize(buf.byteCount())
        pil = Image.frombytes("RGBA", (buf.width(), buf.height()), bytes(bits))
        return pil.convert("P", palette=Image.ADAPTIVE, colors=128)

    frames = []
    steps = int(IDLE_CYCLE * FPS)
    for i in range(steps):
        frames.append(capture(sample_keys(IDLE_KEYS, i / FPS)))
    # 入睡渐入（0.7s）+ 惊醒四拍（1.55s）
    for i in range(int(0.7 * FPS)):
        frames.append(capture(Pose(eye=EYE_HALF if i * 0.05 < 0.35 else EYE_BLINK)))
    for i in range(int(PetAnim.WAKE_SEC * FPS)):
        frames.append(capture(sample_keys(WAKE_KEYS, i / FPS)))
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        disposal=2,
    )
    print(f"[preview] {path}  {len(frames)} frames  {int(renderer.canvas_w)}x{int(renderer.canvas_h)}")


def main() -> int:
    app = QApplication(sys.argv)
    _load_fonts(app)
    renderer = BongoRenderer(mode=get_mode("paws"))
    build_sheet(renderer, os.path.join(ROOT, "docs", "pet-poses.png"))
    if "--gif" in sys.argv:
        build_gif(renderer, os.path.join(ROOT, "docs", "pet-anim.gif"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
