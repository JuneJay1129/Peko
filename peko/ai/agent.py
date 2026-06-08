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
                # 无工具调用 → 最终回复
                if self._on_token:
                    # 有 token 回调 → 流式输出
                    current = [""]

                    def _on_token(token: str):
                        current[0] += token
                        if self._on_token:
                            self._on_token(token)

                    result_text = stream_chat(self._messages, on_token=_on_token)
                    # 用流式累积的结果覆盖（stream_chat 的返回值可能为空）
                    final = current[0] if current[0] else result_text
                    # 替换最后一条 assistant 消息为流式结果
                    self._messages[-1]["content"] = final
                    return final
                else:
                    return resp.content

            # 有工具调用 → 执行工具 → 继续下一轮
            for tc in resp.tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = tc["function"]["arguments"]
                self._on_status(f"🔧 正在使用 {fn_name}...")
                result = call_tool(fn_name, fn_args)
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result.output if result.success else f"错误: {result.error}",
                })

        return "（达到最大工具调用轮数，请重试）"
