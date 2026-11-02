"""bongo 按键状态机：重点是快速连打不能吞动作。

背景：2026-11 初版用「松开后延迟 90ms 再回落」，快速连打时松开启动的
定时器会被下一次 press 停掉，落下状态却仍是 True，既不 emit 也不回落，
爪子卡住不动——按键越快越像没反应。这里锁死「每次抬落都要有事件」。
"""
import unittest

from peko.ui.bongo import BongoController


def _collect(ctrl):
    seq = []
    ctrl.state_changed.connect(lambda l, r: seq.append((l, r)))
    return seq


class FastTypingTests(unittest.TestCase):
    def test_same_key_repeat_never_swallowed(self):
        """同一个键连打在 30ms 级别，每次都要有抬起。"""
        c = BongoController()
        seq = _collect(c)
        for _ in range(20):
            c.key_event("a", True, "left")
            c.key_event("a", False, "left")
        # 20 次按下 + 20 次松开 = 40 次状态翻转
        self.assertEqual(40, len(seq))
        self.assertEqual((False, False), c.state)
        self.assertTrue(all(seq[i][0] != seq[i - 1][0] for i in range(1, len(seq))))

    def test_two_hands_alternate(self):
        c = BongoController()
        seq = _collect(c)
        for i in range(10):
            key, side = ("j", "right") if i % 2 else ("f", "left")
            c.key_event(key, True, side)
            c.key_event(key, False, side)
        self.assertEqual(20, len(seq))
        self.assertEqual((False, False), c.state)


class HoldTests(unittest.TestCase):
    def test_long_press_auto_repeat_ignored(self):
        """长按会持续收到 press，只算一次落下。"""
        c = BongoController()
        seq = _collect(c)
        for _ in range(10):
            c.key_event("a", True, "left")
        self.assertEqual(1, len(seq))
        self.assertEqual((True, False), c.state)
        c.key_event("a", False, "left")
        self.assertEqual((False, False), c.state)

    def test_same_hand_multiple_keys(self):
        """A+S 同时按着，只松 A 不该回落。"""
        c = BongoController()
        c.key_event("a", True, "left")
        c.key_event("s", True, "left")
        c.key_event("a", False, "left")
        self.assertEqual((True, False), c.state)
        c.key_event("s", False, "left")
        self.assertEqual((False, False), c.state)

    def test_release_without_press_ignored(self):
        c = BongoController()
        seq = _collect(c)
        c.key_event("a", False, "left")
        self.assertEqual([], seq)


class SideTests(unittest.TestCase):
    def test_space_alternates_hands(self):
        c = BongoController()
        c.key_event("sp1", True, "alt")
        self.assertEqual((True, False), c.state)
        c.key_event("sp1", False, "alt")
        c.key_event("sp2", True, "alt")
        self.assertEqual((False, True), c.state)

    def test_unknown_hint_ignored(self):
        c = BongoController()
        seq = _collect(c)
        c.key_event("mouse", True, None)
        self.assertEqual([], seq)


class KeyCapTests(unittest.TestCase):
    """键盘上对应键帽要跟着亮，且不能因为重复的物理键而残留。"""

    def test_cap_lights_on_press_and_clears_on_release(self):
        c = BongoController()
        seen = []
        c.caps_changed.connect(lambda caps: seen.append(set(caps)))
        c.key_event("vk65", True, "left", "a")
        self.assertEqual({"a"}, set(c.caps))
        c.key_event("vk65", False, "left", "a")
        self.assertEqual(set(), set(c.caps))
        self.assertEqual([{"a"}, set()], seen)

    def test_multiple_caps_at_once(self):
        c = BongoController()
        c.key_event("vk65", True, "left", "a")
        c.key_event("vk70", True, "left", "f")
        c.key_event("vk74", True, "right", "j")
        self.assertEqual({"a", "f", "j"}, set(c.caps))
        c.key_event("vk70", False, "left", "f")
        self.assertEqual({"a", "j"}, set(c.caps))

    def test_no_cap_for_unmapped_key(self):
        """数字键、功能键在键盘上没画，不点亮但要照常动爪。"""
        c = BongoController()
        c.key_event("vk49", True, "left", None)
        self.assertEqual(set(), set(c.caps))
        self.assertEqual((True, False), c.state)

    def test_cap_survives_auto_repeat(self):
        c = BongoController()
        for _ in range(5):
            c.key_event("vk65", True, "left", "a")
        self.assertEqual({"a"}, set(c.caps))

    def test_stuck_key_clears_cap(self):
        c = BongoController()
        c.key_event("vk65", True, "left", "a")
        c._held_since["vk65"] -= 10.0
        c.key_event("vk65", True, "left", "a")  # 视为新的按下
        c.key_event("vk65", False, "left", "a")
        self.assertEqual(set(), set(c.caps))


class StuckKeyTests(unittest.TestCase):
    def test_lost_release_recovers(self):
        """切窗口导致 release 丢失时，下次按下要能自愈，不能永久按住。"""
        c = BongoController()
        c.key_event("a", True, "left")
        self.assertEqual((True, False), c.state)

        # 伪造「这次按下距离上次已经很久」，跳过 5 秒等待
        c._held_since["a"] = c._held_since["a"] - 10.0
        c.key_event("a", True, "left")
        self.assertEqual((True, False), c.state)  # 仍然按住，但已重置计时

        c.key_event("a", False, "left")
        self.assertEqual((False, False), c.state)  # 这次能正常抬起来


if __name__ == "__main__":
    unittest.main()
