"""
宠物包管理器（仿 SimuEngine 的 topicManager）
- 从 pets/<pet_id>/ 目录加载宠物配置，每个宠物像 topic 一样独立
- 支持公共插槽（如 AI 模型）与每宠物独立插槽（后续可扩展不同功能）
- 打包为 exe 时：pets 从包内资源目录读取
"""
import os
import sys
import json
from typing import Dict, List, Any, Optional

# 项目根目录（peko/core/ -> 项目根）；打包后使用 PyInstaller 解压目录
def _get_root():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = _get_root()
PETS_DIR = os.path.join(_ROOT, "pets")
CONFIG_FILENAME = "pet_config.json"
RESOURCE_DIR = "resource"  # 每个宠物独立 resource 目录名


def get_app_exe_icon_path() -> str:
    """
    与 main.spec 中打包 exe 所用图标一致的文件路径（开发时为项目根，frozen 时为 _MEIPASS 或 exe 同目录）。
    查找顺序与 spec 一致：macOS 优先 icon.icns，否则 icon.ico、inco.ico；其他平台 icon.ico、inco.ico。
    """
    if sys.platform == "darwin":
        names = ("icon.icns", "icon.ico", "inco.ico")
    else:
        names = ("icon.ico", "inco.ico")
    roots = [_ROOT]
    if getattr(sys, "frozen", False):
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    for root in roots:
        for name in names:
            p = os.path.join(root, name)
            if os.path.isfile(p):
                return p
    return ""


_pet_registry: Dict[str, Dict[str, Any]] = {}


def _load_animations(pet_dir: str, raw: Any) -> Dict[str, Any]:
    """
    解析 animations：每个 state 为 { "frames": [路径列表], "frameRate"?, "stateSwitchInterval"?, "moveSpeed"? }。
    路径均相对宠物目录解析，其余 key 原样保留。
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for state, value in raw.items():
        if not isinstance(value, dict) or "frames" not in value:
            out[state] = {"frames": []}
            continue
        paths = value.get("frames") or []
        extra = {k: v for k, v in value.items() if k != "frames"}
        resolved = []
        for p in paths:
            if isinstance(p, str):
                if os.path.isabs(p):
                    resolved.append(p)
                else:
                    full = os.path.normpath(os.path.join(pet_dir, p))
                    resolved.append(full)
        out[state] = {"frames": resolved, **extra}
    return out


def _load_pet_package(pet_id: str, pet_dir: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(pet_dir, CONFIG_FILENAME)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"宠物配置不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("hidden"):
        return None
    data["id"] = data.get("id") or pet_id
    data["name"] = data.get("name") or pet_id
    data["animations"] = _load_animations(pet_dir, data.get("animations", {}))
    data["character"] = data.get("character") or {}
    data["slots"] = data.get("slots") or {}
    data["bubbleStyle"] = data.get("bubbleStyle") or {}
    data["actionConfig"] = data.get("actionConfig") or {}
    data["randomSayings"] = data.get("randomSayings") or {}
    data["_pet_dir"] = pet_dir  # 宠物目录，供托盘图标等使用
    return data


def discover_pets() -> None:
    """扫描 pets/ 目录，加载所有宠物包并注册。"""
    global _pet_registry
    _pet_registry.clear()
    if not os.path.isdir(PETS_DIR):
        return
    for name in os.listdir(PETS_DIR):
        pet_dir = os.path.join(PETS_DIR, name)
        if not os.path.isdir(pet_dir):
            continue
        config_path = os.path.join(pet_dir, CONFIG_FILENAME)
        if not os.path.isfile(config_path):
            continue
        try:
            pkg = _load_pet_package(name, pet_dir)
            if pkg is None:
                continue
            pid = pkg["id"]
            _pet_registry[pid] = pkg
        except Exception as e:
            print(f"[PetManager] 跳过宠物 {name}: {e}")


def get_available_pets() -> List[str]:
    """返回已注册的宠物 ID 列表。"""
    if not _pet_registry:
        discover_pets()
    return list(_pet_registry.keys())


def get_pet(pet_id: str) -> Dict[str, Any]:
    """获取指定宠物包，不存在则抛错。"""
    if not _pet_registry:
        discover_pets()
    if pet_id not in _pet_registry:
        raise KeyError(f"宠物不存在: {pet_id}")
    return _pet_registry[pet_id]


def has_pet(pet_id: str) -> bool:
    if not _pet_registry:
        discover_pets()
    return pet_id in _pet_registry


def get_default_pet_id() -> str:
    """默认宠物 ID（优先 BB)"""
    avail = get_available_pets()
    if "BB" in avail:
        return "BB"
    return avail[0] if avail else "BB"


def register_pet(pet_id: str, pet_dir: str) -> None:
    """手动注册一个宠物包（用于脚手架后或自定义路径）。"""
    pkg = _load_pet_package(pet_id, pet_dir)
    if pkg is None:
        return
    _pet_registry[pkg["id"]] = pkg
