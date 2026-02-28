"""
Peko API 配置加载器
- 从 config/api.json 读取全部配置：apiKey、modelId（当前使用的模型）、模型列表
- 用户只需在 api.json 中填写 apiKey、设置 modelId 即可使用
"""
import json
import os
from typing import Optional, List, Dict, Any

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
API_CONFIG_PATH = os.path.join(CONFIG_DIR, "api.json")
_USER_API_LEGACY_PATH = os.path.join(CONFIG_DIR, "user_api.json")

_cached_api_config: Optional[Dict[str, Any]] = None


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
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            full = json.load(f)
        full["apiKey"] = data.get("apiKey", "")
        full["modelId"] = data.get("modelId", full.get("defaultModel", "qwen-72b"))
        with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return data


def load_api_config() -> Dict[str, Any]:
    """加载 config/api.json（含 apiKey、modelId、模型列表）。"""
    global _cached_api_config
    if _cached_api_config is not None:
        return _cached_api_config
    data = _load_json(API_CONFIG_PATH)
    if data is None:
        _cached_api_config = {
            "version": "1.0.0",
            "apiKey": "",
            "modelId": "qwen-72b",
            "defaultModel": "qwen-72b",
            "models": [
                {
                    "id": "qwen-72b",
                    "name": "Qwen 2.5 72B",
                    "provider": "siliconflow",
                    "model": "Qwen/Qwen2.5-72B-Instruct",
                    "apiUrl": "https://api.siliconflow.cn/v1/chat/completions",
                    "temperature": 0.8,
                    "maxTokens": 2000,
                    "enabled": True,
                }
            ],
        }
    else:
        data = _merge_legacy_user_api(data)
        if "apiKey" not in data:
            data["apiKey"] = ""
        if "modelId" not in data:
            data["modelId"] = data.get("defaultModel", "qwen-72b")
        _cached_api_config = data
    return _cached_api_config


def get_models() -> List[Dict[str, Any]]:
    """获取已启用的模型列表。"""
    cfg = load_api_config()
    models = cfg.get("models") or []
    return [m for m in models if m.get("enabled", True)]


def get_default_model_id() -> str:
    """获取默认模型 ID。"""
    cfg = load_api_config()
    return cfg.get("defaultModel") or "qwen-72b"


def get_model_by_id(model_id: str) -> Optional[Dict[str, Any]]:
    """根据 ID 获取模型配置。"""
    for m in get_models():
        if m.get("id") == model_id:
            return m
    return None


def load_user_api_config() -> Dict[str, Any]:
    """从 api.json 中读取用户配置（apiKey、modelId），兼容旧调用。"""
    cfg = load_api_config()
    return {"apiKey": cfg.get("apiKey", ""), "modelId": cfg.get("modelId") or cfg.get("defaultModel")}


def save_user_api_config(api_key: str = "", model_id: str = "") -> None:
    """将 apiKey / modelId 写回 config/api.json。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = _load_json(API_CONFIG_PATH) or {}
    if api_key is not None:
        data["apiKey"] = api_key
    if model_id:
        data["modelId"] = model_id
    with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    global _cached_api_config
    _cached_api_config = None


def get_ai_config() -> Dict[str, Any]:
    """从 api.json 读取 apiKey、modelId 等，供 AI 调用使用。"""
    cfg = load_api_config()
    model_id = cfg.get("modelId") or os.environ.get("PEKO_AI_MODEL_ID") or get_default_model_id()
    api_key = cfg.get("apiKey") or os.environ.get("PEKO_AI_KEY") or os.environ.get("VITE_AI_KEY") or ""

    model_cfg = get_model_by_id(model_id)
    if model_cfg is None:
        model_cfg = get_model_by_id(get_default_model_id()) or (get_models() or [{}])[0]

    return {
        "apiKey": api_key,
        "modelId": model_id,
        "model": model_cfg.get("model", "gpt-3.5-turbo"),
        "apiUrl": model_cfg.get("apiUrl", "https://api.openai.com/v1/chat/completions"),
        "provider": model_cfg.get("provider", "openai"),
        "temperature": model_cfg.get("temperature", 0.8),
        "maxTokens": model_cfg.get("maxTokens", 2000),
    }


def validate_ai_config() -> bool:
    """验证当前 AI 配置是否可用。"""
    cfg = get_ai_config()
    if cfg.get("provider") == "spark":
        return bool(
            cfg.get("apiKey")
            or (os.environ.get("SPARKAI_APP_ID") and os.environ.get("SPARKAI_API_KEY"))
        )
    return bool(cfg.get("apiKey") and cfg.get("apiUrl"))
