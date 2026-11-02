"""Bongo 模式的按键 → 左右手映射（纯 Python，无 Qt 依赖，可直接单测）。

bongocat 的左右手是按键盘**物理位置**分的：左手区出左爪，右手区出右爪。
pynput 只给字符 / 键名，拿不到物理坐标，所以用一张标准 QWERTY 触摸打字分区表近似。

返回值约定：
    "left" / "right"  明确归属
    "alt"             无明确归属（空格、中文输入、未知字符），由调用方交替左右
    None              不响应（鼠标、媒体键等）

「空格」不归任何一只手：真人打字时左右拇指都用，这里交给交替策略，
否则空格会永远只敲一只手，看起来比不敲还假。
"""
from __future__ import annotations

from typing import Optional

# 左手区：数字 1-5、Q W E R T、A S D F G、Z X C V B 及其 shift 符号
LEFT_CHARS = frozenset("`~12345!@#$%qwertQWERTasdfgASDFGzxcvbZXCVB")

# 右手区：数字 6-0、Y U I O P、H J K L、N M 及其 shift 符号
RIGHT_CHARS = frozenset("67890^&*()yuiopYUIOP;:'\"hjklHJKLnm,.<>/?-_=+[]{}|\\")

# 特殊键按自然归属分
LEFT_NAMES = frozenset(
    {
        "esc",
        "tab",
        "caps_lock",
        "shift",
        "shift_l",
        "ctrl",
        "ctrl_l",
        "alt",
        "alt_l",
        "alt_gr",
        "cmd",
        "cmd_l",
        "backspace",
        "`",
    }
)

RIGHT_NAMES = frozenset(
    {
        "enter",
        "return",
        "shift_r",
        "ctrl_r",
        "alt_r",
        "cmd_r",
        "delete",
        "insert",
        "home",
        "end",
        "page_up",
        "page_down",
        "up",
        "down",
        "left",
        "right",
        "print_screen",
        "menu",
        "\\",
        "[",
        "]",
        "-",
        "=",
        ";",
        "'",
        ",",
        ".",
        "/",
    }
) | frozenset(f"f{i}" for i in range(1, 13))

# 交给交替策略的键
ALT_NAMES = frozenset({"space", " ", "spacebar"})


def side_for(char: Optional[str] = None, name: Optional[str] = None) -> Optional[str]:
    """把一次按键归到某只手。

    char 是字符键的字符（可能为 None），name 是特殊键名（可能为 None）。
    普通字符优先，其次看特殊键名。
    """
    if name:
        key = name.lower()
        if key in ALT_NAMES:
            return "alt"
        if key in LEFT_NAMES:
            return "left"
        if key in RIGHT_NAMES:
            return "right"

    if char:
        if char in LEFT_CHARS:
            return "left"
        if char in RIGHT_CHARS:
            return "right"
        # 中文输入法下 char 可能是汉字 / 全角符号，取不到物理键位。
        # 与其让爪子完全不动，不如交替拍一下，至少反馈是「你在打字」。
        # 空白里只认空格，\t \n 之类不响应。
        if char.strip() or char == " ":
            return "alt"

    return None


def side_for_pynput(key) -> Optional[str]:
    """把 pynput 的 KeyCode / Key 转成左右手。"""
    char = getattr(key, "char", None)
    name = getattr(key, "name", None)
    return side_for(char=char, name=name)


# ---------------------------------------------------------------------------
# 键帽 id：bongo.svg 里每个键帽是一个 <g id="k...">，这里定义 "k" 后面那截。
# 键盘上画了哪些键，这里就得有同名条目，漏一个那个键就永远不亮。
# 字符键按**输出字符**查（Shift 组合也查得到，! 和 1 落到同一个键帽）。
# ---------------------------------------------------------------------------

# 字母直接用自己的小写字符做 id
CHAR_CAPS = {ch: ch for ch in "abcdefghijklmnopqrstuvwxyz"}

# 数字行 / 标点：符号统一给个英文名，别把 ; . / 之类塞进 XML id
CHAR_CAPS.update(
    {
        " ": "space",
        "`": "backtick", "~": "backtick",
        "1": "1", "!": "1",
        "2": "2", "@": "2",
        "3": "3", "#": "3",
        "4": "4", "$": "4",
        "5": "5", "%": "5",
        "6": "6", "^": "6",
        "7": "7", "&": "7",
        "8": "8", "*": "8",
        "9": "9", "(": "9",
        "0": "0", ")": "0",
        "-": "minus", "_": "minus",
        "=": "equal", "+": "equal",
        "[": "lbracket", "{": "lbracket",
        "]": "rbracket", "}": "rbracket",
        "\\": "backslash", "|": "backslash",
        ";": "semicolon", ":": "semicolon",
        "'": "quote", '"': "quote",
        ",": "comma", "<": "comma",
        ".": "period", ">": "period",
        "/": "slash", "?": "slash",
    }
)

# 功能键按 pynput 的 Key.name 查。左右各一个的键名带 l/r 区分，
# 不区分的话按右 Shift 会点亮左 Shift。
NAME_CAPS = {
    "space": "space",
    "spacebar": "space",
    "backspace": "backspace",
    "tab": "tab",
    "caps_lock": "caps",
    "enter": "enter",
    "return": "enter",
    "shift": "lshift",
    "shift_l": "lshift",
    "shift_r": "rshift",
    "ctrl": "lctrl",
    "ctrl_l": "lctrl",
    "ctrl_r": "rctrl",
    "alt": "lalt",
    "alt_l": "lalt",
    "alt_gr": "lalt",
    "alt_r": "ralt",
    "cmd": "lwin",
    "cmd_l": "lwin",
    "cmd_r": "rwin",
    "menu": "menu",
}

# 键盘上真实画出来的键帽 id（不含前缀 "k"）
KEY_CAPS = frozenset(CHAR_CAPS.values()) | frozenset(NAME_CAPS.values())

_VK_LETTER_FIRST = 65  # VK_A
_VK_LETTER_LAST = 90   # VK_Z
_VK_SPACE = 32


def cap_for(
    char: Optional[str] = None,
    name: Optional[str] = None,
    vk: Optional[int] = None,
) -> Optional[str]:
    """把一次按键映射到键盘上要亮起的那个键帽 id。

    vk 优先：字符键在 Shift 组合下 char 会变成 'A'，虚拟键码不受影响。
    数字和标点不查 vk——Shift+1 的 char 是 '!'，走字符表也能落到键帽 "1"，
    而 vk 在部分输入法 / 仿真环境里不可靠。
    """
    if vk is not None:
        if vk == _VK_SPACE:
            return "space"
        if _VK_LETTER_FIRST <= vk <= _VK_LETTER_LAST:
            return chr(vk + 32)

    if char:
        cap = CHAR_CAPS.get(char)
        if cap is not None:
            return cap
        # 大写字母：'A' -> 'a'
        cap = CHAR_CAPS.get(char.lower())
        if cap is not None:
            return cap

    if name:
        return NAME_CAPS.get(name.lower())

    return None


def cap_for_pynput(key) -> Optional[str]:
    """pynput 版本：先取虚拟键码，取不到再看字符。"""
    vk = getattr(key, "vk", None)
    if vk is None:
        vk = getattr(getattr(key, "value", None), "vk", None)
    return cap_for(
        char=getattr(key, "char", None),
        name=getattr(key, "name", None),
        vk=vk,
    )
