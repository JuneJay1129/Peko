import unittest
from unittest import mock

from peko import main as main_module


class MainModuleTests(unittest.TestCase):
    def test_tray_is_available_returns_true_when_qt_reports_true(self):
        with mock.patch.object(main_module.QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
            self.assertTrue(main_module._tray_is_available())

    def test_tray_is_available_returns_false_on_qt_error(self):
        with mock.patch.object(main_module.QSystemTrayIcon, "isSystemTrayAvailable", side_effect=RuntimeError("boom")):
            self.assertFalse(main_module._tray_is_available())

    def test_create_tray_icon_returns_none_when_system_tray_unavailable(self):
        with mock.patch.object(main_module, "_tray_is_available", return_value=False), \
             mock.patch.object(main_module, "TrayIcon") as tray_cls:
            tray = main_module._create_tray_icon(app=object(), pet_holder=[])

        self.assertIsNone(tray)
        tray_cls.assert_not_called()

    def test_create_tray_icon_builds_tray_when_available(self):
        sentinel = object()
        with mock.patch.object(main_module, "_tray_is_available", return_value=True), \
             mock.patch.object(main_module, "TrayIcon", return_value=sentinel) as tray_cls:
            tray = main_module._create_tray_icon(app="app", pet_holder=["pet"], on_switch_pet="switch", clone_pets=[1], set_clone_mode="clone")

        self.assertIs(tray, sentinel)
        tray_cls.assert_called_once_with(
            "app",
            ["pet"],
            on_switch_pet="switch",
            clone_pets=[1],
            set_clone_mode="clone",
        )


if __name__ == "__main__":
    unittest.main()
