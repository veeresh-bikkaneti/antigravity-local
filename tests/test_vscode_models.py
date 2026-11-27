import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agl.core import vscode_models as vm  # noqa: E402
from pathlib import PurePath  # noqa: E402

BASE = "http://localhost:11434"


def _entry(tokens=8192, tools=True):
    return vm.model_entry("m:1", BASE, tokens, tools)


def _foreign():
    return {"name": "Other Provider", "vendor": "customendpoint", "models": [{"id": "x:1"}]}


def _dirs(platform, env):
    found = vm.user_dirs(platform, PurePath("/home/u"), env)
    return [(label, path.as_posix()) for label, path in found]


class VscodeModelsTests(unittest.TestCase):
    def test_entry_added_to_empty_list(self):
        groups = vm.merge_models([], _entry())
        self.assertEqual(
            groups,
            [{"name": vm.GROUP, "vendor": "customendpoint", "apiType": "chat-completions", "models": [_entry()]}],
        )

    def test_our_entry_updated_on_second_merge(self):
        first = vm.merge_models([], _entry())
        first[0]["models"][0]["note"] = "keep me"
        second = vm.merge_models(first, _entry(tokens=16384))
        self.assertEqual(len(second), 1)
        models = second[0]["models"]
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["contextWindow"], 16384)
        self.assertEqual(models[0]["note"], "keep me")

    def test_foreign_group_untouched_and_input_not_mutated(self):
        groups = [_foreign()]
        result = vm.merge_models(groups, _entry())
        self.assertEqual(groups, [_foreign()])
        self.assertIsNot(result, groups)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], _foreign())
        self.assertEqual(result[1]["name"], vm.GROUP)

    def test_tool_calling_follows_tools_flag(self):
        self.assertIs(_entry(tools=False)["toolCalling"], False)
        self.assertIs(_entry(tools=True)["toolCalling"], True)

    def test_max_output_tokens_is_quarter_capped_at_4096(self):
        self.assertEqual(_entry(8192)["maxOutputTokens"], 2048)
        self.assertEqual(_entry(65536)["maxOutputTokens"], 4096)

    def test_non_list_raises_value_error(self):
        with self.assertRaises(ValueError):
            vm.merge_models({}, _entry())
        with self.assertRaises(ValueError):
            vm.merge_settings([], BASE)

    def test_chat_url_with_and_without_v1(self):
        expected = "http://localhost:11434/v1/chat/completions"
        self.assertEqual(vm.chat_url(BASE + "/v1"), expected)
        self.assertEqual(vm.chat_url(BASE), expected)

    def test_is_default_endpoint(self):
        self.assertTrue(vm.is_default_endpoint("http://localhost:11434"))
        self.assertTrue(vm.is_default_endpoint("http://127.0.0.1:11434/v1/"))
        self.assertFalse(vm.is_default_endpoint("http://example.com:11434"))

    def test_user_dirs_win32_uses_appdata_or_roaming_fallback(self):
        dirs = _dirs("win32", {"APPDATA": "/roam"})
        self.assertEqual([label for label, _ in dirs], ["VS Code", "VS Code Insiders"])
        self.assertTrue(dirs[0][1].endswith("/roam/Code/User"))
        self.assertTrue(dirs[1][1].endswith("/roam/Code - Insiders/User"))
        fallback = _dirs("win32", {"APPDATA": ""})
        self.assertTrue(fallback[0][1].endswith("AppData/Roaming/Code/User"))

    def test_user_dirs_darwin(self):
        dirs = _dirs("darwin", {})
        self.assertTrue(dirs[0][1].endswith("Library/Application Support/Code/User"))
        self.assertTrue(dirs[1][1].endswith("Library/Application Support/Code - Insiders/User"))

    def test_user_dirs_linux(self):
        dirs = _dirs("linux", {})
        self.assertTrue(dirs[0][1].endswith(".config/Code/User"))
        self.assertTrue(dirs[1][1].endswith(".config/Code - Insiders/User"))

    def test_merge_settings_keeps_other_keys(self):
        merged = vm.merge_settings({"editor.fontSize": 14, "ollama.endpoint": "old"}, BASE + "/v1")
        self.assertEqual(merged, {"editor.fontSize": 14, "ollama.endpoint": BASE})


if __name__ == "__main__":
    unittest.main()
