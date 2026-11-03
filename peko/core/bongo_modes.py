"""
Bongo 造型模式注册表：决定叠加层画哪块键盘、有没有手臂。

为什么单独抽一层：造型不能是渲染代码里的一堆 if。它得能被配置、能持久化，
以后还要长出别的玩法（键鼠同摆、小键盘、只手不按键……）。每个模式是一份
**数据**，渲染层只按字段办事；加一种造型 = 在 MODES 里加一条 + 补一份素材，
不改 BongoRenderer 的绘制流程。

模式字段分三类，加新造型时按需覆盖，渲染层不自带任何 if-else：

素材
- desk_svg / body_svg  文件名，相对 pets/<pet>/resource/bongo
- layout               键位布局标识，给 bongo_keys 挑键帽表用（现在只有 "60"）

几何（整块画布坐标系，改一个就要重新跑一遍素材脚本）
- canvas_w / canvas_h  画布尺寸；小键盘比例和 60% 完全不同
- tilt_deg / tilt_cy   键盘和身体的公共倾斜角与旋转中心
- persp_inset          键盘上边收窄量（透视）
- shoulders            两只手臂的肩点 (x, y)，画面左 / 右

行为
- draw_arms            是否从肩膀拉一条手臂到爪子

几何参数留在模式里而不是 renderer 的类常量，是为了让「小键盘模式」只写一条
数据 + 一份素材就能落地：那种键盘只有 4 列，画布窄、重心也不在 210，所有能转
的东西都得跟着变。

已知取舍：`draw_arms=False`（纯手）时身体和手的关系是断的——肩膀下面空一块，
手更像贴在键帽上的贴纸。换来的是 60% 键盘只有 252 宽，爪子却要够到最左的
Backspace 和最右的 Enter，手臂一拉满就是两条斜穿整块键盘的粗灰杆。

持久化到 config/bongo.json，只存选中的 key。读到不认识的 key 一律回退默认，
不因为用户手改坏文件就让叠加层起不来。
纯 Python、不依赖 Qt，便于单元测试。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

from .config_store import read_json, write_json

CONFIG_PATH = "config/bongo.json"
CONFIG_VERSION = 1

# 素材根目录相对宠物包，两段都由调用方拼（宠物包可切换）
RESOURCE_SUBDIR = ("resource", "bongo")


@dataclass(frozen=True)
class BongoMode:
    """一种造型。frozen：注册表里的条目不应该被就地改。

    默认值就是 60% 键盘那一套（15u × 5 排，420×280 画布，绕 (210,228) 转 8°），
    其它模式只需覆盖跟自己不一样的字段。
    """

    key: str
    label: str
    desc: str = ""

    # 素材
    desk_svg: str = "bongo.svg"
    body_svg: str = "body.svg"
    layout: str = "60"

    # 几何
    canvas_w: int = 420
    canvas_h: int = 280
    tilt_deg: float = 8.0
    tilt_cy: float = 228.0
    persp_inset: float = 34.0
    # (画面左肩, 画面右肩)，**没旋转前**的坐标
    shoulders: Tuple[Tuple[float, float], Tuple[float, float]] = (
        (158.0, 172.0),
        (262.0, 172.0),
    )

    # 行为
    draw_arms: bool = False
    # 宠物整体上下挪多少（画布像素，负数上移）。键鼠造型要把它抬到桌沿后面，
    # 桌子才盖得住下半身、只露上半身。
    body_dy: float = 0.0
    # 宠物整体放大倍数，锚点在「画布水平中心 + tilt_cy」：身体是从桌沿后面
    # 冒出来的，绕底部往上长才像坐得更近；绕正中缩放会连下身一起放大，
    # 桌沿就盖不住了。
    body_scale: float = 1.0
    # 爪子相对键帽中心的纵向偏移。60% 键帽 16 高，抬 -5 只压住上沿；
    # 40% 键帽只有 15，还按 -5 会把高亮整个盖掉，所以留个按模式调的字段。
    paw_y_offset: float = -5.0
    # 画面哪只手固定在鼠标上（"l" / "r"，空串表示这造型没有鼠标）。
    # 非空时 PawMotion 不再驱动这只手：它跟着真光标在垫子上滑，
    # 另一只手接走**全部**按键（40% 键盘只有一半宽，左右手分工没意义了）。
    mouse_hand: str = ""
    # 打字手闲置时的休息位（画面左/右，**未倾斜**的画布坐标）。
    # 给了之后松手停手一段时间会自动收回到这里，而不是赖在最后按下的键上；
    # None 表示老行为（手一直在键盘上），60% 那套键盘用不着。
    # 注意这两个是**桌面上**的点，只走倾斜、不套键盘透视；要让手停在某个
    # 键帽上就用下面的 rest_cap_*，别硬算键帽坐标。
    paw_rest_l: Optional[Tuple[float, float]] = None
    paw_rest_r: Optional[Tuple[float, float]] = None
    # 打字手闲置时停在哪个键帽上（键帽 id，不带 "k" 前缀，如 "space"）。
    # 走的是和真按下同一套 cap_center + paw_y_offset，所以「待机」和
    # 「按下再松手」是同一个落点，手不会在这一步跳一下。优先于 paw_rest_*。
    rest_cap_l: Optional[str] = None
    rest_cap_r: Optional[str] = None


# ---- 注册表 ----
# 顺序即菜单顺序。新造型加在这里；同 key 重复注册按「后写覆盖」处理，
# 留给测试和换肤用。
MODES: Dict[str, BongoMode] = {}


def register(mode: BongoMode) -> BongoMode:
    MODES[mode.key] = mode
    return mode


register(BongoMode(
    key="paws",
    label="纯手",
    desc="只有爪子浮在键帽上，没有手臂",
    draw_arms=False,
))
register(BongoMode(
    key="arms",
    label="带手臂",
    desc="从肩膀伸到爪子的灰色手臂，手跟着身体",
    draw_arms=True,
))

register(BongoMode(
    key="mouse",
    label="键鼠同摆",
    desc="透视小键盘 + 一只手握鼠标，光标动鼠标就跟着滑",
    desk_svg="bongo_mouse.svg",
    layout="40",
    # 透视已经烘进素材坐标（见 gen_bongo_mouse.py 的 homography），
    # 再叠一层 persp_inset 会把梯形二次收窄，键帽和爪子一起错位。
    persp_inset=0.0,
    # 和其它造型同一个倾斜角和旋转中心：桌子、垫子、鼠标、键盘、宠物
    # 共用这一个变换，切造型时姿态才连续。素材边界已经按 8° 外扩过，
    # 画布四角不会露透明（见 gen_bongo_mouse.py 的 TABLE_EDGE）。
    tilt_deg=8.0,
    tilt_cy=228.0,
    # 不要手臂：40% 键盘只有 172 宽，手臂一次压掉 3~4 个键。
    # 手直接搭在键帽 / 鼠标上，靠素材里的接触阴影贴住。
    draw_arms=False,
    # 整只鼠抬到桌沿后面（body.svg y78~242 → 54~218），
    # 桌面那层盖住 150 以下：头 + 上胸露出来，body.svg 自带的两个粉色
    # 前爪（y178~196 → 154~172）刚好压在桌沿底下，不会多出「第三只手」。
    # 放大之后头顶已经贴到画布上沿，所以往上抬的量要小于原尺寸：
    # 只露上半身这个约束没变，抬 24 会连头顶一起切掉。
    body_dy=-10.0,
    # 键鼠同摆的整体画面元素多（垫子 + 键盘），宠物按原尺寸显得偏小。
    # 1.08 / 1.15 在 361×241 的窗口里只差十几个像素，肉眼基本看不出来；
    # 1.3 是这块画布的上限——再大一档头顶就被上沿切掉了（锚点 228、
    # 身体顶边 67.5，s > 1.36 就出界）。
    body_scale=1.3,
    # 手放大到和握鼠标那只一样（17×14）之后，原来的 -2 会整只盖住键帽，
    # 连黄色高亮都看不见；-11 才只压住上沿、露出下半截。
    paw_y_offset=-11.0,
    # 画面左 = 宠物右手。鼠标垫在左下，就由这只手去握
    mouse_hand="l",
    # 画面右那只手是唯一打字的手，闲置时就搭在空格键上——和真按下空格
    # 是同一个落点，不是另算一块桌面。键盘占满画布下半，桌面那边已经塞
    # 不下第三只手了（键盘下沿到画布底只剩 27）。
    rest_cap_r="space",
))

DEFAULT_MODE = "paws"


def list_modes() -> List[BongoMode]:
    """按注册顺序返回全部模式，给设置页 / 菜单用。"""
    return list(MODES.values())


def get_mode(key: Optional[str] = None, base_dir: Optional[str] = None) -> BongoMode:
    """按 key 取模式；None 取当前选中的，未知 key 回退默认。

    永远返回一个可用对象——调用方不用判 None，素材缺了是另一层的事。
    base_dir 仅供单元测试注入临时目录，业务代码不要传。
    """
    if key is None:
        key = current_key(base_dir=base_dir)
    return MODES.get(key) or MODES[DEFAULT_MODE]


def current_key(base_dir: Optional[str] = None) -> str:
    """当前选中的模式 key（未配置过就是默认）。"""
    raw = read_json(CONFIG_PATH, {}, base_dir=base_dir)
    key = raw.get("mode") if isinstance(raw, dict) else None
    return key if isinstance(key, str) and key in MODES else DEFAULT_MODE


def has_mode(key: str) -> bool:
    return key in MODES


def set_mode(key: str, base_dir: Optional[str] = None) -> bool:
    """切换模式并落盘；key 不认识返回 False 且不改动现有配置。"""
    if key not in MODES:
        return False
    return write_json(
        CONFIG_PATH, {"version": CONFIG_VERSION, "mode": key}, base_dir=base_dir
    )


def load_config(base_dir: Optional[str] = None) -> Dict[str, object]:
    """完整配置（含默认值），给诊断 / 设置页回显用。"""
    return {"version": CONFIG_VERSION, "mode": current_key(base_dir=base_dir)}


def asset_path(mode: BongoMode, pet_dir: str, which: str = "desk") -> str:
    """把模式里的素材名拼成绝对路径。

    pet_dir 传宠物包根目录（如 pets/BB），不是 resource 目录——
    子目录结构写在这里，调用方少拼一次就不会两处不一致。
    """
    name = mode.desk_svg if which == "desk" else mode.body_svg
    return os.path.join(pet_dir, *RESOURCE_SUBDIR, name)


def with_overrides(base: Optional[str] = None, **fields) -> BongoMode:
    """在某个模式基础上覆盖几个字段（测试和临时预览用，不落盘）。"""
    return replace(get_mode(base), **fields)


def next_mode(key: Optional[str] = None, base_dir: Optional[str] = None) -> BongoMode:
    """循环取下一个模式，给「按一下换个造型」的预览快捷键用。"""
    order = list(MODES)
    cur = key if isinstance(key, str) and key in MODES else current_key(base_dir=base_dir)
    idx = order.index(cur) if cur in order else 0
    return MODES[order[(idx + 1) % len(order)]]
