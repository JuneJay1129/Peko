"""
本地工作台 HTTP 服务。

让系统浏览器打开的「工作台」与桌宠内嵌「计划台」读写同一份
data/plans.json / data/todos.json，实现两端数据同步。

- 仅监听 127.0.0.1，随桌宠进程启动/退出，外部不可访问。
- 提供静态页（plans_web.html）与 JSON API（/api/plans、/api/todos）。
- 所有读写走 PlansStore（原子写），与内嵌桥接共用同一真相源。
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Optional
from urllib.parse import urlparse

from ..core import plans_store as ps

_PORT = 18340
_html_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plans")
_store = ps.PlansStore(__file__)

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


class _Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")

    def _send_json(self, payload, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, fs_path: str) -> None:
        try:
            with open(fs_path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        ext = os.path.splitext(fs_path)[1].lower()
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPES.get(ext, "application/octet-stream"))
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Optional[List[dict]]:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"[]"
        try:
            data = json.loads(raw or b"[]")
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, list) else None

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html", "/plans_web.html"):
            self._send_file(os.path.join(_html_dir, "plans_web.html"))
        elif path == "/qwebchannel.js":
            self._send_file(os.path.join(_html_dir, "qwebchannel.js"))
        elif path == "/api/plans":
            self._send_json(_store.all())
        elif path == "/api/todos":
            self._send_json(_store.todos())
        elif path == "/api/habits":
            self._send_json(_store.habits())
        elif path == "/api/ledger":
            self._send_json(_store.ledger())
        elif path == "/api/review":
            self._send_json(_store.review())
        elif path == "/api/focus":
            self._send_json(_store.focus_log())
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path in ("/api/plans", "/api/todos", "/api/habits", "/api/ledger", "/api/review", "/api/focus"):
            data = self._read_body()
            if data is None:
                self._send_json({"error": "expect array"}, 400)
                return
            if path == "/api/plans":
                _store.replace_all(data)
            elif path == "/api/todos":
                _store.replace_todos(data)
            elif path == "/api/habits":
                _store.replace_habits(data)
            elif path == "/api/ledger":
                _store.replace_ledger(data)
            elif path == "/api/review":
                _store.replace_review(data)
            else:
                _store.replace_focus(data)
            self._send_json({"ok": True})
        else:
            self.send_error(404)

    def log_message(self, *args) -> None:  # 静默
        pass


_server: Optional[ThreadingHTTPServer] = None
_url: Optional[str] = None


def ensure_server() -> str:
    """启动（若未启动）本地工作台服务，返回访问 URL。"""
    global _server, _url
    if _server is not None:
        return _url  # type: ignore
    httpd = ThreadingHTTPServer(("127.0.0.1", _PORT), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    _server = httpd
    _url = f"http://127.0.0.1:{_PORT}/"
    return _url


def stop_server() -> None:
    global _server
    if _server is not None:
        _server.shutdown()
        _server = None
