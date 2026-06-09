"""验证 sentinel 方案的流式块查找/更新/删除逻辑。"""
import sys
import unittest

from PyQt5.QtWidgets import QApplication, QTextBrowser
from PyQt5.QtGui import QTextCursor

app = QApplication.instance() or QApplication(sys.argv)

SENTINEL_THINKING = "\uE001"
SENTINEL_STREAM   = "\uE002"


class SentinelBlockTests(unittest.TestCase):

    def setUp(self):
        self.tb = QTextBrowser()

    def _append_thinking(self):
        self.tb.append(
            f"<p align=\"center\" style=\"font-size:12px;\">"
            f"{SENTINEL_THINKING}thinking...</p>"
        )

    def _remove_thinking(self):
        cursor = self.tb.document().find(SENTINEL_THINKING)
        self.assertTrue(not cursor.isNull(), "sentinel not found")
        bc = QTextCursor(cursor.block())
        bc.movePosition(QTextCursor.StartOfBlock)
        bc.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        bc.removeSelectedText()
        if not bc.block().text().strip():
            bc.deleteChar()

    def _append_streaming(self):
        self.tb.append(
            f"<p style=\"margin:8px 8px 8px 64px; padding:12px;\">"
            f"{SENTINEL_STREAM}...</p>"
        )
        doc = self.tb.document()
        self._stream_block_num = doc.lastBlock().blockNumber()

    def _update_streaming(self, text):
        doc = self.tb.document()
        block = doc.findBlockByNumber(self._stream_block_num)
        self.assertTrue(block.isValid(), "streaming block not found by number")
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(SENTINEL_STREAM + text.replace("\n", "\u2028"))

    def _remove_streaming(self):
        doc = self.tb.document()
        block = doc.findBlockByNumber(self._stream_block_num)
        if not block.isValid():
            cursor = doc.find(SENTINEL_STREAM)
            if not cursor.isNull():
                block = cursor.block()
        self.assertIsNotNone(block)
        bc = QTextCursor(block)
        bc.movePosition(QTextCursor.StartOfBlock)
        bc.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        bc.removeSelectedText()
        if not bc.block().text().strip():
            bc.deleteChar()

    # ── tests ──

    def test_thinking_sentinel_found_and_removed(self):
        # 先加一条用户消息，避免空文档的边界行为
        self.tb.append("<p>用户消息</p>")
        blocks_before = self.tb.document().blockCount()

        self._append_thinking()
        self.assertGreater(self.tb.document().blockCount(), blocks_before,
                           "appending thinking should increase block count")

        cursor = self.tb.document().find(SENTINEL_THINKING)
        self.assertFalse(cursor.isNull(), "thinking sentinel not found in document")

        self._remove_thinking()
        # sentinel 应已不存在
        cursor_after = self.tb.document().find(SENTINEL_THINKING)
        self.assertTrue(cursor_after.isNull(), "thinking sentinel should be removed")

    def test_streaming_block_update(self):
        self._append_streaming()
        self._update_streaming("Hello")
        doc = self.tb.document()
        block = doc.findBlockByNumber(self._stream_block_num)
        self.assertIn("Hello", block.text())
        self.assertIn(SENTINEL_STREAM, block.text())

    def test_streaming_block_multiline(self):
        self._append_streaming()
        self._update_streaming("Line1\nLine2")
        doc = self.tb.document()
        block = doc.findBlockByNumber(self._stream_block_num)
        # \u2028 is line separator, stays in same block
        self.assertIn("Line1", block.text())
        self.assertIn("Line2", block.text())
        # block number must NOT change (still same block)
        self.assertEqual(block.blockNumber(), self._stream_block_num)

    def test_streaming_block_removed(self):
        self._append_streaming()
        blocks_before = self.tb.document().blockCount()
        self._remove_streaming()
        self.assertLess(self.tb.document().blockCount(), blocks_before + 1)

    def test_full_flow_with_tool_call(self):
        """模拟：追加 thinking → 追加 tool status → 出现第一个 token → done"""
        initial = self.tb.document().blockCount()

        # 追加 thinking
        self._append_thinking()
        # 追加工具状态（不带 sentinel）
        self.tb.append("<p align=\"center\" style=\"font-size:12px;\">🔧 正在使用 set_timer...</p>")
        after_statuses = self.tb.document().blockCount()
        self.assertGreater(after_statuses, initial)

        # 第一个 token：删除 thinking，追加 streaming 块
        self._remove_thinking()
        self._append_streaming()

        # 多个 token
        for word in ["设置", "成功", "！"]:
            prev_text = self.tb.document().findBlockByNumber(
                self._stream_block_num
            ).text()
            current = prev_text.replace(SENTINEL_STREAM, "") + word
            self._update_streaming(current)

        final_text = self.tb.document().findBlockByNumber(
            self._stream_block_num
        ).text()
        self.assertIn("设置", final_text)
        self.assertIn("成功", final_text)

        # 完成：删除 streaming 块
        self._remove_streaming()
        self.assertFalse(
            self.tb.document().find(SENTINEL_STREAM).isNull() is False
            and self.tb.document().find(SENTINEL_STREAM).block().isValid(),
            "streaming sentinel should be gone"
        )


if __name__ == "__main__":
    unittest.main()
