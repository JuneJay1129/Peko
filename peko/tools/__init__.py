"""
Peko 工具注册表。
"""
from __future__ import annotations
import json
from typing import Dict, List, Any, Optional
from .base import BaseTool, ToolResult

_registry: Dict[str, BaseTool] = {}


def register(tool: BaseTool) -> None:
    _registry[tool.name] = tool


def get_tool(name: str) -> Optional[BaseTool]:
    return _registry.get(name)


def get_all_tools() -> List[BaseTool]:
    return list(_registry.values())


def get_openai_tools() -> List[Dict[str, Any]]:
    return [t.to_openai_schema() for t in _registry.values()]


def call_tool(name: str, arguments: str | Dict[str, Any]) -> ToolResult:
    tool = _registry.get(name)
    if tool is None:
        return ToolResult.fail(f"未知工具: {name}")
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments)
        else:
            args = arguments
        return tool.execute(**args)
    except Exception as e:
        return ToolResult.fail(f"工具 {name} 执行出错: {e}")


# Auto-register built-in tools
from .web_search import WebSearchTool  # noqa: E402, F401

register(WebSearchTool())
