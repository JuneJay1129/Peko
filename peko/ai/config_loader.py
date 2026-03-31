"""
Peko API 配置加载器
- 从 config/api.json 读取模型配置；API Key 从 config/secrets.json 读取
- 用户复制 api.json.example → api.json、secrets.json.example → secrets.json，在 secrets.json 中填写 apiKey 即可
- 打包为 exe 时：config 目录在 exe 同目录下（可写），模板文件从包内读取
"""
import json
import os
import sys
import shutil
from typing import Optional, List, Dict, Any
from ..core.runtime_paths import get_bundle_root, get_writable_root

# 项目根目录（peko/ai/ -> 项目根）；打包后配置写到 exe 所在目录，macOS .app 写到 .app 外部同级目录。
_ROOT = get_writable_root(module_file=__file__)
_BUNDLE = get_bundle_root(module_file=__file__)
CONFIG_DIR = os.path.join(_ROOT, "config")
API_CONFIG_PATH = os.path.join(CONFIG_DIR, "api.json")
API_CONFIG_EXAMPLE_PATH = os.path.join(_BUNDLE, "config", "api.json.example")
SECRETS_PATH = os.path.join(CONFIG_DIR, "secrets.json")
SECRETS_EXAMPLE_PATH = os.path.join(_BUNDLE, "config", "secrets.json.example")
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
        _save_secrets(data.get("apiKey", ""))
        full = _load_json(API_CONFIG_PATH) or {}
        full["modelId"] = data.get("modelId", full.get("defaultModel", "qwen-72b"))
        with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return data


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
    """加载 config/api.json（模型列表等），并合并 config/secrets.json 中的 apiKey。"""
    global _cached_api_config
    if _cached_api_config is not None:
        return _cached_api_config
    path = API_CONFIG_PATH if os.path.isfile(API_CONFIG_PATH) else API_CONFIG_EXAMPLE_PATH
    # 打包 exe 首次运行：将 config 模板复制到 exe 同目录，便于用户编辑
    if not os.path.isfile(API_CONFIG_PATH) and getattr(sys, "frozen", False) and os.path.isfile(API_CONFIG_EXAMPLE_PATH):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            shutil.copy(API_CONFIG_EXAMPLE_PATH, API_CONFIG_PATH)
            path = API_CONFIG_PATH
        except Exception:
            pass
    data = _load_json(path)
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
        secrets = _load_secrets()
        if secrets.get("apiKey") and secrets.get("apiKey") != "your-api-key-here":
            _cached_api_config["apiKey"] = secrets["apiKey"]
    else:
        data = _merge_legacy_user_api(data)
        if "apiKey" not in data:
            data["apiKey"] = ""
        secrets = _load_secrets()
        if secrets.get("apiKey") and secrets.get("apiKey") != "your-api-key-here":
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
    """将 apiKey 写入 config/secrets.json，将 modelId 写入 config/api.json。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if api_key is not None:
        _save_secrets(api_key)
    if model_id:
        path = API_CONFIG_PATH
        if not os.path.isfile(path) and os.path.isfile(API_CONFIG_EXAMPLE_PATH):
            shutil.copy(API_CONFIG_EXAMPLE_PATH, path)
        data = _load_json(path) or {}
        data["modelId"] = model_id
        with open(path, "w", encoding="utf-8") as f:
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
