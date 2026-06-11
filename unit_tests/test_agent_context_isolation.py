import unittest

from peko.ai.agent import AgentLoop


class AgentContextIsolationTests(unittest.TestCase):
    def test_load_history_replaces_previous_conversation_context(self):
        agent = AgentLoop(system_prompt="system")
        agent._messages.extend([
            {"role": "user", "content": "A user"},
            {"role": "assistant", "content": "A assistant"},
        ])

        agent.load_history([
            {"role": "user", "content": "B user"},
            {"role": "assistant", "content": "B assistant"},
        ])

        self.assertEqual(agent.messages, [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "B user"},
            {"role": "assistant", "content": "B assistant"},
        ])

    def test_load_history_ignores_ui_only_message_roles(self):
        agent = AgentLoop(system_prompt="system")

        agent.load_history([
            {"role": "timer_alert", "content": "stand up"},
            {"role": "streaming", "content": "partial"},
            {"role": "tool_status", "content": "using tool"},
            {"role": "user", "content": "real user"},
        ])

        self.assertEqual(agent.messages, [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "real user"},
        ])


if __name__ == "__main__":
    unittest.main()
