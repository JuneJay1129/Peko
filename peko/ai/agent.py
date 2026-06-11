"""
Peko Agent Loop — 最小工具调用循环。
LLM 可自主决定是否调用工具（如 web_search），最多执行 MAX_ROUNDS 轮。
"""
from __future__ import annotations
import json
from typing import Any, Callable, Dict, List, Optional
from .service import AgentResponse, chat_with_tools, stream_chat
from ..tools import get_openai_tools, call_tool


MAX_ROUNDS = 3  # 工具调用最多轮数


class AgentLoop:
    """
    轻量 Agent 循环。
    - 维护对话历史（messages）
    - 调用 LLM，若返回 tool_calls 则执行工具后重试
    - 最终回复通过 on_token 流式返回
    """

    def __init__(
        self,
        system_prompt: str,
        on_status: Optional[Callable[[str], None]] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ):
        self._system_prompt = system_prompt
        self._on_status = on_status or (lambda _: None)
        self._on_token = on_token
        self._messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

    @property
    def messages(self) -> List[Dict[str, Any]]:
        return list(self._messages)

    def clear(self) -> None:
        """重置对话（保留 system prompt）。"""
        self._messages = [{"role": "system", "content": self._system_prompt}]

    def load_history(self, messages: List[Dict[str, Any]]) -> None:
        """用指定会话历史重建模型上下文（保留 system prompt）。"""
        allowed_roles = {"user", "assistant"}
        history: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role not in allowed_roles or not isinstance(content, str):
                continue
            history.append({"role": role, "content": content})
        self._messages = [{"role": "system", "content": self._system_prompt}, *history]

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt
        if self._messages and self._messages[0]["role"] == "system":
            self._messages[0]["content"] = prompt

    def chat(self, user_input: str) -> str:
        """
        执行一轮对话（含工具调用循环）。
        返回最终文本回复。
        """
        self._messages.append({"role": "user", "content": user_input})
        tools = get_openai_tools()

        for round_i in range(MAX_ROUNDS):
            resp = chat_with_tools(self._messages, tools=tools if tools else None)
            # 记录 assistant 回复
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": resp.content}
            if resp.has_tool_calls:
                assistant_msg["tool_calls"] = resp.tool_calls
            self._messages.append(assistant_msg)

            if not resp.has_tool_calls:
                # 无工具调用 → 流式获取最终回复
                content = resp.content or ""
                if self._on_token:
                    # 去掉 chat_with_tools 已追加的 assistant 消息，用流式重新获取
                    self._messages.pop()
                    current = [""]

                    def _on_token(token: str):
                        current[0] += token
                        if self._on_token:
                            self._on_token(token)

                    result_text = stream_chat(self._messages, on_token=_on_token)
                    content = current[0] or result_text
                    self._messages.append({"role": "assistant", "content": content})
                    return content
                else:
                    self._messages[-1]["content"] = content
                    return content

            # 有工具调用 → 执行工具 → 继续下一轮
            for tc in resp.tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = tc["function"]["arguments"]
                print(f"正在使用 {fn_name}...", flush=True)
                self._on_status(f"🔧 正在使用 {fn_name}...")
                result = call_tool(fn_name, fn_args)
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result.output if result.success else f"错误: {result.error}",
                })

        return "（达到最大工具调用轮数，请重试）"
