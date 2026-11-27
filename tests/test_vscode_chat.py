"""Tests for agl.app.vscode_chat: the yes-gated VS Code Chat merge, run only inside temp folders."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agl.app import vscode_chat  # noqa: E402
from agl.platform import vscode_files  # noqa: E402

MODEL = "m:1"
LOCAL = "http://127.0.0.1:11434"
REMOTE = "http://192.168.1.50:11434"
OTHER_GROUP = [{"name": "Other Provider", "vendor": "other", "models": []}]


def _values(node, key):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            yield from _values(v, key)
    elif isinstance(node, list):
        for item in node:
            yield from _values(item, key)


class VsCodeChatTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.user = root / "User"
        self.user.mkdir()
        self.ws = root / "ws"
        self.ws.mkdir()
        self.lines = []
        self.prompts = []

    def _input(self, answers):
        pending = list(answers)

        def fake(prompt):
            self.prompts.append(prompt)
            return pending.pop(0) if pending else ""

        return fake

    def _offer(self, result, answers, base_url=LOCAL, tools=True):
        vscode_chat.offer(
            result,
            MODEL,
            base_url,
            str(self.ws),
            user_dirs=[("Test", self.user)],
            tools_of=lambda url, name: tools,
            files=vscode_files,
            input_fn=self._input(answers),
            out=self.lines.append,
        )

    def _chat_file(self):
        return self.user / "chatLanguageModels.json"

    def test_env_source_asks_nothing(self):
        self._offer((8192, "env"), ["y"])
        self.assertEqual(self.prompts, [])
        self.assertEqual(self.lines, [])
        self.assertFalse(self._chat_file().exists())

    def test_no_answer_writes_nothing(self):
        self._offer((8192, "loaded"), ["n"])
        self.assertEqual(len(self.prompts), 1)
        self.assertFalse(self._chat_file().exists())
        self.assertEqual(list(self.ws.iterdir()), [])

    def test_yes_keeps_other_group_adds_ours_and_backs_up(self):
        self._chat_file().write_text(json.dumps(OTHER_GROUP), encoding="utf-8")
        self._offer((8192, "loaded"), ["y"], tools=True)
        data = json.loads(self._chat_file().read_text(encoding="utf-8-sig"))
        self.assertEqual(len(data), 2)
        self.assertTrue(any(g.get("vendor") == "other" for g in data))
        self.assertIn(MODEL, json.dumps(data))
        self.assertIn(True, list(_values(data, "toolCalling")))
        backups = [p for p in self.user.iterdir() if ".bak-antigravity-local" in p.name]
        self.assertTrue(backups)

    def test_unparseable_file_is_left_byte_identical(self):
        raw = b"{ not json"
        self._chat_file().write_bytes(raw)
        self._offer((8192, "loaded"), ["y"])
        self.assertEqual(self._chat_file().read_bytes(), raw)
        self.assertTrue(any("Not changed" in line for line in self.lines))

    def test_remote_endpoint_writes_workspace_settings(self):
        (self.ws / ".vscode").mkdir()
        self._offer((8192, "loaded"), ["y", "y"], base_url=REMOTE)
        self.assertEqual(len(self.prompts), 2)
        settings_path = self.ws / ".vscode" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        self.assertIn("ollama.endpoint", settings)


if __name__ == "__main__":
    unittest.main()
