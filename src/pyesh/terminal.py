# terminal.py

import os
from pathlib import Path
import re
from typing import Iterable, List, Optional, Set, Tuple

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style

from .config import DEFAULT_TERMINAL_STYLES, TerminalConfig
from .history import CommandHistory
from .plugins import CORE_COMMANDS

BUILTIN_COMMANDS = tuple(sorted(CORE_COMMANDS))
_SYNTAX_TOKEN = re.compile(
    r'''(?P<space>\s+)'''
    r'''|(?P<string>"(?:\\.|[^"\\])*"?|\'(?:\\.|[^\'\\])*\'?)'''
    r'''|(?P<operator>\|\||&&|>>|[|&;<>])'''
    r'''|(?P<variable>@[A-Za-z_]\w*(?::[A-Za-z_]\w*)?|\$\{[^}]*\}|\$[A-Za-z_]\w*)'''
    r'''|(?P<option>--?[A-Za-z0-9][\w-]*)'''
    r'''|(?P<number>\b(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?)\b)'''
    r'''|(?P<word>[^\s|&;<>]+)'''
    r'''|(?P<other>.)'''
)

def syntax_fragments(command_line: str) -> List[Tuple[str, str]]:
    """Split command input into prompt-toolkit styled fragments.

    Args:
        command_line: Source currently displayed by the editor.

    Returns:
        Style and text fragments.

    The scanner is deliberately presentation-only: execution continues to use
    :mod:`pyesh.parsing`, so an incomplete line can be colored without changing
    what pyesh accepts.
    """
    fragments: List[Tuple[str, str]] = []
    command_position = True
    for match in _SYNTAX_TOKEN.finditer(command_line):
        kind = match.lastgroup or "other"
        text = match.group(0)
        style = ""
        if kind == "operator":
            style = "class:pyesh.operator"
            if text in ("|", "||", "&&", ";", "&"):
                command_position = True
        elif kind == "string":
            style = "class:pyesh.string"
            command_position = False
        elif kind == "variable":
            style = "class:pyesh.variable"
            command_position = False
        elif kind == "option":
            style = "class:pyesh.option"
            command_position = False
        elif kind == "number":
            style = "class:pyesh.number"
            command_position = False
        elif kind == "word":
            if command_position:
                style = (
                    "class:pyesh.builtin"
                    if text in BUILTIN_COMMANDS
                    else "class:pyesh.command"
                )
            command_position = False
        fragments.append((style, text))
    return fragments

class PyeshLexer(Lexer):
    """Apply pyesh shell colors while a command is being edited."""

    def lex_document(self, document: Document):
        """Create a line lexer for a prompt-toolkit document.

        Args:
            document: Current editor document.

        Returns:
            Callable returning styled fragments for a line number.
        """
        lines = document.lines

        def get_line(line_number: int) -> List[Tuple[str, str]]:
            """Style one document line.

            Args:
                line_number: Zero-based line index.

            Returns:
                Styled fragments for the selected line.
            """
            return syntax_fragments(lines[line_number]) if line_number < len(lines) else []

        return get_line

class PromptCompleter(Completer):
    """prompt-toolkit adapter for pyesh's existing completion rules."""

    def __init__(self, extra_commands: Iterable[str] = (), environment=None,
                 cwd: Optional[Path] = None) -> None:
        """Create a session-aware completion provider.

        Args:
            extra_commands: Loaded plugin command names.
            environment: Optional session environment.
            cwd: Optional session working directory.
        """
        self._extra_commands = tuple(extra_commands)
        self._environment = os.environ if environment is None else environment
        self._cwd = cwd or Path.cwd()

    def get_completions(self, document: Document, complete_event):
        """Yield completion candidates for the cursor position.

        Args:
            document: Current editor document.
            complete_event: Prompt-toolkit completion event.

        Returns:
            An iterator of prompt-toolkit completions.
        """
        word = document.get_word_before_cursor(WORD=True)
        before_word = document.text_before_cursor[: -len(word)] if word else document.text_before_cursor
        if not before_word.strip():
            candidates = sorted(set( _command_candidates(word, self._extra_commands, self._environment) + _local_command_candidates(word, self._cwd)))
        else:
            candidates = _path_candidates(word, self._cwd)
        for candidate in candidates:
            yield Completion(candidate, start_position=-len(word))

def create_prompt_session(history: CommandHistory, extra_commands: Iterable[str] = (),
                          config: Optional[TerminalConfig] = None,
                          environment=None, cwd: Optional[Path] = None) -> PromptSession:
    """Create the cross-platform interactive editor.

    Args:
        history: Existing command history.
        extra_commands: Loaded plugin command names.
        config: Terminal presentation settings.
        environment: Optional session environment.
        cwd: Optional session working directory.

    Returns:
        Configured prompt-toolkit session.
    """
    prompt_history = InMemoryHistory()
    for command in history.entries():
        prompt_history.append_string(command)
    settings = config or TerminalConfig()
    color_enabled = settings.colors and "NO_COLOR" not in (
        os.environ if environment is None else environment
    )
    configured_styles = settings.styles or DEFAULT_TERMINAL_STYLES
    styles = {"pyesh.{0}".format(key): value for key, value in configured_styles.items()}
    return PromptSession(
        history=prompt_history,
        completer=PromptCompleter(extra_commands, environment, cwd) if settings.completion else None,
        lexer=PyeshLexer() if settings.syntax_highlighting else None,
        style=Style.from_dict(styles if color_enabled else {}),
        complete_while_typing=settings.complete_while_typing,
        mouse_support=settings.mouse_support,
    )

def sync_prompt_history(session, history: CommandHistory) -> None:
    """Refresh editor history from the shared model.

    Args:
        session: Prompt-toolkit session.
        history: Authoritative command history.

    Returns:
        None.
    """
    prompt_history = InMemoryHistory(history.entries())
    session.history = prompt_history
    session.default_buffer.history = prompt_history

def formatted_prompt(prompt: str) -> ANSI:
    """Convert an ANSI-aware prompt to toolkit fragments.

    Args:
        prompt: Rendered prompt text.

    Returns:
        Prompt-toolkit ANSI object.
    """
    from .console import prompt_text
    return ANSI(prompt_text(prompt))

def _command_candidates(prefix: str, extra_commands: Iterable[str] = (), environment=None) -> List[str]:
    """Find built-ins and executable program names matching a prefix.

    Args:
        prefix: Partial command name from the first input word.
        extra_commands: Loaded plugin command names.

    Returns:
        Sorted, deduplicated command names.
    """
    folded_prefix = prefix.casefold()
    candidates: Set[str] = {command for command in BUILTIN_COMMANDS if command.casefold().startswith(folded_prefix)}
    candidates.update(command for command in extra_commands if command.casefold().startswith(folded_prefix))
    for directory_text in (os.environ if environment is None else environment).get("PATH", "").split(os.pathsep):
        if not directory_text:
            continue
        directory = Path(directory_text)
        try:
            entries = directory.iterdir()
        except OSError:
            continue
        for entry in entries:
            if entry.name.casefold().startswith(folded_prefix) and os.access(
                str(entry), os.X_OK
            ):
                candidates.add(entry.name)
    return sorted(candidates)

def _path_candidates(prefix: str, cwd: Optional[Path] = None) -> List[str]:
    """Find filesystem entries matching a partial path.

    Args:
        prefix: Partial path from the current input word.

    Returns:
        Sorted matching paths. Directory results end in the platform separator.
    """
    quote = prefix[:1] if prefix.startswith(("'", '"')) else ""
    path_prefix = prefix[1:] if quote else prefix
    closing_quote = quote if quote and path_prefix.endswith(quote) else ""
    if closing_quote:
        path_prefix = path_prefix[:-1]

    expanded = Path(path_prefix).expanduser()
    parent = expanded.parent if path_prefix else Path(".")
    if not parent.is_absolute():
        parent = (cwd or Path.cwd()) / parent
    name_prefix = expanded.name if path_prefix else ""
    try:
        entries = list(parent.iterdir())
    except OSError:
        return []

    folded_name_prefix = name_prefix.casefold()
    candidates = []
    for entry in entries:
        if not entry.name.casefold().startswith(folded_name_prefix):
            continue
        # Retain the spelling of the parent that the user entered. pathlib
        # normalizes away a leading "./", which is meaningful when completing
        # a command path, so construct the displayed prefix deliberately.
        if path_prefix.startswith("./"):
            typed_parent = os.path.dirname(path_prefix)
            displayed = "./{0}".format(entry.name) if typed_parent == "." else os.path.join(typed_parent, entry.name)
        elif path_prefix.startswith("~/"):
            typed_parent = os.path.dirname(path_prefix)
            displayed = os.path.join(typed_parent, entry.name)
        elif path_prefix:
            typed_parent = os.path.dirname(path_prefix)
            displayed = (os.path.join(typed_parent, entry.name) if typed_parent else entry.name)
        else:
            displayed = entry.name
        if entry.is_dir():
            displayed += os.sep
        candidates.append(quote + displayed + closing_quote)
    return sorted(candidates)

def _local_command_candidates(prefix: str, cwd: Optional[Path] = None) -> List[str]:
    """Complete local command paths while keeping them explicit.

    Args:
        prefix: Partial first word entered by the user.

    Returns:
        Filesystem candidates. Bare current-directory matches are prefixed with
        ``./`` (or ``.\\`` on Windows); already-qualified paths are preserved.
    """
    candidates = _path_candidates(prefix, cwd)
    if os.path.dirname(prefix):
        return candidates
    return [".{0}{1}".format(os.sep, candidate) for candidate in candidates]

class ShellCompleter:
    """Stateful adapter implementing readline's completion protocol."""

    def __init__(self, readline_module: object, extra_commands: Iterable[str] = ()) -> None:
        """Create a completer bound to a readline-compatible module.

        Args:
            readline_module: Module exposing readline buffer and index methods.
            extra_commands: Loaded plugin command names to complete.
        """
        self._readline = readline_module
        self._extra_commands = tuple(extra_commands)
        self._matches: List[str] = []

    def complete(self, text: str, state: int) -> Optional[str]:
        """Return one completion for readline.

        Args:
            text: Partial word being completed.
            state: Zero-based candidate index requested by readline.

        Returns:
            The selected candidate or ``None`` after candidates are exhausted.
        """
        if state == 0:
            beginning = self._readline.get_begidx()
            if beginning == 0:
                # The first word may be either a PATH command or a script/file
                # in the current directory. Combining both also permits pyesh's
                # automatic .py, .sh, and .ps1 dispatch to be completed.
                self._matches = sorted(
                    set(
                        _command_candidates(text, self._extra_commands)
                        + _local_command_candidates(text)
                    )
                )
            else:
                self._matches = _path_candidates(text)
        return self._matches[state] if state < len(self._matches) else None

def configure_line_editing(history: CommandHistory, extra_commands: Iterable[str] = ()) -> bool:
    """Enable arrow-key history navigation and tab completion when available.

    Args:
        history: Existing commands to seed into the terminal history.
        extra_commands: Loaded plugin command names to complete.

    Returns:
        ``True`` when readline was configured, otherwise ``False``. A false
        result is a supported fallback, notably on standard Windows Python.
    """
    try:
        import readline
    except ImportError:
        return False

    readline.set_completer(ShellCompleter(readline, extra_commands).complete)
    readline.set_completer_delims(" \t\n")
    # GNU readline and macOS libedit use different binding syntax.
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
    for command in history.entries():
        readline.add_history(command)
    return True
