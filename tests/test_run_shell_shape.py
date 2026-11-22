"""Shape guard for run.py (Phase 6e): the shell stays thin, formatted and alias-free.

Fails when run.py has a line over 100 characters, a semicolon outside a string, a top-level
assignment whose value is a lambda or another module's attribute (or a tuple of either), a
top-level function that only forwards its arguments to another module, or more than 199 lines.
"""
import ast
import io
import tokenize
import unittest
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent / "run.py"
MAX_LINES = 199
MAX_COLUMNS = 100


def _docstring(node):
    """The node's docstring statement, or None."""
    first = node.body[0] if node.body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first
    return None


def _is_lambda_or_attribute(node):
    return isinstance(node, ast.Lambda) or isinstance(node, ast.Attribute)


def _alias_assignment(node):
    """True for `name = lambda ...`, `name = module.attr` and a tuple of either."""
    if not isinstance(node, ast.Assign):
        return False
    value = node.value
    if _is_lambda_or_attribute(value):
        return True
    return isinstance(value, ast.Tuple) and any(_is_lambda_or_attribute(elt) for elt in value.elts)


def _forwarded(node, params):
    """True for a call argument that is exactly one of the enclosing function's parameters."""
    if isinstance(node, ast.Starred):
        node = node.value
    return isinstance(node, ast.Name) and node.id in params


def _forwarder(node):
    """True when the function body is one return of a call that forwards every parameter.

    A zero-parameter factory (build_ports) is not a forwarder: it builds something new.
    """
    body = node.body[1:] if _docstring(node) else node.body
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    call = body[0].value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return False
    params = {arg.arg for arg in node.args.args}
    if node.args.vararg:
        params.add(node.args.vararg.arg)
    if node.args.kwarg:
        params.add(node.args.kwarg.arg)
    if not params:
        return False
    args = [*call.args, *(keyword.value for keyword in call.keywords if keyword.arg)]
    return bool(args) and all(_forwarded(arg, params) for arg in args)


class RunShellShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = io.open(RUN, encoding="utf-8").read()
        cls.tree = ast.parse(cls.source)
        cls.lines = cls.source.splitlines()

    def test_at_most_199_lines(self):
        self.assertLessEqual(len(self.lines), MAX_LINES, f"run.py is {len(self.lines)} lines")

    def test_no_line_over_100_columns(self):
        long_lines = [number for number, line in enumerate(self.lines, 1) if len(line) > MAX_COLUMNS]
        self.assertEqual(long_lines, [], f"lines over {MAX_COLUMNS} characters: {long_lines}")

    def test_no_semicolons_outside_strings(self):
        semicolons = [
            token.start[0]
            for token in tokenize.generate_tokens(io.StringIO(self.source).readline)
            if token.type == tokenize.OP and token.string == ";"
        ]
        self.assertEqual(semicolons, [], f"semicolons on lines: {semicolons}")

    def test_no_alias_assignments(self):
        aliases = [node.lineno for node in self.tree.body if _alias_assignment(node)]
        self.assertEqual(aliases, [], f"top-level lambda/attribute aliases on lines: {aliases}")

    def test_no_forwarder_functions(self):
        forwarders = [
            node.name
            for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _forwarder(node)
        ]
        self.assertEqual(forwarders, [], f"forwarder functions: {forwarders}")


if __name__ == "__main__":
    unittest.main()
