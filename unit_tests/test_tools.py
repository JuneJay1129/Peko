import json
import os
import tempfile
import unittest
from unittest import mock

from peko.tools import get_all_tools, get_openai_tools, call_tool
from peko.tools.file_utils import resolve_allowed_path, read_text_file
from peko.tools.weather import WeatherTool


class ToolRegistryTests(unittest.TestCase):
    def test_builtin_tools_registered(self):
        names = {t.name for t in get_all_tools()}
        self.assertIn("web_search", names)
        self.assertIn("get_weather", names)
        self.assertIn("read_file", names)
        self.assertIn("summarize_file", names)

    def test_openai_schemas_have_required_fields(self):
        for schema in get_openai_tools():
            fn = schema["function"]
            self.assertTrue(fn["name"])
            self.assertTrue(fn["description"])
            self.assertEqual(schema["type"], "function")


class FileUtilsTests(unittest.TestCase):
    def test_read_project_file(self):
        readme = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
        if not os.path.isfile(readme):
            self.skipTest("README.md not found")
        content, meta = read_text_file(readme, max_chars=200)
        self.assertIn("Peko", content)
        self.assertEqual(meta["name"], "README.md")

    def test_block_secrets_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = os.path.join(tmp, "secrets.json")
            with open(secret, "w", encoding="utf-8") as f:
                f.write("{}")
            with self.assertRaises(ValueError):
                resolve_allowed_path(secret)

    def test_read_file_tool(self):
        readme = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
        if not os.path.isfile(readme):
            self.skipTest("README.md not found")
        result = call_tool("read_file", {"file_path": readme, "max_chars": 300})
        self.assertTrue(result.success)
        self.assertIn("README.md", result.output)


class WeatherToolTests(unittest.TestCase):
    def test_format_weather(self):
        sample = {
            "current_condition": [{
                "temp_C": "20",
                "FeelsLikeC": "19",
                "humidity": "55",
                "windspeedKmph": "12",
                "weatherDesc": [{"value": "晴"}],
            }],
            "weather": [{
                "date": "2026-06-08",
                "maxtempC": "25",
                "mintempC": "18",
                "hourly": [{"weatherDesc": [{"value": "多云"}]}],
            }],
        }
        text = WeatherTool._format("北京", sample, 1)
        self.assertIn("北京", text)
        self.assertIn("20", text)
        self.assertIn("晴", text)

    @mock.patch("peko.tools.weather.requests.get")
    def test_weather_tool_execute(self, mock_get):
        mock_resp = mock.Mock()
        mock_resp.raise_for_status = mock.Mock()
        mock_resp.json.return_value = {
            "current_condition": [{
                "temp_C": "8",
                "FeelsLikeC": "6",
                "humidity": "70",
                "windspeedKmph": "10",
                "weatherDesc": [{"value": "阴"}],
            }],
            "weather": [],
        }
        mock_get.return_value = mock_resp

        tool = WeatherTool()
        result = tool.execute(city="上海")
        self.assertTrue(result.success)
        self.assertIn("上海", result.output)


class SummarizeFileToolTests(unittest.TestCase):
    @mock.patch("peko.ai.service.chat_with_tools")
    @mock.patch("peko.ai.config_loader.validate_ai_config", return_value=True)
    def test_summarize_file(self, _mock_validate, mock_chat):
        from peko.ai.service import AgentResponse

        mock_chat.return_value = AgentResponse(content="这是文件摘要。")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "note.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("第一段\n第二段")

            result = call_tool("summarize_file", {"file_path": path})
            self.assertTrue(result.success)
            self.assertIn("摘要", result.output)
            self.assertIn("这是文件摘要", result.output)


if __name__ == "__main__":
    unittest.main()
