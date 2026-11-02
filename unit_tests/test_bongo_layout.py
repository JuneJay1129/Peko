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
from peko.ui.bongo import BongoRenderer, PawMotion

_app = QApplication.instance() or QApplication([])

_SVG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "pets", "BB", "resource", "bongo", "bongo.svg",
)


class KeyboardViewTests(unittest.TestCase):
    """键盘正对宠物，画面镜像：Q 区在右、Enter 在左。"""

    @classmethod
    def setUpClass(cls):
        cls.r = BongoRenderer(_SVG)

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
        self.r = BongoRenderer(_SVG)
        self.m = PawMotion(self.r)

    def _settle(self):
        for _ in range(80):
            self.m._tick()

    def test_starts_at_rest(self):
        centers = self.m.centers()
        self.assertEqual(self.r.rest_center("l"), centers["l"])
        self.assertEqual(self.r.rest_center("r"), centers["r"])

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


if __name__ == "__main__":
    unittest.main()
