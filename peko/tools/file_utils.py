"""
本地文件读取工具函数：路径校验、安全过滤。
仅允许读取项目目录或用户主目录下的文本文件。
"""
from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

from ..core.runtime_paths import get_bundle_root, get_writable_root

# 单文件最大读取字节数
MAX_FILE_BYTES = 512 * 1024
# 送入 LLM 摘要的最大字符数
MAX_SUMMARY_CHARS = 12_000

_BLOCKED_NAMES = frozenset({
    "secrets.json",
    ".env",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
})

_ALLOWED_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".json", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".htm", ".css", ".xml", ".yaml", ".yml", ".csv", ".log", ".ini",
    ".cfg", ".conf", ".toml", ".rst", ".sql", ".sh", ".bat", ".ps1",
})


def _allowed_roots() -> Tuple[str, ...]:
    module_file = os.path.join(os.path.dirname(__file__), "..", "core", "runtime_paths.py")
    return (
        os.path.normpath(get_bundle_root(module_file=module_file)),
        os.path.normpath(get_writable_root(module_file=module_file)),
        os.path.normpath(os.path.expanduser("~")),
    )


def resolve_allowed_path(path: str) -> str:
    """解析并校验路径，返回绝对路径。"""
    if not path or not str(path).strip():
        raise ValueError("文件路径不能为空")

    resolved = os.path.normpath(os.path.abspath(os.path.expanduser(str(path).strip())))
    if not os.path.isfile(resolved):
        raise ValueError(f"文件不存在: {resolved}")

    basename = os.path.basename(resolved).lower()
    if basename in _BLOCKED_NAMES or basename.startswith(".env"):
        raise ValueError("不允许读取敏感配置文件")

    allowed = False
    for root in _allowed_roots():
        try:
            if os.path.commonpath([resolved, root]) == root:
                allowed = True
                break
        except ValueError:
            continue
    if not allowed:
        raise ValueError("仅允许读取项目目录或用户主目录下的文件")

    ext = os.path.splitext(resolved)[1].lower()
    if ext and ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"不支持的文件类型: {ext}，"
            f"支持: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
        )
    return resolved


def read_text_file(path: str, *, max_chars: Optional[int] = None) -> Tuple[str, Dict[str, object]]:
    """读取文本文件，返回 (内容, 元信息)。"""
    resolved = resolve_allowed_path(path)
    size_bytes = os.path.getsize(resolved)
    if size_bytes > MAX_FILE_BYTES:
        raise ValueError(
            f"文件过大（{size_bytes // 1024} KB），上限 {MAX_FILE_BYTES // 1024} KB"
        )

    with open(resolved, "rb") as f:
        raw = f.read(MAX_FILE_BYTES + 1)

    if b"\x00" in raw[:8192]:
        raise ValueError("疑似二进制文件，仅支持文本文件")

    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        raise ValueError("无法识别文件编码")

    limit = max_chars if max_chars is not None else MAX_SUMMARY_CHARS
    truncated = len(text) > limit
    if truncated:
        text = text[:limit]

    meta = {
        "path": resolved,
        "name": os.path.basename(resolved),
        "size_bytes": size_bytes,
        "chars": len(text),
        "truncated": truncated,
    }
    return text, meta


def format_file_meta(meta: Dict[str, object]) -> str:
    """格式化文件元信息供工具输出。"""
    lines = [
        f"文件：{meta['name']}",
        f"路径：{meta['path']}",
        f"大小：{meta['size_bytes']} 字节",
    ]
    if meta.get("truncated"):
        lines.append(f"（内容已截断，仅展示前 {meta['chars']} 字符）")
    return "\n".join(lines)
