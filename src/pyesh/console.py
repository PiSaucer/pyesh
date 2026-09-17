# console.py

import os
import platform
from pathlib import Path
import re
import shlex
import sys
from io import StringIO
from typing import Sequence, TextIO

from rich.console import Console
from rich.text import Text

from .backends import active_python_executable

DEFAULT_WELCOME_TEMPLATE = "\n".join(
    [
        "                        _     ",
        "                       | |    ",
        " _ __  _   _  ___   ___| |__  ",
        "| '_ \\| | | |/ _ \\ / __| '_ \\ ",
        "| |_) | |_| |  __/ \\__ \\ | | |",
        "| .__/ \\__, |\\___| |___/_| |_|",
        "| |     __/ |             ",
        "|_|    |___/              ",
        "",
        "Python Expanded Shell {version}",
        "Python: {python_version} ({python_executable})",
        "Platform: {platform}",
        "Directory: {directory}",
        "Virtual environment: {venv}",
    ]
)

def _styled_welcome_art(line: str) -> Text:
    """Color one logo row by letter group rather than by row.

    Args:
        line: One row of the fixed-width ``pyesh`` artwork.

    Returns:
        Rich text with the ``PY`` columns blue and ``ESH`` columns yellow.
    """
    rendered = Text()
    # The Y descender occupies column 12 on several rows, so ESH begins at 13.
    rendered.append(line[:13], style="bold #3776AB")
    rendered.append(line[13:], style="bold #FFD43B")
    return rendered

def _styled_welcome_detail(line: str) -> Text:
    """Style a splash detail with a yellow label and white value.

    Args:
        line: Detail in ``Label: value`` form.

    Returns:
        Rich text matching the Python-inspired detail palette.
    """
    label, separator, value = line.partition(":")
    rendered = Text()
    rendered.append(label + separator, style="bold #FFD43B")
    rendered.append(value, style="bright_white")
    return rendered

def supports_color(stream: TextIO) -> bool:
    """Determine whether ANSI color should be written to a stream.

    Args:
        stream: Destination stream being considered.

    Returns:
        ``True`` for an interactive terminal unless the conventional
        ``NO_COLOR`` environment variable is present.
    """
    return "NO_COLOR" not in os.environ and hasattr(stream, "isatty") and stream.isatty()

def colorize(text: str, style: str, stream: TextIO = sys.stdout) -> str:
    """Render styled text through Rich when the destination supports color.

    Args:
        text: Text to display.
        style: Rich style expression, such as ``red`` or ``bold cyan``.
        stream: Destination used to decide whether color is appropriate.

    Returns:
        Colored text for a terminal or unchanged text otherwise.
    """
    if not supports_color(stream):
        return text
    buffer = StringIO()
    console = Console(
        file=buffer,
        force_terminal=True,
        color_system="standard",
        highlight=False,
        width=max(len(text), 1),
    )
    console.print(Text(text, style=style), end="", soft_wrap=True)
    return buffer.getvalue()

def print_error(message: str) -> None:
    """Write a red pyesh diagnostic to standard error.

    Args:
        message: Complete diagnostic text, including the ``pyesh:`` prefix.

    Returns:
        None.
    """
    print(colorize(message, "bold red", sys.stderr), file=sys.stderr)

def print_warning(message: str) -> None:
    """Write a yellow warning to standard error.

    Args:
        message: Warning text to display.

    Returns:
        None.
    """
    print(colorize(message, "yellow", sys.stderr), file=sys.stderr)

def welcome_text(version: str, template: str = "", environment=None,
                 directory=None) -> str:
    """Build the plain-text welcome splash for the current environment.

    Args:
        version: Authoritative pyesh package version.
        template: Optional user format template. Empty selects the built-in ASCII splash.

    Returns:
        A multiline ASCII splash with runtime and session information.
    """
    values_environment = os.environ if environment is None else environment
    virtual_environment = values_environment.get("VIRTUAL_ENV")
    environment_name = (Path(virtual_environment).name if virtual_environment else "none")
    values = {
        "version": version,
        "python_version": platform.python_version(),
        "python_executable": active_python_executable(values_environment),
        "platform": platform.platform(),
        "directory": str(directory or Path.cwd()),
        "venv": environment_name,
    }
    try:
        return (template or DEFAULT_WELCOME_TEMPLATE).format(**values)
    except (KeyError, ValueError) as error:
        raise ValueError("invalid welcome template: {0}".format(error)) from error

def print_welcome(version: str, template: str = "", environment=None, directory=None) -> None:
    """Print the terminal-aware pyesh welcome splash.

    Args:
        version: Authoritative pyesh package version.
        template: Optional user format template.
        environment: Optional session environment.
        directory: Optional session directory.

    Returns:
        None.
    """
    splash = welcome_text(version, template=template, environment=environment,
                          directory=directory)
    lines = splash.splitlines()
    console = Console(
        file=sys.stdout,
        no_color="NO_COLOR" in (os.environ if environment is None else environment),
        highlight=False,
        soft_wrap=True,
    )
    if template:
        for line in lines:
            console.print(Text.from_markup(line) if line else "")
        return
    for index, line in enumerate(lines):
        if not line:
            console.print()
        elif index < 8:
            console.print(_styled_welcome_art(line))
        elif line.startswith("Python Expanded"):
            console.print(Text(line, style="bold #3776AB"))
        else:
            console.print(_styled_welcome_detail(line))

def print_startup_python(environment=None) -> None:
    """Trace the active Python runtime during verbose shell startup.

    Args:
        environment: Optional session environment used for runtime selection.

    Returns:
        None.
    """
    message = "startup: Python {0} at {1}".format(platform.python_version(), active_python_executable(environment))
    print(colorize(message, "cyan", sys.stderr), file=sys.stderr)

def print_execution_trace(arguments: Sequence[str]) -> None:
    """Display the exact argument vector about to be executed.

    Args:
        arguments: Resolved executable followed by its process arguments.

    Returns:
        None.
    """
    rendered = shlex.join(str(argument) for argument in arguments)
    print(colorize("exec: {0}".format(rendered), "cyan", sys.stderr), file=sys.stderr)

def print_builtin_trace(arguments: Sequence[str]) -> None:
    """Display a built-in invocation before it changes shell state.

    Args:
        arguments: Built-in name followed by its arguments.

    Returns:
        None.
    """
    rendered = shlex.join(str(argument) for argument in arguments)
    print(colorize("builtin: {0}".format(rendered), "cyan", sys.stderr), file=sys.stderr)

def print_python_trace(source: str) -> None:
    """Display native Python source immediately before evaluation.

    Args:
        source: Python source entered at the pyesh prompt.

    Returns:
        None.
    """
    print(colorize("python: {0}".format(source), "cyan", sys.stderr), file=sys.stderr)

def print_python_pipe_trace(reference: str, direction: str) -> None:
    """Display a typed Python pipeline endpoint before conversion.

    Args:
        reference: `@variable:datatype` source text.
        direction: Either ``input`` or ``capture``.

    Returns:
        None.
    """
    print(colorize("python-pipe {0}: {1}".format(direction, reference), "cyan", sys.stderr), file=sys.stderr)

def prompt_text(prompt: str, readline_safe: bool = False) -> str:
    """Apply the interactive prompt color.

    Args:
        prompt: Plain prompt configured for the shell.
        readline_safe: Whether to mark ANSI sequences as non-printing for readline's cursor-width calculations.

    Returns:
        Prompt text with only its parenthesized Git branch colored green, or
        unchanged text when no branch is present or color is unavailable.
    """
    if not supports_color(sys.stdout):
        return prompt
    # The default template places the branch before ``%``, while custom
    # templates may choose another suffix. Color the last parenthesized
    # segment, which is the shape produced by ``{branch_segment}``.
    matches = list(re.finditer(r"\([^()\r\n]+\)", prompt))
    match = matches[-1] if matches else None
    if match is None:
        return prompt
    branch = match.group(0)
    colored = colorize(branch, "green", sys.stdout)
    if readline_safe:
        prefix, separator, suffix = colored.partition(branch)
        colored = "\001{0}\002{1}\001{2}\002".format(prefix, separator, suffix)
    return prompt[: match.start()] + colored + prompt[match.end() :]
