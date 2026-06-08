"""
工具基类和结果类型。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ToolResult:
    """工具执行结果。"""
    success: bool
    output: str
    data: Any = None
    error: Optional[str] = None

    @staticmethod
    def ok(output: str, data: Any = None) -> "ToolResult":
        return ToolResult(success=True, output=output, data=data)

    @staticmethod
    def fail(error: str) -> "ToolResult":
        return ToolResult(success=False, output="", error=error)


class BaseTool:
    """工具基类。所有工具继承此类。"""
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}

    def execute(self, **kwargs) -> ToolResult:
        raise NotImplementedError

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
