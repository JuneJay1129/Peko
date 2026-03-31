"""
Peko AI 服务：统一封装对话调用（仿 SimuEngine 风格）
- 在 config/secrets.json 填写 apiKey、config/api.json 设置 modelId 后，由此模块负责流式调用
- 支持 OpenAI 兼容接口（SiliconFlow / OpenAI / 豆包等）与讯飞星火
"""
import json
from typing import Any, Callable, List, Dict, Optional
from .config_loader import get_ai_config, validate_ai_config, load_user_api_config, get_model_by_id

# 可选：使用 openai 包兼容任意 base_url（SiliconFlow、豆包等）
try:
    from openai import OpenAI
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# 讯飞星火
try:
    from sparkai.llm.llm import ChatSparkLLM
    from sparkai.core.messages import ChatMessage
    _HAS_SPARK = True
except ImportError:
    _HAS_SPARK = False


def _stream_chat_http(
    api_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.8,
    max_tokens: int = 2000,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    """直接用 HTTP 请求完整 URL，与 curl 一致，避免 base_url 拼接导致 404。"""
    if not _HAS_REQUESTS:
        raise RuntimeError("请安装 requests 包: pip install requests")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    full = []
    with requests.post(api_url, headers=headers, json=body, stream=True, timeout=60) as r:
        r.raise_for_status()
        r.encoding = "utf-8"  # 流式响应常无 charset，强制按 UTF-8 解码避免乱码
        for line in r.iter_lines(decode_unicode=True):
            if not line or line.strip() != line:
                continue
            if line.startswith("data: "):
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        full.append(text)
                        if on_token:
                            on_token(text)
                except json.JSONDecodeError:
                    continue
    return "".join(full)


def _openai_stream_chat(
    api_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.8,
    max_tokens: int = 2000,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    """使用 OpenAI 兼容接口流式对话，并返回完整回复文本。"""
    if not _HAS_OPENAI:
        raise RuntimeError("请安装 openai 包: pip install openai")
    base_url = api_url.rstrip("/").rsplit("/", 1)[0]  # 去掉 /chat/completions 等路径
    client = OpenAI(base_url=base_url, api_key=api_key)
    full = []
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                text = delta.content
                full.append(text)
                if on_token:
                    on_token(text)
    return "".join(full)


def _spark_stream_chat(
    app_id: str,
    api_key: str,
    api_secret: str,
    url: str,
    domain: str,
    messages: List[Any],
    temperature: float = 0.8,
    max_tokens: int = 2000,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    """讯飞星火流式对话。messages 为 sparkai ChatMessage 列表。"""
    if not _HAS_SPARK:
        raise RuntimeError("请安装 sparkai 包: pip install sparkai")
    spark = ChatSparkLLM(
        spark_api_url=url,
        spark_app_id=app_id,
        spark_api_key=api_key,
        spark_api_secret=api_secret,
        spark_llm_domain=domain,
        request_timeout=30,
        streaming=True,
    )
    collected = []

    class _Handler:
        def on_llm_new_token(self, token: str, **kwargs):
            collected.append(token)
            if on_token:
                on_token(token)

    spark.generate([messages], callbacks=[_Handler()])
    return "".join(collected)


def messages_to_spark(messages: List[Dict[str, str]]) -> List[Any]:
    """将 [{"role":"user","content":"..."}] 转为 sparkai ChatMessage 列表。"""
    out = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        out.append(ChatMessage(role=role, content=content))
    return out


def stream_chat(
    messages: List[Dict[str, str]],
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    """
    使用当前配置（API Key + 所选模型）进行流式对话。
    messages: [{"role":"user"|"assistant"|"system", "content": "..."}]
    on_token: 每收到一个 token 调用一次，用于气泡逐字显示。
    返回完整回复文本。
    """
    if not validate_ai_config():
        raise ValueError("AI 未配置，请在 config/secrets.json 中填写 apiKey，并在 config/api.json 中设置 modelId")
    cfg = get_ai_config()
    provider = cfg.get("provider", "openai")
    temperature = cfg.get("temperature", 0.8)
    max_tokens = cfg.get("maxTokens", 2000)

    # 打印请求到控制台（apiKey 脱敏）
    req_info = {
        "provider": provider,
        "model": cfg.get("model"),
        "apiUrl": cfg.get("apiUrl"),
        "temperature": temperature,
        "maxTokens": max_tokens,
        "messages": messages,
    }
    if cfg.get("apiKey"):
        req_info["apiKey"] = cfg["apiKey"][:8] + "***" if len(cfg["apiKey"]) > 8 else "***"
    print("[Peko API 请求]", req_info)

    if provider == "spark":
        import os
        user = load_user_api_config()
        app_id = user.get("sparkAppId") or os.environ.get("SPARKAI_APP_ID", "")
        api_key = user.get("sparkApiKey") or user.get("apiKey") or os.environ.get("SPARKAI_API_KEY", "")
        api_secret = user.get("sparkApiSecret") or os.environ.get("SPARKAI_API_SECRET", "")
        url = user.get("sparkUrl") or os.environ.get("SPARKAI_URL", "wss://spark-api.xf-yun.com/v1.1/chat")
        domain = user.get("sparkDomain") or os.environ.get("SPARKAI_DOMAIN", "lite")
        spark_messages = messages_to_spark(messages)
        result = _spark_stream_chat(
            app_id=app_id,
            api_key=api_key,
            api_secret=api_secret,
            url=url,
            domain=domain,
            messages=spark_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            on_token=on_token,
        )
        print("[Peko API 返回]", result)
        return result
    else:
        # 所有带 apiUrl 的 OpenAI 兼容接口均用 HTTP 直接发送，确保请求体（model、messages、temperature、max_tokens、stream）完整带上
        if _HAS_REQUESTS and cfg.get("apiUrl"):
            result = _stream_chat_http(
                api_url=cfg["apiUrl"],
                api_key=cfg["apiKey"],
                model=cfg["model"],
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                on_token=on_token,
            )
        else:
            result = _openai_stream_chat(
                api_url=cfg["apiUrl"],
                api_key=cfg["apiKey"],
                model=cfg["model"],
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                on_token=on_token,
            )
        print("[Peko API 返回]", result)
        return result


def get_current_model_name() -> str:
    """返回当前选中模型的显示名称，用于 UI。"""
    cfg = get_ai_config()
    mid = cfg.get("modelId")
    m = get_model_by_id(mid) if mid else None
    return (m.get("name") if m else None) or mid or "未选择"
