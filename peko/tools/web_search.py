"""
Web 搜索工具 — 使用 DuckDuckGo HTML 搜索。
无需 API Key，直接请求 DuckDuckGo 搜索页面解析结果。
"""
from __future__ import annotations
import re
import html
from typing import List, Dict
from .base import BaseTool, ToolResult

try:
    import requests
except ImportError:
    requests = None


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "搜索互联网，返回相关网页的标题、摘要和链接。适合查询实时信息、新闻、技术文档等。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "max_results": {
                "type": "integer",
                "description": "返回结果数量，默认 5",
                "default": 5
            }
        },
        "required": ["query"]
    }

    _DDG_URL = "https://html.duckduckgo.com/html/"
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }

    def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        if not requests:
            return ToolResult.fail("requests 库未安装，无法执行搜索")
        if not query or not query.strip():
            return ToolResult.fail("搜索关键词不能为空")
        try:
            results = self._search(query.strip(), max_results)
            if not results:
                return ToolResult.ok(f"搜索 \"{query}\" 未找到相关结果。")
            lines = [f"搜索 \"{query}\" 的结果：\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. **{r['title']}**")
                if r.get("snippet"):
                    lines.append(f"   {r['snippet']}")
                if r.get("url"):
                    lines.append(f"   链接: {r['url']}")
                lines.append("")
            return ToolResult.ok("\n".join(lines), data=results)
        except Exception as e:
            return ToolResult.fail(f"搜索出错: {e}")

    def _search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        resp = requests.post(
            self._DDG_URL,
            data={"q": query, "b": ""},
            headers=self._HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        return self._parse(resp.text, max_results)

    @staticmethod
    def _parse(html_text: str, max_results: int) -> List[Dict[str, str]]:
        results = []
        blocks = re.split(r'class="result\s+result--', html_text)
        for block in blocks[1:]:
            if len(results) >= max_results:
                break
            title_m = re.search(r'class="result__a"[^>]*>(.*?)</a>', block, re.DOTALL)
            snippet_m = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)', block, re.DOTALL)
            url_m = re.search(r'class="result__url"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_m:
                continue
            title = html.unescape(re.sub(r'<[^>]+>', '', title_m.group(1)).strip())
            snippet = ""
            if snippet_m:
                snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip())
            url = ""
            if url_m:
                url = html.unescape(re.sub(r'<[^>]+>', '', url_m.group(1)).strip())
            if title:
                results.append({"title": title, "snippet": snippet, "url": url})
        return results
