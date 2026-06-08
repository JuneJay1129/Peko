"""
本地文件工具：读取文件、AI 摘要。
"""
from __future__ import annotations

from .base import BaseTool, ToolResult
from .file_utils import (
    MAX_SUMMARY_CHARS,
    format_file_meta,
    read_text_file,
    resolve_allowed_path,
)


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "读取本地文本文件内容，返回文件正文。"
        "适合查看代码、日志、Markdown、配置文件等。"
        "若用户需要摘要或要点，请使用 summarize_file。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径，支持相对或绝对路径",
            },
            "max_chars": {
                "type": "integer",
                "description": "最多返回字符数，默认 8000",
                "default": 8000,
            },
        },
        "required": ["file_path"],
    }

    def execute(self, file_path: str, max_chars: int = 8000, **kwargs) -> ToolResult:
        try:
            limit = max(500, min(int(max_chars or 8000), MAX_SUMMARY_CHARS))
            content, meta = read_text_file(file_path, max_chars=limit)
            header = format_file_meta(meta)
            body = f"{header}\n\n---\n{content}\n---"
            return ToolResult.ok(body, data={"meta": meta, "content": content})
        except Exception as e:
            return ToolResult.fail(str(e))


class SummarizeFileTool(BaseTool):
    name = "summarize_file"
    description = (
        "读取本地文本文件并用 AI 生成中文摘要。"
        "适合用户说「帮我总结这个文件」「这个文档讲了什么」等。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要总结的文件路径",
            },
            "focus": {
                "type": "string",
                "description": "可选，摘要时重点关注的方向，如「技术架构」「待办事项」",
            },
        },
        "required": ["file_path"],
    }

    def execute(self, file_path: str, focus: str = "", **kwargs) -> ToolResult:
        try:
            content, meta = read_text_file(file_path, max_chars=MAX_SUMMARY_CHARS)
            summary = self._summarize(content, meta, focus or "")
            if not summary:
                return ToolResult.fail("摘要生成失败，请检查 AI 配置")
            header = format_file_meta(meta)
            output = f"{header}\n\n【摘要】\n{summary}"
            return ToolResult.ok(output, data={"meta": meta, "summary": summary})
        except Exception as e:
            return ToolResult.fail(str(e))

    @staticmethod
    def _summarize(content: str, meta: dict, focus: str) -> str:
        from ..ai.config_loader import validate_ai_config
        from ..ai.service import chat_with_tools

        if not validate_ai_config():
            raise ValueError("AI 未配置，无法生成文件摘要")

        instruction = "请用中文简洁总结以下文件内容，分点列出关键信息。"
        if focus.strip():
            instruction += f" 重点关注：{focus.strip()}"

        messages = [
            {
                "role": "system",
                "content": (
                    "你是文件摘要助手。输出简洁的中文摘要，"
                    "使用条目列表，不要编造文件中不存在的信息。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{instruction}\n\n"
                    f"文件：{meta.get('name')}\n"
                    f"路径：{meta.get('path')}\n"
                    f"{'（内容已截断）' if meta.get('truncated') else ''}\n\n"
                    f"---\n{content}\n---"
                ),
            },
        ]
        resp = chat_with_tools(messages, tools=None)
        return (resp.content or "").strip()
