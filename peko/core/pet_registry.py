"""
当前宠物注册中心（阶段 C 基建）：替代裸 list pet_holder 的隐式全局共享。

此前 main/tray/settings/follower 四处共享同一个 list（pet_holder），
靠约定「[0] 是主宠」传递语义；切宠直接改 list[0]，无任何变更通知。
收敛为 PetRegistry 后：

- 语义显式化：current() / clones() / all_pets()
- 主宠替换有通知：on_master_replaced 注册回调（跟班自动退出等场景）
- bool 语义兼容：if registry: 等价于原来的 if pet_holder:

纯 Python、不依赖 Qt，便于单元测试。
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional


class PetRegistry:
    def __init__(self) -> None:
        self._master: Optional[Any] = None
        self._clones: List[Any] = []
        self._replace_listeners: List[Callable[[Any, Any], None]] = []

    # ---- 读写 ----
    def set_master(self, pet: Any) -> None:
        """替换主宠并广播（回调签名 fn(new_pet, old_pet)）。"""
        old = self._master
        self._master = pet
        for fn in list(self._replace_listeners):
            try:
                fn(pet, old)
            except Exception as e:
                print(f"[PetRegistry] 主宠替换回调异常: {e}")

    def set_clones(self, pets: List[Any]) -> None:
        """同步分身列表引用（分身模式开/关时由 main 调用）。"""
        self._clones = pets if pets is not None else []

    def current(self) -> Optional[Any]:
        return self._master

    def clones(self) -> List[Any]:
        return list(self._clones)

    def all_pets(self) -> List[Any]:
        """主宠 + 分身（主宠在前），用于显示/隐藏/退出等批量操作。"""
        return ([self._master] if self._master is not None else []) + list(self._clones)

    def on_master_replaced(self, fn: Callable[[Any, Any], None]) -> None:
        self._replace_listeners.append(fn)

    # ---- 兼容旧 bool 语义（if pet_holder:）----
    def __bool__(self) -> bool:
        return self._master is not None
