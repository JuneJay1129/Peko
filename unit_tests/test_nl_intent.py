import os
import tempfile
import unittest

from peko.core import nl_intent
from peko.core.plans_store import PlansStore


def _temp_store(tmp: str) -> PlansStore:
    # module_file 位于 <tmp>/a/b/c.py → get_writable_root 解析到 <tmp>，数据写入 <tmp>/data
    return PlansStore(os.path.join(tmp, "a", "b", "c.py"))


class ParseTests(unittest.TestCase):
    def test_ledger_with_explicit_verb(self):
        intent = nl_intent.parse("记一笔午饭 38")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "add_ledger")
        self.assertEqual(intent["title"], "午饭")
        self.assertEqual(intent["amount"], 38.0)
        self.assertEqual(intent["kind"], "expense")
        self.assertEqual(intent["cat"], "diet")

    def test_ledger_with_flow_word(self):
        intent = nl_intent.parse("午饭花了38")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "add_ledger")
        self.assertEqual(intent["kind"], "expense")

    def test_ledger_income(self):
        intent = nl_intent.parse("收入 5000 工资")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "add_ledger")
        self.assertEqual(intent["kind"], "income")
        self.assertEqual(intent["cat"], "work")

    def test_ledger_question_not_hijacked(self):
        # 疑问语气 + 金额：不应被当作记账
        self.assertIsNone(nl_intent.parse("你觉得我午饭花了38块贵吗"))

    def test_todo_with_time(self):
        intent = nl_intent.parse("提醒我 17:00 交周报")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "add_todo")
        self.assertEqual(intent["title"], "交周报")
        self.assertIn("17:00", intent["note"])

    def test_todo_simple(self):
        intent = nl_intent.parse("加一个待办 买牛奶")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "add_todo")
        self.assertEqual(intent["title"], "买牛奶")

    def test_focus_minutes(self):
        intent = nl_intent.parse("开始专注 25 分钟")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "start_focus")
        self.assertEqual(intent["minutes"], 25)

    def test_focus_pomodoro(self):
        intent = nl_intent.parse("来个番茄钟")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "start_focus")
        self.assertEqual(intent["minutes"], 25)

    def test_plain_chat_not_hijacked(self):
        self.assertIsNone(nl_intent.parse("今天天气怎么样"))
        self.assertIsNone(nl_intent.parse("你是谁"))
        self.assertIsNone(nl_intent.parse(""))
        self.assertIsNone(nl_intent.parse("   "))

    def test_quick_command_templates_parse(self):
        # input_dialog 快捷按钮的模板必须全部命中非 AI 路径
        expense = nl_intent.parse("记一笔 支出 午饭 38")
        self.assertEqual(expense["action"], "add_ledger")
        self.assertEqual(expense["kind"], "expense")
        self.assertEqual(expense["title"], "午饭")  # 「支出」不写进标题
        income = nl_intent.parse("记一笔 收入 兼职 500")
        self.assertEqual(income["action"], "add_ledger")
        self.assertEqual(income["kind"], "income")
        self.assertEqual(income["title"], "兼职")  # 「收入」不写进标题
        self.assertEqual(nl_intent.parse("提醒我 17:00 交周报")["action"], "add_todo")
        self.assertEqual(nl_intent.parse("开始专注 25 分钟")["action"], "start_focus")


class SuggestUsageTests(unittest.TestCase):
    def test_incomplete_command_gives_hint(self):
        self.assertIsNotNone(nl_intent.suggest_usage("记一笔"))      # 缺金额
        self.assertIsNotNone(nl_intent.suggest_usage("提醒我"))      # 缺内容
        self.assertIsNotNone(nl_intent.suggest_usage("记账"))        # 只有动词

    def test_complete_command_no_hint(self):
        self.assertIsNone(nl_intent.suggest_usage("记一笔 支出 午饭 38"))
        self.assertIsNone(nl_intent.suggest_usage("开始专注 25 分钟"))

    def test_plain_chat_no_hint(self):
        self.assertIsNone(nl_intent.suggest_usage("今天天气怎么样"))
        self.assertIsNone(nl_intent.suggest_usage(""))
        self.assertIsNone(nl_intent.suggest_usage("   "))


class ApplyTests(unittest.TestCase):
    def test_apply_add_ledger_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _temp_store(tmp)
            intent = nl_intent.parse("记一笔咖啡 32")
            msg = nl_intent.apply(intent, store=store)
            self.assertIn("已记一笔", msg)
            ledger = store.ledger()
            self.assertEqual(len(ledger), 1)
            self.assertEqual(ledger[0]["title"], "咖啡")
            self.assertEqual(ledger[0]["amount"], 32.0)
            self.assertEqual(ledger[0]["kind"], "expense")

    def test_apply_add_todo_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _temp_store(tmp)
            intent = nl_intent.parse("提醒我 写月度复盘")
            msg = nl_intent.apply(intent, store=store)
            self.assertIn("已加待办", msg)
            todos = store.todos()
            self.assertEqual(len(todos), 1)
            self.assertEqual(todos[0]["title"], "写月度复盘")

    def test_apply_focus_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _temp_store(tmp)
            intent = nl_intent.parse("开始专注 25 分钟")
            msg = nl_intent.apply(intent, store=store)
            self.assertIn("专注", msg)
            self.assertEqual(store.focus_log(), [])  # 不落盘，避免虚增统计


if __name__ == "__main__":
    unittest.main()
