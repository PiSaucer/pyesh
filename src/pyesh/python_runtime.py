# python_runtime.py

import ast
import builtins
import os
import re
import traceback
from typing import Any, Dict

from .console import print_error

_PYTHON_STATEMENTS = (
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Delete,
    ast.Assert,
    ast.Raise,
    ast.Pass,
)
_ENVIRONMENT_REFERENCE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")

def expand_python_environment(source: str, environment=None) -> str:
    """Replace shell-style environment references with Python literals.

    Args:
        source: Python source that may contain ``$NAME`` or ``${NAME}``.

    Returns:
        Python source with unquoted references replaced by the ``repr`` of
        their environment value. Missing names become ``None``.
    """
    result = []
    index = 0
    quote = ""
    while index < len(source):
        character = source[index]
        if quote:
            if character == "\\" and index + 1 < len(source):
                result.append(source[index : index + 2])
                index += 2
                continue
            if source.startswith(quote, index):
                result.append(quote)
                index += len(quote)
                quote = ""
                continue
            result.append(character)
            index += 1
            continue
        if character in ("'", '"'):
            quote = character * 3 if source.startswith(character * 3, index) else character
            result.append(quote)
            index += len(quote)
            continue
        match = _ENVIRONMENT_REFERENCE.match(source, index)
        if match is not None:
            name = match.group(1) or match.group(2)
            values = os.environ if environment is None else environment
            result.append(repr(values.get(name)))
            index = match.end()
            continue
        result.append(character)
        index += 1
    return "".join(result)

class NativePythonSession:
    """A persistent namespace for Python entered directly at the prompt."""

    def __init__(self) -> None:
        """Create an isolated session namespace."""
        self.namespace: Dict[str, Any] = {
            "__name__": "__pyesh__",
            "__builtins__": builtins,
        }
        self.environment = dict(os.environ)

    def should_execute(self, source: str) -> bool:
        """Determine whether input is unambiguously native Python.

        Args:
            source: Raw terminal input.

        Returns:
            ``True`` for Python statements, calls, compound expressions, and
            names previously defined in this session. A new bare name remains
            a shell command so inputs such as ``ls`` keep working.
        """
        source = expand_python_environment(source, self.environment)
        try:
            module = ast.parse(source, mode="exec")
        except SyntaxError:
            return False
        if len(module.body) != 1:
            return bool(module.body) and all(
                isinstance(statement, _PYTHON_STATEMENTS) for statement in module.body
            )
        statement = module.body[0]
        if isinstance(statement, _PYTHON_STATEMENTS):
            return True
        if not isinstance(statement, ast.Expr):
            return False
        expression = statement.value
        if isinstance(expression, ast.Name):
            return expression.id in self.namespace
        if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name):
            if not (
                expression.func.id in self.namespace
                or hasattr(builtins, expression.func.id)
            ):
                return False
            return True
        # Literals, arithmetic, attributes, subscriptions, comprehensions, and
        # other structured expressions are Python only when their loaded names
        # already exist. This keeps shell forms such as ``ls -la`` from being
        # mistaken for subtraction between two new Python variables.
        stored_names = {
            node.id
            for node in ast.walk(expression)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        }
        return all(
            node.id in self.namespace
            or hasattr(builtins, node.id)
            or node.id in stored_names
            for node in ast.walk(expression)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        )

    def execute(self, source: str) -> int:
        """Execute Python and preserve resulting names for later commands.

        Args:
            source: Python source selected by ``should_execute``.

        Returns:
            Zero on success or one after a Python exception.
        """
        source = expand_python_environment(source, self.environment)
        try:
            module = ast.parse(source, mode="exec")
            if len(module.body) == 1 and isinstance(module.body[0], ast.Expr):
                expression = ast.Expression(module.body[0].value)
                value = eval(compile(expression, "<pyesh>", "eval"), self.namespace)
                if value is not None:
                    builtins.print(repr(value))
            else:
                exec(compile(module, "<pyesh>", "exec"), self.namespace)
        except SystemExit as error:
            print_error("pyesh: Python requested exit: {0}".format(error))
            return 1
        except BaseException as error:
            rendered = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ).rstrip()
            print_error(rendered)
            return 1
        return 0
