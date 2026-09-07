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
        # 注：「今天天气怎么样」已改为走天气直答（见 WeatherIntentTests），此处只保留纯闲聊
        self.assertIsNone(nl_intent.parse("你是谁"))
        self.assertIsNone(nl_intent.parse("今天好累啊"))
        self.assertIsNone(nl_intent.parse("讲个笑话"))
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


class WeatherIntentTests(unittest.TestCase):
    """天气查询走非 AI 直答；且不劫持待办与闲聊。"""

    def test_weather_phrases(self):
        for text in ("今天天气怎么样", "外面多少度", "明天会下雨吗", "今天要带伞吗", "气温怎么样"):
            intent = nl_intent.parse(text)
            self.assertIsNotNone(intent, text)
            self.assertEqual(intent["action"], "ask_weather", text)

    def test_todo_with_umbrella_not_hijacked(self):
        # 「提醒我带伞」是待办，不能被天气抢走（天气规则排在最后匹配）
        self.assertEqual(nl_intent.parse("提醒我明天带伞")["action"], "add_todo")

    def test_casual_chat_not_hijacked(self):
        self.assertIsNone(nl_intent.parse("今天好累啊"))
        self.assertIsNone(nl_intent.parse("跟我说说话"))


class SetCityIntentTests(unittest.TestCase):
    """纠正城市（解决 IP 定位不准）。口语「我在XX」需命中城市表，明确动词直接信任用户。"""

    def test_casual_known_city(self):
        intent = nl_intent.parse("我在宁波")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "set_city")
        self.assertEqual(intent["city"], "宁波")

    def test_casual_with_province_suffix(self):
        intent = nl_intent.parse("我住在杭州市")
        self.assertEqual(intent["action"], "set_city")
        self.assertEqual(intent["city"], "杭州")

    def test_explicit_verb_trusted(self):
        intent = nl_intent.parse("城市改成 深圳")
        self.assertEqual(intent["action"], "set_city")
        self.assertEqual(intent["city"], "深圳")
        intent2 = nl_intent.parse("定位到 成都")
        self.assertEqual(intent2["action"], "set_city")
        self.assertEqual(intent2["city"], "成都")

    def test_casual_unknown_not_set(self):
        # 「我在上班」不是城市 → 不应误设，交给 AI 闲聊
        self.assertIsNone(nl_intent.parse("我在上班"))
        # 口语动词命中但非城市（「我在吃饭」）→ 不误设
        self.assertIsNone(nl_intent.parse("我在吃饭"))

    def test_explicit_unknown_refused(self):
        # 明确动词但城市表没有 → 仍不强行设置（避免「城市改成 上班」写进配置）
        self.assertIsNone(nl_intent.parse("城市改成 火星"))

    def test_weather_phrase_not_hijacked_into_set_city(self):
        # 「宁波下雨吗」含天气词，应走 ask_weather 而非 set_city
        intent = nl_intent.parse("宁波下雨吗")
        self.assertEqual(intent["action"], "ask_weather")


class AskWeatherCityIntentTests(unittest.TestCase):
    """显式城市天气查询（「帮我查看xx的天气」）：一次性查该城市，不改默认城市。"""

    def test_verb_led_with_city(self):
        intent = nl_intent.parse("帮我查看宁波的天气")
        self.assertEqual(intent["action"], "ask_weather_city")
        self.assertEqual(intent["city"], "宁波")

    def test_variants(self):
        cases = {
            "查一下杭州天气": "杭州",
            "查看北京天气": "北京",
            "查深圳的天气": "深圳",
            "看看成都天气": "成都",
        }
        for text, city in cases.items():
            with self.subTest(text):
                intent = nl_intent.parse(text)
                self.assertEqual(intent["action"], "ask_weather_city", text)
                self.assertEqual(intent["city"], city, text)

    def test_city_first_phrase(self):
        # 「宁波天气怎么样」也应识别为查询宁波（不带查/看动词的自然说法）
        intent = nl_intent.parse("宁波天气怎么样")
        self.assertEqual(intent["action"], "ask_weather_city")
        self.assertEqual(intent["city"], "宁波")

    def test_non_city_falls_back_to_default(self):
        # 「帮我查看今天天气」抽到的是时间词，退化为默认城市查询（ask_weather）
        intent = nl_intent.parse("帮我查看今天天气")
        self.assertEqual(intent["action"], "ask_weather")

    def test_does_not_hijack_set_city(self):
        # 口语/明确动词改城市仍走 set_city，不被天气城市查询抢走
        self.assertEqual(nl_intent.parse("我在宁波")["action"], "set_city")
        self.assertEqual(nl_intent.parse("城市改成 深圳")["action"], "set_city")

    def test_explicit_unknown_city_refused(self):
        # 抽不到城市（如「帮我查看天气」缺城市名）→ 退化为默认 ask_weather
        intent = nl_intent.parse("帮我查看天气")
        self.assertEqual(intent["action"], "ask_weather")


if __name__ == "__main__":
    unittest.main()
