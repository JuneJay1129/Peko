"""
Peko AI 服务：统一封装 OpenAI 兼容对话调用
- 配置只需三要素（API URL + Key + 模型名），对接任意 OpenAI 兼容服务
- 流式调用：优先直接 HTTP（与 curl 一致，避免 base_url 拼接 404），缺失时用 openai SDK
"""
import json
from typing import Any, Callable, List, Dict, Optional, Tuple
from .config_loader import get_ai_config, validate_ai_config

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


def _ensure_chat_completions_url(api_url: str) -> str:
    """兼容填基础地址（base URL）：若不以 /chat/completions 结尾，自动补全。

    火山方舟、OpenAI、SiliconFlow 等 OpenAI 兼容服务的接口都是 <base>/chat/completions；
    用户填 base（如 .../api/coding/v3）或完整端点都行。
    """
    url = (api_url or "").strip().rstrip("/")
    if not url:
        return url
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


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
    api_url = _ensure_chat_completions_url(api_url)
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
    api_url = _ensure_chat_completions_url(api_url)
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


def stream_chat(
    messages: List[Dict[str, str]],
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    """
    使用当前配置（API URL + Key + 模型名）进行流式对话。
    messages: [{"role":"user"|"assistant"|"system", "content": "..."}]
    on_token: 每收到一个 token 调用一次，用于气泡逐字显示。
    返回完整回复文本。
    """
    if not validate_ai_config():
        raise ValueError(
            "AI 未配置：请在「AI 设置」里填入 API URL / Key / 模型名"
        )
    cfg = get_ai_config()
    temperature = cfg.get("temperature", 0.8)
    max_tokens = cfg.get("maxTokens", 2000)

    # 打印请求到控制台（apiKey 脱敏）
    req_info = {
        "model": cfg.get("model"),
        "apiUrl": cfg.get("apiUrl"),
        "temperature": temperature,
        "maxTokens": max_tokens,
        "messages": messages,
    }
    if cfg.get("apiKey"):
        key = cfg["apiKey"]
        req_info["apiKey"] = key[:8] + "***" if len(key) > 8 else "***"
    print("[Peko API 请求]", req_info)

    # 所有带 apiUrl 的 OpenAI 兼容接口均用 HTTP 直接发送，确保请求体完整带上
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


def _try_connection(url: str, api_key: str, model: str, timeout: float) -> Tuple[bool, str]:
    """对单个 URL 发一次最小请求，返回 (ok, 说明)。"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "stream": False,
    }
    r = requests.post(url, headers=headers, json=body, timeout=timeout)
    if r.status_code == 200:
        return True, "接口可用 ✓"
    try:
        err = (r.json().get("error") or {}).get("message") or r.text[:160]
    except Exception:
        err = r.text[:160]
    return False, f"HTTP {r.status_code}: {err}"


def test_connection(
    api_url: str,
    api_key: str,
    model: str,
    timeout: float = 15,
) -> Tuple[bool, str]:
    """向配置的接口发一次最小请求验证可用性，供「AI 设置」页测试连接。返回 (ok, message)。

    兼容两种填法：直接填完整端点（.../chat/completions），或填基础地址（base URL）；
    基础地址首次 404 时会自动补全 /chat/completions 再试一次。
    """
    api_url = (api_url or "").strip()
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    if not api_url or not api_key or not model:
        return False, "请先完整填写 API URL / Key / 模型名"
    if not _HAS_REQUESTS:
        return False, "缺少 requests 库"

    # 候选：原样 + 补全 /chat/completions（去重保序）
    normalized = _ensure_chat_completions_url(api_url)
    candidates = []
    for u in (api_url, normalized):
        if u and u not in candidates:
            candidates.append(u)

    last = ""
    for url in candidates:
        try:
            ok, msg = _try_connection(url, api_key, model, timeout)
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        if ok:
            auto = "（自动补全 /chat/completions）" if url != api_url else ""
            return True, f"连接成功，接口可用 {auto}✓"
        # 路径类错误（404/403）说明可能差后缀，尝试下一个候选；其余错误直接返回
        if msg.startswith("HTTP 404") or msg.startswith("HTTP 403") or msg.startswith("HTTP 405"):
            last = msg
            continue
        return False, msg
    return False, last or "无法连接"


def get_current_model_name() -> str:
    """返回当前模型的显示名称（v2 下即模型名）。"""
    cfg = get_ai_config()
    return cfg.get("model") or cfg.get("modelId") or "未配置"
