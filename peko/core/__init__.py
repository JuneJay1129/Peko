"""核心逻辑：宠物包管理"""
from .pet_manager import (
    RESOURCE_DIR,
    discover_pets,
    get_available_pets,
    get_pet,
    get_default_pet_id,
    has_pet,
    register_pet,
)

__all__ = [
    "RESOURCE_DIR",
    "discover_pets",
    "get_available_pets",
    "get_pet",
    "get_default_pet_id",
    "has_pet",
    "register_pet",
]
