# parsing.py

import glob
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

@dataclass(frozen=True)
class Segment:
    text: str
    quote: str = ""

class ShellWord(str):
    def __new__(cls, segments: Sequence[Segment]):
        """Create a string retaining lexical segments.

        Args:
            segments: Quote-aware word segments.

        Returns:
            A string-compatible shell word.
        """
        instance = str.__new__(cls, "".join(item.text for item in segments))
        instance.segments = tuple(segments)
        return instance

@dataclass
class Command:
    arguments: List[str] = field(default_factory=list)
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    append_output: bool = False
    redirections: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    heredoc_data: Optional[bytes] = None

@dataclass
class Job:
    commands: List[Command]
    run_if_previous_succeeded: bool = False
    run_if_previous_failed: bool = False
    background: bool = False

class _Operator(str):
    pass

_OPERATORS = ("2>&1", "1>&2", "0>&-", "1>&-", "2>&-", "2>>", "2>", "&>", "&&", "||", ">>", "<<-", "<<", "|", "&", ";", "<", ">")

def _substitution_end(source: str, start: int) -> int:
    """Find the closing parenthesis for a command substitution.

    Args:
        source: Complete source text.
        start: Index of the opening ``$(``.

    Returns:
        Index of the matching closing parenthesis.
    """
    depth, index, quote = 1, start + 2, ""
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 2; continue
            if char == quote:
                quote = ""
        elif char in ("'", '"'):
            quote = char
        elif source.startswith("$(", index):
            depth += 1; index += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("unterminated command substitution")

def _tokens(command_line: str, posix: Optional[bool] = None) -> List[str]:
    """Tokenize a command while retaining quote provenance.

    Args:
        command_line: Source line to tokenize.
        posix: Optional compatibility override for path escaping.

    Returns:
        Shell words and operator tokens in lexical order.
    """
    windows = os.name == "nt" if posix is None else not posix
    tokens: List[str] = []
    segments: List[Segment] = []
    text = ""
    quote = ""
    index = 0
    
    def segment() -> None:
        """Flush pending text into the current word.

        Returns:
            None.
        """
        nonlocal text
        if text or quote:
            segments.append(Segment(text, quote)); text = ""
            
    def word() -> None:
        """Flush the current word into the token list.

        Returns:
            None.
        """
        segment()
        if segments:
            tokens.append(ShellWord(tuple(segments))); segments.clear()
    while index < len(command_line):
        char = command_line[index]
        if char == "\\" and quote != "single":
            if index + 1 >= len(command_line):
                raise ValueError("trailing escape")
            if windows and command_line[index + 1] not in " \\t\r\n'\"$#|&;<>":
                text += "\\"; index += 1; continue
            segment()
            segments.append(Segment(command_line[index + 1], "single"))
            index += 2; continue
        if quote:
            delimiter = "'" if quote == "single" else '"'
            if char == delimiter:
                segment(); quote = ""; index += 1; continue
            if quote == "double" and command_line.startswith("$(", index):
                end = _substitution_end(command_line, index)
                text += command_line[index:end + 1]; index = end + 1; continue
            text += char; index += 1; continue
        if char in ("'", '"'):
            segment(); quote = "single" if char == "'" else "double"; index += 1; continue
        if command_line.startswith("$(", index):
            end = _substitution_end(command_line, index)
            text += command_line[index:end + 1]; index = end + 1; continue
        if char.isspace():
            word(); index += 1; continue
        if char == "#" and not segments and not text:
            break
        operator = next((item for item in _OPERATORS if command_line.startswith(item, index)), None)
        if operator:
            word(); tokens.append(_Operator(operator)); index += len(operator); continue
        text += char; index += 1
    if quote:
        raise ValueError("No closing quotation")
    word()
    return tokens

def parse_command_line(command_line: str) -> List[Job]:
    """Parse one pyesh command line.

    Args:
        command_line: Source containing commands and operators.

    Returns:
        Parsed jobs in evaluation order.
    """
    tokens = _tokens(command_line)
    if not tokens:
        return []
    jobs, pipeline, current = [], [], Command()
    require_success = require_failure = False
    index = 0
    
    def finish_command() -> None:
        """Append the pending command to its pipeline.

        Returns:
            None.
        """
        if not current.arguments:
            raise ValueError("missing command near operator")
        pipeline.append(current)
        
    def finish_job(background: bool = False) -> None:
        """Append the pending pipeline as a job.

        Args:
            background: Whether the job runs asynchronously.

        Returns:
            None.
        """
        nonlocal current, pipeline
        finish_command()
        jobs.append(Job(list(pipeline), require_success, require_failure, background))
        pipeline, current = [], Command()
    while index < len(tokens):
        token = tokens[index]
        if not isinstance(token, _Operator):
            current.arguments.append(token)
        elif token in ("2>&1", "1>&2", "0>&-", "1>&-", "2>&-"):
            current.redirections.append((token, None))
        elif token in ("<", ">", ">>", "2>", "2>>", "&>", "<<", "<<-"):
            index += 1
            if index >= len(tokens) or isinstance(tokens[index], _Operator):
                raise ValueError("{0} requires a target".format(token))
            target = tokens[index]
            if token == "<": current.input_path = target
            elif token not in ("<<", "<<-"):
                if token in (">", ">>", "&>"):
                    current.output_path, current.append_output = target, token == ">>"
                current.redirections.append((token, target))
            else: current.redirections.append((token, target))
        elif token == "|":
            finish_command(); current = Command()
        elif token in ("&&", "||", ";", "&"):
            finish_job(token == "&")
            require_success, require_failure = token == "&&", token == "||"
        else:
            raise ValueError("unsupported operator: {0}".format(token))
        index += 1
    if current.arguments or pipeline: finish_job()
    elif tokens[-1] in ("&&", "||", "|"): raise ValueError("missing command after {0}".format(tokens[-1]))
    return jobs

def _value(state, name: str):
    """Resolve a session or special parameter.

    Args:
        state: Active shell session.
        name: Parameter name without dollar syntax.

    Returns:
        The resolved Python value.
    """
    if name == "?": return state.last_status
    if name == "$": return os.getpid()
    if name == "!": return state.last_background_pid or ""
    if name == "0": return state.argv0
    if name == "@": return list(state.argv)
    if name.isdigit():
        position = int(name)
        return state.argv[position - 1] if 0 < position <= len(state.argv) else ""
    if name in state.python.namespace: return state.python.namespace[name]
    if name in state.environment: return state.environment[name]
    raise ValueError("variable is not defined: {0}".format(name))

def _expand_text(text: str, state, command_substitute: Optional[Callable[[str], str]]):
    """Expand variables and substitutions in one word segment.

    Args:
        text: Segment text.
        state: Active shell session.
        command_substitute: Callback for nested command source.

    Returns:
        Pairs of values and expansion-origin flags.
    """
    values = []
    literal, index = "", 0
    while index < len(text):
        if text.startswith("$(", index):
            end = _substitution_end(text, index)
            if literal: values.append((literal, False)); literal = ""
            if command_substitute is None: raise ValueError("command substitution is unavailable")
            values.append((command_substitute(text[index + 2:end]), True)); index = end + 1; continue
        if text[index] == "$":
            if index + 1 < len(text) and text[index + 1] == "{":
                end = text.find("}", index + 2)
                if end < 0: raise ValueError("unterminated variable expansion")
                name, index = text[index + 2:end], end + 1
            elif index + 1 < len(text) and text[index + 1] in "?$!@":
                name, index = text[index + 1], index + 2
            else:
                match = re.match(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+", text[index + 1:])
                if match is None: literal += "$"; index += 1; continue
                name, index = match.group(0), index + 1 + len(match.group(0))
            if literal: values.append((literal, False)); literal = ""
            values.append((_value(state, name), True)); continue
        literal += text[index]; index += 1
    if literal or not values: values.append((literal, False))
    return values

def expand_arguments(arguments: Iterable[str], state=None, command_substitute: Optional[Callable[[str], str]] = None) -> List[str]:
    """Expand quote-aware words into an argument vector.

    Args:
        arguments: Parsed shell words.
        state: Active shell session, or a legacy environment-only default.
        command_substitute: Callback for command substitution.

    Returns:
        Fully expanded string arguments.
    """
    if state is None:
        class LegacyState:
            last_status, last_background_pid, argv0, argv, cwd = 0, None, "pyesh", [], os.getcwd()
            python = type("Python", (), {"namespace": {}})()
            environment = dict(os.environ)
        state = LegacyState()
    output: List[str] = []
    for argument in arguments:
        segments = getattr(argument, "segments", (Segment(str(argument)),))
        fields, unquoted = [""], False
        for part in segments:
            if part.quote == "single": fields[-1] += part.text; continue
            values = _expand_text(part.text, state, command_substitute)
            quoted = part.quote == "double"; unquoted = unquoted or not quoted
            for value, expanded in values:
                if isinstance(value, (list, tuple)) and not quoted:
                    items = value
                elif expanded and not quoted and isinstance(value, str):
                    items = value.split()
                else:
                    items = [value]
                rendered = ["" if item is None else str(item) for item in items]
                if rendered: fields[-1] += rendered[0]; fields.extend(rendered[1:])
        for value in fields:
            value = os.path.expanduser(value)
            absolute_pattern = value if os.path.isabs(value) else os.path.join(str(state.cwd), value)
            matches = glob.glob(absolute_pattern) if unquoted and any(c in value for c in "*?[") else []
            output.extend([os.path.relpath(item, str(state.cwd)) for item in sorted(matches)] if matches else [value])
    return output
