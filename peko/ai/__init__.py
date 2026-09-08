"""AI 服务与配置（v2：通用 OpenAI 兼容三要素 URL + Key + Model）"""
from .config_loader import (
    load_api_config,
    get_ai_config,
    validate_ai_config,
    get_models,
    get_model_by_id,
    get_default_model_id,
    load_user_api_config,
    save_user_api_config,
    save_ai_settings,
)
from .service import stream_chat, test_connection, get_current_model_name

__all__ = [
    "load_api_config",
    "get_ai_config",
    "validate_ai_config",
    "get_models",
    "get_model_by_id",
    "get_default_model_id",
    "load_user_api_config",
    "save_user_api_config",
    "save_ai_settings",
    "stream_chat",
    "test_connection",
    "get_current_model_name",
]
