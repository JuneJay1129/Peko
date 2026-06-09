"""update_mood 工具：让 Agent 在对话中调整宠物心情/饱食度/精力。"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from .base import BaseTool, ToolResult

if TYPE_CHECKING:
    from ..core.mood import MoodEngine

# 全局 MoodEngine 引用，由 pet.py 初始化时注入
_mood_engine: Optional["MoodEngine"] = None


def set_mood_engine(engine: "MoodEngine") -> None:
    """注册 MoodEngine 实例，供 update_mood 工具使用。"""
    global _mood_engine
    _mood_engine = engine


class UpdateMoodTool(BaseTool):
    name = "update_mood"
    description = (
        "根据对话内容调整宠物的心情、饱食度或精力。"
        "正数表示增加，负数表示减少。"
        "只在对话内容确实应该影响宠物状态时才调用，不要每次对话都调用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "mood_delta": {
                "type": "integer",
                "description": "心情变化值，范围 -20 到 +20。例如被夸奖 +10，被骂 -15",
            },
            "satiety_delta": {
                "type": "integer",
                "description": "饱食度变化值，范围 -15 到 +15。例如用户说喂食 +10",
            },
            "energy_delta": {
                "type": "integer",
                "description": "精力变化值，范围 -15 到 +15。例如用户说去休息 +10，剧烈运动 -10",
            },
            "reason": {
                "type": "string",
                "description": "变化原因，用于日志和上下文",
            },
        },
        "required": [],
    }

    def execute(
        self,
        mood_delta: int = 0,
        satiety_delta: int = 0,
        energy_delta: int = 0,
        reason: str = "",
        **kwargs,
    ) -> ToolResult:
        if _mood_engine is None:
            return ToolResult.fail("心情系统未初始化。")

        mood_delta = max(-20, min(20, int(mood_delta)))
        satiety_delta = max(-15, min(15, int(satiety_delta)))
        energy_delta = max(-15, min(15, int(energy_delta)))

        snap = _mood_engine.snapshot
        old_mood = snap.mood_score
        old_satiety = snap.satiety
        old_energy = snap.energy

        snap.mood_score = max(0, min(100, snap.mood_score + mood_delta))
        snap.satiety = max(0, min(100, snap.satiety + satiety_delta))
        snap.energy = max(0, min(100, snap.energy + energy_delta))
        _mood_engine.save()

        parts = []
        if mood_delta:
            parts.append(f"心情 {old_mood}→{snap.mood_score}")
        if satiety_delta:
            parts.append(f"饱食 {old_satiety}→{snap.satiety}")
        if energy_delta:
            parts.append(f"精力 {old_energy}→{snap.energy}")

        desc = "、".join(parts) if parts else "无变化"
        reason_str = f"（{reason}）" if reason else ""
        return ToolResult.ok(f"状态已更新{reason_str}：{desc}")
