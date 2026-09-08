"""
Peko API 配置加载器（v2：通用 OpenAI 兼容三要素）

- 用户只需配置三要素：API URL + API Key + 模型名，即可对接任意 OpenAI 兼容服务
  （SiliconFlow / DeepSeek / Kimi / GLM / 通义 / OpenRouter / 本地 Ollama 等）。
- apiKey 写入 config/secrets.json（gitignore）；API URL / 模型名写入 config/api.json。
- 兼容旧版 v1（models 数组 + modelId）配置：读取时自动迁移为 v2 并落盘。
- 打包时：config 模板从包内读取，首次运行复制到可写目录
  （Windows 为 exe 同目录，macOS 为 ~/Library/Application Support/Peko）。
"""
import json
import os
import sys
import shutil
from typing import Optional, List, Dict, Any
from ..core.runtime_paths import get_bundle_root, get_writable_root

# 项目根目录（peko/ai/ -> 项目根）；打包后配置写到可写运行目录：Windows 为 exe 所在目录，macOS 为 ~/Library/Application Support/Peko。
_ROOT = get_writable_root(module_file=__file__)
_BUNDLE = get_bundle_root(module_file=__file__)
CONFIG_DIR = os.path.join(_ROOT, "config")
API_CONFIG_PATH = os.path.join(CONFIG_DIR, "api.json")
API_CONFIG_EXAMPLE_PATH = os.path.join(_BUNDLE, "config", "api.json.example")
SECRETS_PATH = os.path.join(CONFIG_DIR, "secrets.json")
SECRETS_EXAMPLE_PATH = os.path.join(_BUNDLE, "config", "secrets.json.example")
_USER_API_LEGACY_PATH = os.path.join(CONFIG_DIR, "user_api.json")

_cached_api_config: Optional[Dict[str, Any]] = None

# 基础默认参数（简单聊天够用，不要求用户配置）
DEFAULT_TEMPERATURE = 0.8
DEFAULT_MAX_TOKENS = 2000


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _merge_legacy_user_api(data: Dict[str, Any]) -> Dict[str, Any]:
    """若 api.json 中无 apiKey 且存在 user_api.json，则合并（一次性迁移）。"""
    if data.get("apiKey") or not os.path.isfile(_USER_API_LEGACY_PATH):
        return data
    legacy = _load_json(_USER_API_LEGACY_PATH)
    if not legacy:
        return data
    if legacy.get("apiKey"):
        data["apiKey"] = legacy["apiKey"]
    if legacy.get("modelId"):
        data["modelId"] = legacy["modelId"]
    if legacy.get("model") and not data.get("model"):
        data["model"] = legacy["model"]
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        _save_secrets(data.get("apiKey", ""))
        full = _load_json(API_CONFIG_PATH) or {}
        full["modelId"] = data.get("modelId", full.get("model", ""))
        with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return data


def _pick_model_from_v1(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """旧版 v1：从 models 数组里选当前模型（modelId/defaultModel → 第一个 enabled → 第一个）。"""
    models = data.get("models") or []
    if not models:
        return None
    mid = data.get("modelId") or data.get("defaultModel")
    for m in models:
        if m.get("id") == mid:
            return m
    for m in models:
        if m.get("enabled", True):
            return m
    return models[0]


def _normalize(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把 v1/v2 原始配置规范化为内部统一结构（含当前选中模型的 apiUrl/model/modelId）。"""
    out = dict(data or {})
    out.setdefault("provider", "openai")
    out.setdefault("temperature", DEFAULT_TEMPERATURE)
    out.setdefault("maxTokens", DEFAULT_MAX_TOKENS)
    if out.get("apiUrl") and out.get("model"):
        # v2：顶层即三要素
        out.setdefault("modelId", out["model"])
        return out
    # v1：从 models 数组取当前模型
    m = _pick_model_from_v1(out)
    if m:
        out["apiUrl"] = m.get("apiUrl") or ""
        out["model"] = m.get("model") or ""
        out["modelId"] = m.get("id") or m.get("model") or ""
        out.setdefault("temperature", m.get("temperature", DEFAULT_TEMPERATURE))
        out.setdefault("maxTokens", m.get("maxTokens", DEFAULT_MAX_TOKENS))
        out.setdefault("provider", m.get("provider", "openai"))
    else:
        out.setdefault("apiUrl", "")
        out.setdefault("model", "")
        out.setdefault("modelId", "")
    return out


def _to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """内部结构 → v2 落盘格式（apiKey 永远不写进 api.json）。"""
    return {
        "version": "2.0.0",
        "description": "Peko 桌宠 AI 配置：填入 API URL / Key / 模型名即可，任意 OpenAI 兼容服务通用。",
        "apiUrl": data.get("apiUrl", ""),
        "model": data.get("model", ""),
        "modelId": data.get("modelId", data.get("model", "")),
        "provider": data.get("provider", "openai"),
        "temperature": data.get("temperature", 0.8),
        "maxTokens": data.get("maxTokens", 2000),
    }


def _load_secrets() -> Dict[str, Any]:
    """从 config/secrets.json 读取 apiKey，不存在则尝试从 example 复制并返回占位。"""
    if os.path.isfile(SECRETS_PATH):
        return _load_json(SECRETS_PATH) or {}
    if os.path.isfile(SECRETS_EXAMPLE_PATH):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            shutil.copy(SECRETS_EXAMPLE_PATH, SECRETS_PATH)
            return _load_json(SECRETS_PATH) or {}
        except Exception:
            return _load_json(SECRETS_EXAMPLE_PATH) or {}
    return {}


def _save_secrets(api_key: str) -> None:
    """将 apiKey 写入 config/secrets.json。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = _load_json(SECRETS_PATH) or {}
    data["apiKey"] = api_key
    with open(SECRETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_api_config() -> Dict[str, Any]:
    """加载配置（v1/v2 均可）并返回规范化结果（含 apiKey）。"""
    global _cached_api_config
    if _cached_api_config is not None:
        return _cached_api_config
    path = API_CONFIG_PATH if os.path.isfile(API_CONFIG_PATH) else API_CONFIG_EXAMPLE_PATH
    # 打包 exe 首次运行：将 config 模板复制到可写目录，便于用户编辑
    if not os.path.isfile(API_CONFIG_PATH) and getattr(sys, "frozen", False) and os.path.isfile(API_CONFIG_EXAMPLE_PATH):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            shutil.copy(API_CONFIG_EXAMPLE_PATH, API_CONFIG_PATH)
            path = API_CONFIG_PATH
        except Exception:
            pass

    raw = _load_json(path) or {}
    was_v1 = bool(raw.get("models")) and not raw.get("apiUrl")
    data = _normalize(raw)
    data = _merge_legacy_user_api(data)

    # v1 → v2 迁移落盘（仅当本地有 api.json 可写时才改写）
    if was_v1 and os.path.isfile(API_CONFIG_PATH):
        try:
            with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(_to_v2(data), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # 合并 secrets.json 中的 apiKey
    secrets = _load_secrets()
    if secrets.get("apiKey") and secrets["apiKey"] != "your-api-key-here":
        data["apiKey"] = secrets["apiKey"]
    elif data.get("apiKey") and not os.path.isfile(SECRETS_PATH):
        # 一次性迁移：原 api.json 中有 apiKey 则写入 secrets.json，并从 api.json 文件中移除
        _save_secrets(data["apiKey"])
        try:
            path = API_CONFIG_PATH
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    full = json.load(f)
                full.pop("apiKey", None)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(full, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    else:
        data.setdefault("apiKey", "")

    _cached_api_config = data
    return _cached_api_config


def get_ai_config() -> Dict[str, Any]:
    """返回当前生效的 AI 配置（三要素 + 参数）。"""
    cfg = load_api_config()
    return {
        "apiKey": cfg.get("apiKey", ""),
        "apiUrl": cfg.get("apiUrl", ""),
        "model": cfg.get("model", ""),
        "modelId": cfg.get("modelId", cfg.get("model", "")),
        "provider": cfg.get("provider", "openai"),
        "temperature": cfg.get("temperature", 0.8),
        "maxTokens": cfg.get("maxTokens", 2000),
    }


def get_models() -> List[Dict[str, Any]]:
    """返回模型列表（兼容旧接口）。v2 下为当前模型的单元素列表。"""
    cfg = load_api_config()
    if cfg.get("models"):
        return [m for m in cfg["models"] if m.get("enabled", True)]
    model = cfg.get("model", "")
    if model:
        return [{
            "id": cfg.get("modelId", model),
            "name": model,
            "model": model,
            "apiUrl": cfg.get("apiUrl", ""),
            "provider": cfg.get("provider", "openai"),
            "temperature": cfg.get("temperature", 0.8),
            "maxTokens": cfg.get("maxTokens", 2000),
            "enabled": True,
        }]
    return []


def get_model_by_id(model_id: str) -> Optional[Dict[str, Any]]:
    """按 id 找模型（v2 下 id 即模型名）。"""
    if not model_id:
        return None
    for m in get_models():
        if m.get("id") == model_id:
            return m
    return None


def get_default_model_id() -> str:
    """返回当前默认模型（v2 下即模型名）。"""
    return get_ai_config().get("model") or ""


def load_user_api_config() -> Dict[str, Any]:
    """兼容旧接口：返回用户当前配置（apiKey、modelId、model、apiUrl 等）。"""
    cfg = get_ai_config()
    return {
        "apiKey": cfg.get("apiKey", ""),
        "modelId": cfg.get("modelId", ""),
        "model": cfg.get("model", ""),
        "apiUrl": cfg.get("apiUrl", ""),
        "provider": cfg.get("provider", "openai"),
        "temperature": cfg.get("temperature", 0.8),
        "maxTokens": cfg.get("maxTokens", 2000),
    }


def save_ai_settings(
    api_url: str = "",
    api_key: str = "",
    model: str = "",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> None:
    """通用保存入口：apiUrl/model 写入 api.json，apiKey 写入 secrets.json。"""
    global _cached_api_config
    os.makedirs(CONFIG_DIR, exist_ok=True)

    cur = _load_json(API_CONFIG_PATH) or _load_json(API_CONFIG_EXAMPLE_PATH) or {}
    cur = _normalize(cur)
    new_api = _to_v2({
        "apiUrl": api_url.strip() or cur.get("apiUrl", ""),
        "model": model.strip() or cur.get("model", ""),
        "modelId": model.strip() or cur.get("modelId", cur.get("model", "")),
        "provider": "openai",
        "temperature": temperature if temperature is not None else cur.get("temperature", DEFAULT_TEMPERATURE),
        "maxTokens": int(max_tokens) if max_tokens is not None else cur.get("maxTokens", DEFAULT_MAX_TOKENS),
    })
    with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(new_api, f, ensure_ascii=False, indent=2)
    # apiKey 留空时保留现有值，避免误清空
    if api_key:
        _save_secrets(api_key.strip())
    _cached_api_config = None


def save_user_api_config(api_key: str = "", model_id: str = "") -> None:
    """兼容旧接口：等价于 save_ai_settings(api_key=..., model=...)。"""
    save_ai_settings(api_key=api_key, model=model_id)


def validate_ai_config() -> bool:
    """三要素（URL + Key + 模型名）齐备即可用。"""
    cfg = get_ai_config()
    return bool(cfg.get("apiKey") and cfg.get("apiUrl") and cfg.get("model"))
