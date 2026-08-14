"""
计划 Web 工作台宿主窗：用 QWebEngineView 内嵌 plans_web.html，
经 QWebChannel 与 PlansStore 实时桥接，读写同一份 data/plans.json。

- 在桌面内打开即与「快速记一笔」小窗、磁盘文件实时一致（轮询 2s 拉取差异）。
- 若未安装 PyQtWebEngine，则退化为用系统浏览器打开 plans_web.html
  （此时为纯本地 localStorage 模式，可导入/导出 JSON 与桌面数据互换）。
"""
from __future__ import annotations

import os
import shutil
import glob
from typing import TYPE_CHECKING, Optional

from ..core import plans_store as ps

try:
    from PyQt5.QtCore import Qt, QUrl, QObject, QTimer, pyqtSignal, pyqtSlot, QFile, QIODevice
    from PyQt5.QtWidgets import QDialog, QMessageBox, QDesktopWidget, QApplication
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtWebChannel import QWebChannel

    HAS_WEBENGINE = True
except Exception:  # pragma: no cover - 依赖缺失时优雅降级
    HAS_WEBENGINE = False

if TYPE_CHECKING:
    from .pet import DesktopPet

_HERE = os.path.dirname(os.path.abspath(__file__))
_HTML_PATH = os.path.join(_HERE, "plans", "plans_web.html")


def _find_qwebchannel_js() -> str:
    """在 PyQt5 包内查找 qwebchannel.js，找不到返回空串。"""
    try:
        import PyQt5
    except Exception:
        return ""
    base = os.path.dirname(PyQt5.__file__)
    hits = glob.glob(os.path.join(base, "**", "qwebchannel.js"), recursive=True)
    return hits[0] if hits else ""


def _ensure_webchannel_js() -> None:
    """确保 plans_web.html 旁有 qwebchannel.js（WebChannel 运行所需）。"""
    dest = os.path.join(_HERE, "plans", "qwebchannel.js")
    if os.path.exists(dest):
        return
    src = _find_qwebchannel_js()
    if src:
        try:
            shutil.copyfile(src, dest)
        except OSError:
            pass


class PlanBridge(QObject):
    """暴露给网页的桥接对象：网页读写整份计划，Python 落盘并广播变更。"""

    dataChanged = pyqtSignal(str)

    def __init__(self, store: "ps.PlansStore"):
        super().__init__()
        self.store = store

    @pyqtSlot(result=str)
    def getAll(self) -> str:
        return self.store.to_json()

    @pyqtSlot(str)
    def save(self, json_str: str) -> None:
        try:
            data = __import__("json").loads(json_str)
        except Exception:
            return
        if not isinstance(data, list):
            return
        self.store.replace_all(data)
        self.dataChanged.emit(self.store.to_json())

    @pyqtSlot(result=str)
    def getTodos(self) -> str:
        return self.store.to_json_todos()

    @pyqtSlot(str)
    def saveTodos(self, json_str: str) -> None:
        try:
            data = __import__("json").loads(json_str)
        except Exception:
            return
        if not isinstance(data, list):
            return
        self.store.replace_todos(data)
        self.dataChanged.emit(self.store.to_json_todos())

    @pyqtSlot(str, str)
    def recordEvent(self, kind: str, label: str) -> None:
        """B3：内嵌「计划台」里的完成动作 → 桌宠反馈（靠谱值 + 情绪/动画气泡）。"""
        try:
            from .pet_link import notify_completion
            notify_completion(kind, label)
        except Exception:
            pass


class PlansWebDialog(QDialog):
    """内嵌 Web 工作台的窗口。"""

    def __init__(self, parent: Optional[QWidget], pet: "Optional[DesktopPet]" = None):
        super().__init__(parent)
        self.pet = pet
        self.store = ps.PlansStore(__file__)
        self.setWindowTitle("计划台")
        self.resize(1000, 700)
        self._center()

        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.NoContextMenu)
        self.view.setGeometry(0, 0, self.width(), self.height())

        self.bridge = PlanBridge(self.store)
        self.channel = QWebChannel(self)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        _ensure_webchannel_js()
        self.view.load(QUrl.fromLocalFile(_HTML_PATH))

        # 跨界面实时同步：每 2s 拉取一次，仅数据变化才重渲染
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _center(self):
        screen = QApplication.desktop().availableGeometry()
        self.move(
            (screen.width() - self.width()) // 2 + screen.x(),
            (screen.height() - self.height()) // 2 + screen.y(),
        )

    def _poll(self):
        if self.isVisible():
            self.view.page().runJavaScript(
                "var b=document.getElementById('btnRefresh'); if(b) b.click();",
                lambda _: None,
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.view.setGeometry(0, 0, self.width(), self.height())


def open_plans_web(parent: Optional[QWidget], pet: "Optional[DesktopPet]" = None) -> None:
    """打开 Web 工作台：有 WebEngine 走内嵌桥接，否则系统浏览器兜底。"""
    if HAS_WEBENGINE:
        dlg = PlansWebDialog(parent, pet)
        dlg.exec_()
    else:
        QMessageBox.information(
            parent,
            "未安装 PyQtWebEngine",
            "将以系统浏览器打开 Web 工作台（本地存储模式）。\n"
            "如需在桌宠内实时桥接，请运行：pip install PyQtWebEngine",
        )
        open_plans_web_browser(pet)


def open_plans_web_browser(pet: "Optional[DesktopPet]" = None) -> None:
    """在系统浏览器中打开 Web 工作台（网页版，经本地服务读写同一份数据）。

    网页端通过 http://127.0.0.1 的本地服务读写 data/plans.json / data/todos.json，
    与桌宠内嵌「计划台」共用同一真相源，实现两端同步。
    """
    try:
        from .workbench_server import ensure_server
        from PyQt5.QtGui import QDesktopServices

        url = ensure_server()
        QDesktopServices.openUrl(QUrl(url))
    except Exception:
        try:
            from PyQt5.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(_HTML_PATH))
        except Exception:
            pass
