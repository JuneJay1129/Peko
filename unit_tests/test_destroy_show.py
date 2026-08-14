"""摧毁表演（托盘选文件 → 点位置 → 跑过去摧毁）集成测试。

依赖 PyQt5 + BB 宠物素材，仅能在系统 Python（装了 PyQt5）下运行；
无 PyQt5 的环境（如 managed Python）自动跳过。
离屏运行：QT_QPA_PLATFORM=offscreen。

注意：
- 必须 setQuitOnLastWindowClosed(False) 且 pet.show()，否则确认窗关闭会被
  Qt 视为「最后一个窗口关闭」而退出事件循环，后续定时器全部失效（测试环境特有陷阱）。
- 真实删除（send2trash / PowerShell）在开发沙箱里会被拦截，测试中把 _trash_one
  换成可确定的桩（os.remove）；真实删除由手动测试验证。
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5.QtCore import QPoint, QTimer
    from PyQt5.QtWidgets import QApplication

    from peko.core.pet_manager import get_pet
    from peko.ui.pet import DesktopPet
    from peko.ui import destroy_show

    HAS_QT = True
except Exception:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "需要 PyQt5（系统 Python）")
class DestroyShowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.pet = DesktopPet(get_pet("hamster"))  # pets/BB 注册 id 为 hamster，23 动作含 fight
        self.pet.show()
        # 桩掉真实删除：记录调用并用 os.remove 模拟「进回收站」
        self.trashed = []
        self._orig_trash = destroy_show._trash_one

        def fake_trash(path):
            self.trashed.append(path)
            if os.path.exists(path):
                os.remove(path)
            return None

        destroy_show._trash_one = fake_trash

    def tearDown(self):
        destroy_show._trash_one = self._orig_trash
        self.pet.close()
        self.pet.deleteLater()

    def _make_target(self):
        fd, path = tempfile.mkstemp(prefix="peko_destroy_test_", suffix=".txt")
        os.write(fd, b"x")
        os.close(fd)
        return path

    def _drive(self, decision, timeout_ms=14000):
        """驱动事件 loop：确认窗出现后按 decision 处理（accept/reject），直到表演结束。"""

        def act_on_dialog():
            show = getattr(self.pet, "_destroy_show", None)
            dlg = getattr(show, "_dlg", None) if show else None
            if dlg is not None:
                getattr(dlg, decision)()
            else:
                QTimer.singleShot(150, act_on_dialog)

        def check_done():
            show = getattr(self.pet, "_destroy_show", None)
            if show is None and not self.pet._destroy_running:
                self.app.quit()
            else:
                QTimer.singleShot(150, check_done)

        QTimer.singleShot(1200, act_on_dialog)
        QTimer.singleShot(1400, check_done)
        QTimer.singleShot(timeout_ms, self.app.quit)
        self.app.exec_()

    def _home_xy(self):
        screen = QApplication.desktop().screenGeometry()
        return (screen.width() - self.pet.width() - 20,
                screen.height() - self.pet.height() - 50)

    def test_full_destroy_flow_walks_to_target_and_deletes(self):
        target = self._make_target()
        spot = QPoint(self.pet.x() + 300, self.pet.y())  # 右侧 300px 处
        started = destroy_show.start_destroy_show_at(self.pet, [target], spot)
        self.assertTrue(started)
        self.assertTrue(self.pet._destroy_running)
        self.assertIn(self.pet.current_state, ("walk_right", "walk_left"))
        self._drive("accept")
        self.assertEqual(self.trashed, [target])       # 删除被触发
        self.assertFalse(os.path.exists(target))
        self.assertEqual(self.pet.current_state, "stand")
        self.assertFalse(self.pet._destroy_running)
        # 收场后应跑回桌面右下角（老家）
        home_x, home_y = self._home_xy()
        self.assertLess(abs(self.pet.x() - home_x), 5)
        self.assertLess(abs(self.pet.y() - home_y), 5)
        # 冻结的 moveSpeed 已恢复
        self.assertNotEqual(self.pet._state_config.get("walk_right", {}).get("moveSpeed"), 0)

    def test_cancel_keeps_file(self):
        target = self._make_target()
        spot = QPoint(self.pet.x() + 200, self.pet.y())
        destroy_show.start_destroy_show_at(self.pet, [target], spot)
        self._drive("reject")
        self.assertEqual(self.trashed, [])              # 取消则不删
        self.assertTrue(os.path.exists(target))
        self.assertEqual(self.pet.current_state, "stand")
        os.remove(target)

    def test_pet_without_fight_is_refused(self):
        class FakePet:
            animations = {"stand": ["x"], "walk_left": ["x"]}
            control_mode = False
            follow_mouse_mode = False
            _destroy_running = False
            bubbles = []

            def update_bubble(self, text, duration=3000):
                FakePet.bubbles.append(text)

        ok = destroy_show.start_destroy_show_at(FakePet(), ["whatever.txt"], QPoint(100, 100))
        self.assertFalse(ok)
        self.assertTrue(FakePet.bubbles)


@unittest.skipUnless(HAS_QT, "需要 PyQt5（系统 Python）")
class TrashOneTests(unittest.TestCase):
    """_trash_one 的确定性分支（不依赖真实回收站）。"""

    def test_missing_file_returns_reason(self):
        from peko.ui.destroy_show import _trash_one
        self.assertEqual(_trash_one("D:/definitely/not/exist_12345.txt"), "文件不存在")


class FilePickerTests(unittest.TestCase):
    """狙击点选的名称匹配（纯函数，managed Python 可跑）。"""

    def test_exact_and_stem_match(self):
        from peko.core.file_picker import match_name_in_folder
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "测试报告.txt")
            with open(p, "w") as f:
                f.write("x")
            # 全名精确
            self.assertEqual(match_name_in_folder(tmp, "测试报告.txt"), p)
            # 去扩展名（资源管理器隐藏扩展名时的显示名）
            self.assertEqual(match_name_in_folder(tmp, "测试报告"), p)
            # 大小写不敏感
            self.assertEqual(match_name_in_folder(tmp, "测试报告.TXT"), p)
            # 不存在 → None
            self.assertIsNone(match_name_in_folder(tmp, "不存在"))
            self.assertIsNone(match_name_in_folder(tmp, ""))
            self.assertIsNone(match_name_in_folder("D:/no/such/dir", "测试报告"))


if __name__ == "__main__":
    unittest.main()
