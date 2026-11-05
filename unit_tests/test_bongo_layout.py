"""bongo 叠加层的几何：键盘朝向、爪子跟到具体按键。

朝向是用户定的：**键盘正对着宠物，整块绕中心转了 180°**——画面上 Q 区在右、
Enter 在左、数字行在最下面、底排（空格那排）在最上面，键帽上的字也是倒的。
行序断言全跟正常键盘相反，别看着别扭就翻回来，已经反了两次。

爪子原来只有左右两个固定位置，现在按 boundsOnElement 平移到键帽上。
画面是左右反的，所以宠物左手按的键落在画面右侧，PET_TO_SCREEN 必须对调；
但 l/r 这两个名字始终指画面左/右那只爪，不跟着键盘翻。
"""
import os
import unittest

from PyQt5.QtWidgets import QApplication

from peko.core.bongo_keys import KEY_CAPS
from peko.core.bongo_modes import get_mode
from peko.ui.bongo import BongoRenderer, PawMotion

_app = QApplication.instance() or QApplication([])

_SVG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "pets", "BB", "resource", "bongo", "bongo.svg",
)

# 造型必须写死。BongoRenderer 不传 mode 会去读 config/bongo.json——用户上次在
# 托盘里挑了哪个造型，这里的几何断言就按哪个跑：挑「键鼠同摆」时一只手被冻在
# 鼠标上、键盘也没有 persp，这几条会集体红。
_MODE = get_mode("paws")


class KeyboardViewTests(unittest.TestCase):
    """键盘正对宠物，画面镜像：Q 区在右、Enter 在左。"""

    @classmethod
    def setUpClass(cls):
        cls.r = BongoRenderer(_SVG, mode=_MODE)

    def test_svg_loads(self):
        self.assertTrue(self.r.valid)

    def test_first_and_last_letters_in_order(self):
        self.assertGreater(self.r.cap_center("q").x(), self.r.cap_center("p").x())
        self.assertGreater(self.r.cap_center("a").x(), self.r.cap_center("l").x())
        self.assertGreater(self.r.cap_center("z").x(), self.r.cap_center("m").x())

    def test_each_row_runs_right_to_left(self):
        for row in ("qwertyuiop", "asdfghjkl", "zxcvbnm"):
            xs = [self.r.cap_center(c).x() for c in row]
            self.assertEqual(sorted(xs, reverse=True), xs, row)

    def test_digit_row_is_below_letter_row(self):
        """转了 180°，数字行跑到最下面。"""
        self.assertGreater(self.r.cap_center("1").x(), self.r.cap_center("0").x())
        self.assertGreater(self.r.cap_center("1").y(), self.r.cap_center("q").y())

    def test_space_sits_in_the_middle(self):
        space = self.r.cap_center("space").x()
        self.assertLess(space, self.r.cap_center("z").x())
        self.assertGreater(space, self.r.cap_center("m").x())

    def test_enter_is_far_left_and_tab_is_far_right(self):
        self.assertLess(
            self.r.cap_center("enter").x(), self.r.cap_center("p").x()
        )
        self.assertGreater(
            self.r.cap_center("tab").x(), self.r.cap_center("q").x()
        )

    def test_rows_stack_upwards(self):
        """行序整体倒过来：空格那排在最上，QWERTY 在数字行之上。"""
        self.assertLess(self.r.cap_center("space").y(), self.r.cap_center("z").y())
        self.assertLess(self.r.cap_center("z").y(), self.r.cap_center("a").y())
        self.assertLess(self.r.cap_center("a").y(), self.r.cap_center("q").y())

    def test_keyboard_is_tilted_right_end_down(self):
        """整块键盘**顺时针**倾斜：同一排里画面越靠右的键越靠下。

        倾斜是在渲染层做的（BongoRenderer.TILT_DEG，正值），cap_center 返回的
        必须是倾斜**之后**的坐标——不然爪子会落在没斜的位置，和键帽差开一截。
        """
        left = self.r.cap_center("enter")
        right = self.r.cap_center("tab")
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        self.assertGreater(right.y(), left.y())

    def test_keyboard_has_perspective(self):
        """键盘上边（远）比下边（近）窄：最上一排两端的键距要小于最下一排。

        转了 180°，所以「最上一排」是空格那一排（rctrl/lctrl），「最下一排」
        是数字行（backspace/backtick）。透视只作用在键盘上，cap_center 必须
        跟着走；漏掉的话越靠上的键爪子偏得越多，最上面一排能差出小半个键帽。
        """
        top = abs(self.r.cap_center("lctrl").x() - self.r.cap_center("rctrl").x())
        bottom = abs(
            self.r.cap_center("backtick").x() - self.r.cap_center("backspace").x()
        )
        self.assertLess(top, bottom)

    def test_every_drawn_cap_has_a_center(self):
        for cap in sorted(KEY_CAPS):
            self.assertIsNotNone(self.r.cap_center(cap), cap)

    def test_undrawn_key_has_no_center(self):
        # 60% 键盘上没有 F 区，按 F5 只挥手不落爪
        self.assertIsNone(self.r.cap_center("f5"))
        self.assertIsNone(self.r.cap_center(None))


class PawFollowTests(unittest.TestCase):
    """爪子要挪到该手最近按下的那个键上，而不是固定两点。"""

    def setUp(self):
        self.r = BongoRenderer(_SVG, mode=_MODE)
        self.m = PawMotion(self.r)

    def _settle(self):
        for _ in range(80):
            self.m._tick()

    def test_starts_at_rest(self):
        """一开始就是闲置态：有休息位的造型，双手直接搁在身侧桌面上。

        不再「先抬起来再落下去」——开场动画省掉，配合待机收手，
        打字手的默认位置就是休息位本身。
        """
        centers = self.m.centers()
        for side in ("l", "r"):
            rest = self.r.rest_center(side)
            self.assertAlmostEqual(rest.x(), centers[side].x(), delta=0.5, msg=side)
            self.assertAlmostEqual(rest.y(), centers[side].y(), delta=0.5, msg=side)

    def test_release_lifts_but_keeps_the_place(self):
        """松手往上抬，但横坐标留在刚按的键上，不弹回休息位。

        弹回去的话连打同一个键，爪子会在键和休息位之间来回飞。
        """
        self.m.set_targets(left_cap="a")
        self._settle()
        pressed = self.m.centers()["r"]
        self.m.set_targets(left_cap=None)
        self._settle()
        lifted = self.m.centers()["r"]
        self.assertAlmostEqual(pressed.x(), lifted.x(), delta=0.5)
        self.assertAlmostEqual(lifted.y(), pressed.y() - PawMotion.LIFT, delta=0.5)

    def test_left_hand_lands_on_right_paw(self):
        """键盘正对宠物、画面镜像，所以宠物左手（Q/A/Z 区）在画面右侧。"""
        self.m.set_targets(left_cap="a")
        self._settle()
        centers = self.m.centers()
        self.assertAlmostEqual(self.r.cap_center("a").x(), centers["r"].x(), delta=1.0)
        self.assertAlmostEqual(self.r.rest_center("l").x(), centers["l"].x(), delta=1.0)

    def test_right_hand_lands_on_left_paw(self):
        self.m.set_targets(right_cap="p")
        self._settle()
        centers = self.m.centers()
        self.assertAlmostEqual(self.r.cap_center("p").x(), centers["l"].x(), delta=1.0)
        self.assertAlmostEqual(self.r.rest_center("r").x(), centers["r"].x(), delta=1.0)

    def test_paw_sits_above_cap_so_highlight_shows(self):
        self.m.set_targets(right_cap="p")
        self._settle()
        self.assertLess(self.m.centers()["l"].y(), self.r.cap_center("p").y())

    def test_digit_key_is_reachable(self):
        """数字行也要能落爪，之前只有字母能亮。"""
        self.m.set_targets(left_cap="1", right_cap="0")
        self._settle()
        centers = self.m.centers()
        self.assertAlmostEqual(self.r.cap_center("1").x(), centers["r"].x(), delta=1.0)
        self.assertAlmostEqual(self.r.cap_center("0").x(), centers["l"].x(), delta=1.0)

    def test_adjacent_keys_keep_paws_apart(self):
        self.m.set_targets(left_cap="g", right_cap="h")
        self._settle()
        centers = self.m.centers()
        self.assertGreaterEqual(
            abs(centers["r"].x() - centers["l"].x()), PawMotion.MIN_GAP - 0.5
        )

    def test_idle_paw_gives_way_not_the_pressing_one(self):
        """一只手按键、另一只闲着时，该闲着的那只让开。

        K 在主区中间，离画面左爪的休息位很近；平均分摊会把按 K 的爪子
        推离键帽，看着像按在 J 和 K 中间。
        """
        self.m.set_targets(right_cap="k")
        self._settle()
        centers = self.m.centers()
        self.assertAlmostEqual(self.r.cap_center("k").x(), centers["l"].x(), delta=0.5)
        self.assertGreaterEqual(
            centers["r"].x(), centers["l"].x() + PawMotion.MIN_GAP - 0.5
        )

    def test_far_key_does_not_drag_the_idle_paw(self):
        """按 Backspace 时另一只手不能被拽走。

        Backspace 是最左边的键，由画面上右边那只手去够，一路跑到闲着那只
        手的左边，两只手在横坐标上「交叉」。早先拿有符号的间距判断，负值
        被当成「挨得太近」，于是把闲着的手推到按键手旁边 38——按一下
        Backspace，两条胳膊一起动。
        """
        idle_before = self.m.centers()["l"]
        self.m.set_targets(left_cap="backspace")
        self._settle()
        centers = self.m.centers()
        self.assertAlmostEqual(idle_before.x(), centers["l"].x(), delta=0.5)
        self.assertAlmostEqual(
            self.r.cap_center("backspace").x(), centers["r"].x(), delta=0.5
        )

    def test_release_keeps_paw_where_it_was(self):
        self.m.set_targets(left_cap="a")
        self._settle()
        x = self.m.centers()["r"].x()
        self.m.set_targets(left_cap=None, right_cap=None)
        self._settle()
        self.assertAlmostEqual(x, self.m.centers()["r"].x(), delta=0.5)

    def test_unmapped_key_leaves_paw_alone(self):
        self.m.set_targets(left_cap="z")
        self._settle()
        x = self.m.centers()["r"].x()
        self.m.set_targets(left_cap=None)  # 按了个键盘上没画的键
        self._settle()
        self.assertAlmostEqual(x, self.m.centers()["r"].x(), delta=0.5)

    def test_motion_emits_until_settled(self):
        frames = []
        self.m.changed.connect(lambda: frames.append(1))
        self.m.set_targets(left_cap="q")
        self._settle()
        self.assertGreater(len(frames), 3)
        self.assertFalse(self.m._timer.isActive())


class MouseModeTests(unittest.TestCase):
    """键鼠造型：和身体共用同一个倾斜、键位转 180°。

    这套素材的透视是烘在坐标里的（gen_bongo_mouse.py 的 homography），
    所以 persp_inset 必须是 0；tilt 则和其它造型一样 8°。
    """

    @classmethod
    def setUpClass(cls):
        cls.mode = get_mode("mouse")
        cls.r = BongoRenderer(mode=cls.mode)

    def test_shares_the_common_tilt(self):
        self.assertEqual(self.r.tilt_deg, get_mode("paws").tilt_deg)
        self.assertFalse(self.r._desk_matrix().isIdentity())

    def test_perspective_is_baked_into_the_asset(self):
        self.assertEqual(self.r.persp_inset, 0.0)

    def test_key_rows_are_rotated_180(self):
        """Tab 行（原来是远排）落到近边：y 更大；空格在远边。"""
        self.assertGreater(self.r.cap_center("q").y(), self.r.cap_center("space").y())
        self.assertGreater(self.r.cap_center("tab").y(), self.r.cap_center("enter").y())

    def test_mouse_hand_is_frozen_on_the_mouse(self):
        self.assertEqual(self.r.mouse_hand, "l")
        center = self.r.mouse_center()
        self.assertIsNotNone(center)
        self.assertGreater(center.x(), 0.0)
        self.assertLess(center.x(), self.r.canvas_w)

    def test_keyboard_has_a_shadow_layer(self):
        self.assertIn("kb_shadow", self.r._bounds)


class PianoStageTests(unittest.TestCase):
    """钢琴自己的舞台：桌沿分割线（scripts/bongo_stage.py）。

    线以上是 BB 鼠、线以下是琴键。60% 键盘和键鼠仍是各自的老坐标系，
    这里只钉钢琴那一套，别顺手把它们也拉进来。
    """

    DESK_EDGE_Y = 168.0  # = scripts/bongo_stage.DESK_EDGE_Y

    @classmethod
    def setUpClass(cls):
        cls.mode = get_mode("piano")
        cls.r = BongoRenderer(mode=cls.mode)

    def test_desk_asset_ships_its_own_table(self):
        self.assertTrue(self.r.valid)
        self.assertIn("table", self.r._bounds)

    def test_table_edge_sits_on_the_split_line(self):
        # stroke 3 会往上下各溢 1.5，所以量到的上沿比 DESK_EDGE_Y 小 1.5
        self.assertAlmostEqual(
            self.r._bounds["table"].top(), self.DESK_EDGE_Y - 1.5, delta=0.2
        )

    def test_props_start_below_the_edge(self):
        """琴身上沿不能高过桌沿，否则就是它多遮住一截 BB 鼠。"""
        self.assertGreaterEqual(self.r._bounds["desk"].top(), self.DESK_EDGE_Y - 2.0)

    def test_body_is_not_scaled_or_shifted(self):
        """钢琴不缩放身体：BB 鼠和键盘那套一样大、一样高。"""
        self.assertEqual(self.mode.body_dy, 0.0)
        self.assertEqual(self.mode.body_scale, 1.0)

    def test_shares_the_common_tilt(self):
        other = get_mode("paws")
        self.assertEqual(self.mode.tilt_deg, other.tilt_deg)
        self.assertEqual(self.mode.tilt_cy, other.tilt_cy)

    def test_table_covers_the_whole_bottom(self):
        b = self.r._bounds["table"]
        self.assertLess(b.left(), 0.0)
        self.assertGreater(b.right(), self.r.canvas_w)
        self.assertGreater(b.bottom(), self.r.canvas_h)

    def test_props_fit_on_canvas_after_tilt(self):
        """转完 8° 之后四个角都还在画布里，不然窗口会把它切平。"""
        from PyQt5.QtCore import QPointF

        b = self.r._bounds["desk"]
        for pt in (b.topLeft(), b.topRight(), b.bottomLeft(), b.bottomRight()):
            p = self.r._desk_matrix().map(QPointF(pt))
            self.assertTrue(0 <= p.x() <= self.r.canvas_w, (pt, p.x()))
            self.assertTrue(0 <= p.y() <= self.r.canvas_h, (pt, p.y()))


if __name__ == "__main__":
    unittest.main()
