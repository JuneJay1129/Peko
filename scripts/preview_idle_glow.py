"""待机提示的效果预览：敲完手停下 5 秒，键盘和爪子会变成什么样。

只做两格对照（离屏渲染，不开窗口）：
- 左：正在敲（宠物左手按住 F，画面右爪落在 F 上，只有 F 高亮）
- 右：停手 5 秒（两只爪子收回 paw_*_rest，整盘键帽亮起）

坐标全部按运行时那套走：body 只过 tilt，键盘过 persp × tilt，爪子只平移
不缩放（和 BongoRenderer.paint_paws 一致）。素材换版本时重跑这张图就能
确认两个状态没有穿模。

用法：python scripts/preview_idle_glow.py
输出：docs/idle-glow-demo.png
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESK_SVG = os.path.join(ROOT, "pets", "BB", "resource", "bongo", "bongo.svg")
BODY_SVG = os.path.join(ROOT, "pets", "BB", "resource", "bongo", "body.svg")
OUT_PNG = os.path.join(ROOT, "docs", "idle-glow-demo.png")

CANVAS_W, CANVAS_H = 420, 280
TILT_DEG, TILT_CY = 8.0, 228.0
PERSP_INSET = 34.0
HIGHLIGHT = "#FFD166"
PAW_Y_OFFSET = -5.0
CROP = (70, 40, 300, 220)
SCALE = 2.0


def tilt() -> "QTransform":
    from PyQt5.QtGui import QTransform

    t = QTransform()
    t.translate(CANVAS_W / 2.0, TILT_CY)
    t.rotate(TILT_DEG)
    t.translate(-CANVAS_W / 2.0, -TILT_CY)
    return t


def persp(shell) -> "QTransform":
    from PyQt5.QtCore import QPointF
    from PyQt5.QtGui import QPolygonF, QTransform

    if shell.isNull():
        return QTransform()
    src = QPolygonF([shell.topLeft(), shell.topRight(), shell.bottomRight(), shell.bottomLeft()])
    dst = QPolygonF([
        QPointF(shell.left() + PERSP_INSET, shell.top()),
        QPointF(shell.right() - PERSP_INSET, shell.top()),
        QPointF(shell.right(), shell.bottom()),
        QPointF(shell.left(), shell.bottom()),
    ])
    t = QTransform()
    QTransform.quadToQuad(src, dst, t)
    return t


def draw_cell(p, desk, body, shell, key_caps, x, y, title, note, lit, paws, down):
    from PyQt5.QtCore import QPointF, QRectF, Qt
    from PyQt5.QtGui import QColor, QFont, QPen

    cw, ch = int(CROP[2] * SCALE), int(CROP[3] * SCALE)
    p.save()
    p.setClipRect(x, y, cw, ch)
    p.fillRect(x, y, cw, ch, QColor("#1e1e1e"))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#262626"))
    step = 14
    for gy in range(0, ch, step):
        for gx in range(0, cw, step):
            if (gx // step + gy // step) % 2:
                p.drawRect(x + gx, y + gy, step, step)
    p.restore()

    p.save()
    p.translate(x, y)
    p.scale(SCALE, SCALE)
    p.translate(-CROP[0], -CROP[1])

    # 1. 身体（只过 tilt）
    p.save()
    p.setTransform(tilt(), True)
    body.render(p, "body", QRectF(0, 0, CANVAS_W, CANVAS_H))
    p.restore()

    # 2. 键盘（persp × tilt）
    p.save()
    p.setTransform(persp(shell) * tilt(), True)
    desk.render(p, "desk", shell)
    # 3. 高亮：60% 键帽是正矩形，运行时也走 drawRoundedRect 这条分支
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(HIGHLIGHT))
    for cap in lit:
        r = key_caps[cap]
        p.drawRoundedRect(r.adjusted(0.4, 0.4, -0.4, -0.4), 2, 2)
    p.restore()

    # 4. 爪子：只平移，不缩放（centers 已是画面坐标）
    for eid, center in paws:
        rect = QRectF(desk.boundsOnElement(eid))
        rect.translate(center.x() - rect.center().x(), center.y() - rect.center().y())
        desk.render(p, eid, rect)
    p.restore()

    p.save()
    p.setPen(QPen(QColor("#4a4a4a"), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRect(x, y, cw - 1, ch - 1)
    p.setPen(QColor("#e6e6e6"))
    p.setFont(QFont("Microsoft YaHei", 10))
    p.drawText(x + 8, y - 8, title)
    p.setPen(QColor("#8a8a8a"))
    p.setFont(QFont("Consolas", 9))
    p.drawText(x + 8, y + ch + 16, note)
    p.restore()


def main() -> int:
    from PyQt5.QtCore import QPointF, QRectF
    from PyQt5.QtGui import QColor, QFont, QImage, QPainter
    from PyQt5.QtSvg import QSvgRenderer
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    desk = QSvgRenderer(DESK_SVG)
    body = QSvgRenderer(BODY_SVG)
    if not (desk.isValid() and body.isValid()):
        raise SystemExit("svg invalid")

    shell = desk.boundsOnElement("desk")
    # 枚举素材里所有键帽（QSvgRenderer 不能列举 element，走 XML 拿 id）
    import xml.etree.ElementTree as ET

    ids = [e.get("id") for e in ET.parse(DESK_SVG).iter() if e.get("id")]
    key_caps = {}
    for eid in ids:
        if not eid.startswith("k") or eid.startswith("ke"):
            continue
        rect = desk.boundsOnElement(eid)
        if not rect.isNull():
            key_caps[eid[1:]] = rect
    glow = list(key_caps)

    t = tilt()
    dm = persp(shell) * t

    def cap_point(name: str) -> QPointF:
        pt = dm.map(QPointF(desk.boundsOnElement(f"k{name}").center()))
        pt.setY(pt.y() + PAW_Y_OFFSET)
        return pt

    # 画面右 = 宠物左手；paws 字典是「画面侧」
    rest_r = dm.map(QPointF(desk.boundsOnElement("paw_r_rest").center()))
    rest_l = dm.map(QPointF(desk.boundsOnElement("paw_l_rest").center()))

    cw, ch = int(CROP[2] * SCALE), int(CROP[3] * SCALE)
    gap, title_h = 14, 26
    w = 2 * cw + 3 * gap
    h = ch + title_h + 2 * gap

    out = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    out.fill(QColor("#141414"))
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    y = gap + title_h
    draw_cell(
        p, desk, body, shell, key_caps, gap, y,
        "正在敲（按 F / J）", "paws down -> kf / kj",
        {"f", "j"},
        [("paw_r_down", cap_point("f")), ("paw_l_down", cap_point("j"))],
        True,
    )

    # 停手 5 秒后那道扫光中的一帧：同时只亮全盘 1/6，从左往右推
    def cap_x(name: str) -> float:
        return dm.map(QPointF(desk.boundsOnElement(f"k{name}").center())).x()

    ordered = sorted(glow, key=cap_x)
    span = max(2, len(ordered) // 6)
    mid = len(ordered) // 2
    sweep = set(ordered[mid:mid + span])

    draw_cell(
        p, desk, body, shell, key_caps, gap + cw + gap, y,
        "停手 5 秒（扫光中）", f"lit={len(sweep)}/{len(ordered)}  paw -> paw_*_rest",
        sweep,
        [("paw_r_rest", rest_r), ("paw_l_rest", rest_l)],
        False,
    )
    p.end()

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    ok = out.save(OUT_PNG)
    print(("saved " if ok else "FAILED ") + OUT_PNG + f"  {out.width()}x{out.height()}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
