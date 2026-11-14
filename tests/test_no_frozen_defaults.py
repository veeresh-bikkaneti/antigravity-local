"""A default argument is evaluated once, when the module is imported. `def f(input_fn=input)` or
`def f(call=subprocess.call)` therefore freezes the real function, and a test that patches `builtins.input` or
`subprocess.call` later never reaches it (the real `input()` then blocks on stdin and the suite hangs).
This happened twice in one week (model_wizard.choose and the first agent_setup design). Use `None` and look the
function up inside the body: `input_fn = input_fn or input`.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN_NAMES = {"input"}
FROZEN_MODULES = {"subprocess", "shutil", "os", "sys", "urllib", "socket", "time"}


def frozen_defaults(source):
    """(function name, default text, line) for each default that freezes a replaceable function."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.args.defaults + [k for k in node.args.kw_defaults if k is not None]:
            if isinstance(d, ast.Name) and d.id in FROZEN_NAMES:
                found.append((node.name, d.id, d.lineno))
            elif (isinstance(d, ast.Attribute) and isinstance(d.value, ast.Name)
                  and d.value.id in FROZEN_MODULES and not d.attr.isupper()):
                found.append((node.name, f"{d.value.id}.{d.attr}", d.lineno))
    return found


class Checker(unittest.TestCase):
    """Proves the check fires on the real past mistakes, and stays quiet on the fix."""

    def test_flags_the_input_default_that_hung_the_suite(self):
        self.assertEqual(frozen_defaults("def choose(menu, input_fn=input, out=print):\n    pass\n"),
                         [("choose", "input", 1)])

    def test_flags_module_function_defaults_including_keyword_only(self):
        src = "def a(call=subprocess.call): pass\ndef b(*, which=shutil.which): pass\n"
        self.assertEqual([f[1] for f in frozen_defaults(src)], ["subprocess.call", "shutil.which"])

    def test_allows_the_none_pattern_constants_and_print(self):
        src = ("def ok(input_fn=None, out=print, mode=os.R_OK, n=3):\n"
               "    input_fn = input_fn or input\n")
        self.assertEqual(frozen_defaults(src), [])


class Repo(unittest.TestCase):
    def test_no_module_freezes_a_replaceable_function_in_a_default_argument(self):
        problems = []
        files = list(ROOT.glob("*.py")) + list((ROOT / "scripts").glob("*.py")) + list((ROOT / "tests").glob("*.py"))
        for path in files:
            for func, text, line in frozen_defaults(path.read_text(encoding="utf-8")):
                problems.append(f"{path.relative_to(ROOT)}:{line} {func}(... ={text}): default to None and "
                                f"resolve `{text}` inside {func}() so tests can patch it")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
