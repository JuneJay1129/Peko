"""bongo 按键归手：左手区出左爪、右手区出右爪，空格与中文交给交替策略。"""
import io
import os
import unittest

from peko.core.bongo_keys import KEY_CAPS, cap_for, cap_for_pynput, side_for, side_for_pynput


class CharSideTests(unittest.TestCase):
    def test_left_hand_chars(self):
        for ch in "12345qwertasdfgzxcvb":
            self.assertEqual(side_for(char=ch), "left", ch)

    def test_right_hand_chars(self):
        for ch in "67890yuiophjkl;'nm,./":
            self.assertEqual(side_for(char=ch), "right", ch)

    def test_shifted_chars(self):
        self.assertEqual(side_for(char="!"), "left")   # 1 的 shift
        self.assertEqual(side_for(char="^"), "right")  # 6 的 shift
        self.assertEqual(side_for(char="?"), "right")  # / 的 shift

    def test_uppercase_follows_same_hand(self):
        self.assertEqual(side_for(char="A"), "left")
        self.assertEqual(side_for(char="L"), "right")

    def test_space_alternates(self):
        self.assertEqual(side_for(name="space"), "alt")
        self.assertEqual(side_for(char=" "), "alt")

    def test_cjk_char_alternates(self):
        # 中文输入法下拿不到物理键位，退回交替，别让爪子完全不动
        self.assertEqual(side_for(char="你"), "alt")

    def test_unknown_returns_none(self):
        self.assertIsNone(side_for())
        self.assertIsNone(side_for(name="media_play_pause"))

    def test_control_chars_never_alternate(self):
        """Qt 的 QKeyEvent.text() 对 Backspace 是 '\\x08'。

        这些控制字符 strip() 之后仍非空，早先会被当成「输入法字符」走交替，
        按一下 Backspace 就轮到另一只手——表现就是两只手一起过来。
        """
        for ch in ("\x08", "\t", "\r", "\x7f", "\x1b"):
            self.assertIsNone(side_for(char=ch), repr(ch))


class SpecialKeyTests(unittest.TestCase):
    def test_modifiers(self):
        self.assertEqual(side_for(name="shift"), "left")
        self.assertEqual(side_for(name="shift_r"), "right")
        self.assertEqual(side_for(name="ctrl_l"), "left")
        self.assertEqual(side_for(name="enter"), "right")
        # Backspace 在左上角，归画面左边那只手，别再让它横跨整块键盘
        self.assertEqual(side_for(name="backspace"), "right")

    def test_function_keys(self):
        self.assertEqual(side_for(name="f1"), "right")
        self.assertEqual(side_for(name="f12"), "right")

    def test_arrows(self):
        self.assertEqual(side_for(name="left"), "right")


class PynputAdapterTests(unittest.TestCase):
    def _key(self, char=None, name=None):
        class K:
            pass

        k = K()
        k.char = char
        k.name = name
        return k

    def test_char_key(self):
        self.assertEqual(side_for_pynput(self._key(char="q")), "left")
        self.assertEqual(side_for_pynput(self._key(char="p")), "right")

    def test_special_key(self):
        self.assertEqual(side_for_pynput(self._key(name="space")), "alt")
        self.assertEqual(side_for_pynput(self._key(name="enter")), "right")


class KeyCapTests(unittest.TestCase):
    """键盘画了 60% 的 61 个键，每个键帽都有 id，按上就得亮。"""

    def test_every_letter_maps_to_itself(self):
        for ch in "abcdefghijklmnopqrstuvwxyz":
            self.assertEqual(cap_for(char=ch), ch)
            self.assertIn(cap_for(char=ch), KEY_CAPS)

    def test_uppercase_maps_to_lowercase_cap(self):
        self.assertEqual(cap_for(char="A"), "a")
        self.assertEqual(cap_for(char="P"), "p")

    def test_space(self):
        self.assertEqual(cap_for(char=" "), "space")
        self.assertEqual(cap_for(name="space"), "space")

    def test_vk_wins_over_char(self):
        # Shift+A 时 char 是 'A'，虚拟键码仍是 65
        self.assertEqual(cap_for(char="A", vk=65), "a")
        self.assertEqual(cap_for(vk=32), "space")

    def test_digits_map_to_their_own_cap(self):
        for ch in "1234567890":
            self.assertEqual(cap_for(char=ch), ch)

    def test_shifted_symbols_share_the_digit_cap(self):
        # 同一物理键，按下 Shift 只是输出字符变了，亮的还是那个键帽
        for shifted, plain in (("!", "1"), ("@", "2"), ("#", "3"), ("%", "5")):
            self.assertEqual(cap_for(char=shifted), plain, shifted)

    def test_punctuation_caps(self):
        self.assertEqual(cap_for(char=";"), "semicolon")
        self.assertEqual(cap_for(char=":"), "semicolon")
        self.assertEqual(cap_for(char="/"), "slash")
        self.assertEqual(cap_for(char="?"), "slash")
        self.assertEqual(cap_for(char="-"), "minus")
        self.assertEqual(cap_for(char="_"), "minus")
        self.assertEqual(cap_for(char="`"), "backtick")
        self.assertEqual(cap_for(char="\\"), "backslash")

    def test_function_keys_have_caps(self):
        self.assertEqual(cap_for(name="enter"), "enter")
        self.assertEqual(cap_for(name="shift"), "lshift")
        self.assertEqual(cap_for(name="shift_r"), "rshift")
        self.assertEqual(cap_for(name="caps_lock"), "caps")
        self.assertEqual(cap_for(name="tab"), "tab")
        self.assertEqual(cap_for(name="backspace"), "backspace")

    def test_keys_not_on_60_percent_have_no_cap(self):
        # 60% 键盘没有 F 区，按了只挥手不落爪
        self.assertIsNone(cap_for(name="f5"))
        self.assertIsNone(cap_for(name="home"))

    def test_cjk_has_no_cap(self):
        # 中文输入法下 char 是汉字，键盘上没这个键，只能让爪子动
        self.assertIsNone(cap_for(char="你"))

    def test_pynput_adapter(self):
        class K:
            char = "q"
            name = None
            vk = None

        self.assertEqual(cap_for_pynput(K()), "q")

        class Space:
            char = None
            name = None
            vk = 32

        self.assertEqual(cap_for_pynput(Space()), "space")

    def test_caps_cover_svg_ids(self):
        # bongo.svg 里的键帽 id 就是 "k" + 键名，漏一个就会有个键永远不亮
        svg = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "pets", "BB", "resource", "bongo", "bongo.svg",
        )
        with io.open(svg, encoding="utf-8") as f:
            text = f.read()
        for cap in KEY_CAPS:
            self.assertIn(f'id="k{cap}"', text, cap)


if __name__ == "__main__":
    unittest.main()
