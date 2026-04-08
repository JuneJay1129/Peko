"""Shared runtime path helpers for source and frozen builds."""

from __future__ import annotations

import os
import sys
from pathlib import PurePosixPath
from typing import Optional

APP_NAME = "Peko"
APP_SUPPORT_ENV_VAR = "PEKO_APP_SUPPORT_DIR"
APP_SUPPORT_RELATIVE_DIR = os.path.join("Library", "Application Support", APP_NAME)


def _project_root_from(module_file: Optional[str] = None) -> str:
    path = os.path.abspath(module_file or __file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(path)))


def _current_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _find_macos_app_bundle(executable: str) -> Optional[str]:
    current = _parent_dir(_normalize_path(executable))
    while current and current != _parent_dir(current):
        if current.lower().endswith(".app"):
            return current
        current = _parent_dir(current)
    return None


def _is_posix_absolute(path: str) -> bool:
    return path.startswith("/")


def _normalize_path(path: str) -> str:
    if _is_posix_absolute(path):
        return str(PurePosixPath(path))
    return os.path.abspath(path)


def _parent_dir(path: str) -> str:
    if _is_posix_absolute(path):
        return str(PurePosixPath(path).parent)
    return os.path.dirname(os.path.abspath(path))


def _get_macos_app_support_dir() -> str:
    override = os.environ.get(APP_SUPPORT_ENV_VAR)
    if override:
        return _normalize_path(override)
    home = str(PurePosixPath(os.path.expanduser("~")))
    return str(PurePosixPath(home) / "Library" / "Application Support" / APP_NAME)



def get_writable_root(
    module_file: Optional[str] = None,
    *,
    frozen: Optional[bool] = None,
    executable: Optional[str] = None,
    platform_name: Optional[str] = None,
) -> str:
    """Return the writable root directory for config/state files."""
    is_frozen = _current_frozen() if frozen is None else bool(frozen)
    if not is_frozen:
        return _project_root_from(module_file)

    exe_path = _normalize_path(executable or sys.executable)
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        return _get_macos_app_support_dir()
    return _parent_dir(exe_path)


def get_bundle_root(
    module_file: Optional[str] = None,
    *,
    frozen: Optional[bool] = None,
    meipass: Optional[str] = None,
    executable: Optional[str] = None,
) -> str:
    """Return the resource root used to read bundled assets."""
    is_frozen = _current_frozen() if frozen is None else bool(frozen)
    if not is_frozen:
        return _project_root_from(module_file)

    bundle_root = meipass or getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return _normalize_path(bundle_root)
    return _parent_dir(_normalize_path(executable or sys.executable))


def find_app_icon(
    *,
    platform_name: Optional[str] = None,
    bundle_root: Optional[str] = None,
    executable: Optional[str] = None,
    frozen: Optional[bool] = None,
) -> str:
    """Find the packaged application icon using the same precedence as the build."""
    platform_name = platform_name or sys.platform
    is_frozen = _current_frozen() if frozen is None else bool(frozen)
    names = ("icon.icns", "icon.ico", "inco.ico") if platform_name == "darwin" else ("icon.ico", "inco.ico")

    roots = []
    if bundle_root:
        roots.append(_normalize_path(bundle_root))
    if is_frozen and executable:
        roots.append(_parent_dir(_normalize_path(executable)))

    seen = set()
    unique_roots = [root for root in roots if not (root in seen or seen.add(root))]
    for root in unique_roots:
        for name in names:
            path = os.path.join(root, name)
            if os.path.isfile(path):
                return path
    return ""
