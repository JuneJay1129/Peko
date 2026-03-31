import os
import tempfile
import unittest

from peko.core.runtime_paths import find_app_icon, get_bundle_root, get_writable_root


class RuntimePathTests(unittest.TestCase):
    def test_get_writable_root_for_macos_app_bundle(self):
        root = get_writable_root(
            module_file=__file__,
            frozen=True,
            executable="/Applications/Peko.app/Contents/MacOS/Peko",
            platform_name="darwin",
        )
        self.assertEqual(root, "/Applications")

    def test_get_bundle_root_prefers_meipass_for_frozen_build(self):
        bundle_root = get_bundle_root(
            module_file=__file__,
            frozen=True,
            meipass="/private/var/folders/peko/_MEI12345",
        )
        self.assertEqual(bundle_root, "/private/var/folders/peko/_MEI12345")

    def test_find_app_icon_prefers_icns_for_macos(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            icns_path = os.path.join(temp_dir, "icon.icns")
            ico_path = os.path.join(temp_dir, "icon.ico")
            with open(icns_path, "wb") as handle:
                handle.write(b"icns")
            with open(ico_path, "wb") as handle:
                handle.write(b"ico")

            icon_path = find_app_icon(
                platform_name="darwin",
                bundle_root=temp_dir,
                frozen=False,
            )

            self.assertEqual(icon_path, icns_path)


if __name__ == "__main__":
    unittest.main()
