"""
宠物包管理器（仿 SimuEngine 的 topicManager）
- 从 pets/<pet_id>/ 目录加载宠物配置，每个宠物像 topic 一样独立
- 支持公共插槽（如 AI 模型）与每宠物独立插槽（后续可扩展不同功能）
"""
import os
import json
from typing import Dict, List, Any, Optional

# 项目根目录（peko/core/ -> 项目根）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PETS_DIR = os.path.join(_ROOT, "pets")
CONFIG_FILENAME = "pet_config.json"
RESOURCE_DIR = "resource"  # 每个宠物独立 resource 目录名

_pet_registry: Dict[str, Dict[str, Any]] = {}


def _load_animations(pet_dir: str, raw: Any) -> Dict[str, List[str]]:
    """解析 animations：路径列表，均相对该宠物目录 pets/<id>/ 解析。每个宠物独立 resource，无公共模块。"""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for state, paths in raw.items():
        if isinstance(paths, list):
            resolved = []
            for p in paths:
                if os.path.isabs(p):
                    resolved.append(p)
                else:
                    full = os.path.normpath(os.path.join(pet_dir, p))
                    resolved.append(full)
            out[state] = resolved
        else:
            out[state] = []
    return out


def _load_pet_package(pet_id: str, pet_dir: str) -> Dict[str, Any]:
    path = os.path.join(pet_dir, CONFIG_FILENAME)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"宠物配置不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["id"] = data.get("id") or pet_id
    data["name"] = data.get("name") or pet_id
    data["animations"] = _load_animations(pet_dir, data.get("animations", {}))
    data["character"] = data.get("character") or {}
    data["slots"] = data.get("slots") or {}
    data["bubbleStyle"] = data.get("bubbleStyle") or {}
    data["actionConfig"] = data.get("actionConfig") or {}
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
    _pet_registry[pkg["id"]] = pkg
