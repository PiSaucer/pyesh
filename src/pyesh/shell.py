# shell.py

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
from dataclasses import dataclass, field, replace
import codeop
import os
from pathlib import Path
import re
import sys
from typing import Callable, List, Optional, Tuple

from . import __version__
from .backends import active_virtual_environment, virtual_environment_scripts
from .builtins import describe_commands, run_builtin
from .config import ShellConfig
from .console import (
    print_builtin_trace,
    print_error,
    print_python_pipe_trace,
    print_python_trace,
    print_startup_python,
    print_welcome,
)
from .execution import run_pipeline, run_pipeline_captured
from .help import TOPICS
from .history import CommandHistory
from .jobs import JobTable
from .parsing import (
    Command,
    Segment,
    ShellWord,
    collapse_line_continuations,
    expand_arguments,
    parse_command_line,
    shell_input_incomplete,
)
from .plugins import CORE_COMMANDS, PluginManager
from .prompt import build_prompt
from .python_runtime import NativePythonSession
from .python_pipes import (
    PythonPipeReference,
    decode_variable,
    encode_variable,
    parse_reference,
)
from .terminal import create_prompt_session, formatted_prompt
from .user_files import (
    UserFiles,
    enabled_plugins,
    load_environment,
    load_prompt_template,
    load_search_paths,
    load_welcome_config,
    read_history,
    save_welcome_enabled,
    startup_commands,
    user_files,
    write_history,
)
from .profiles import apply_profile_environment

_PYTHON_ASSIGNMENT = re.compile(r"^\s*(@[A-Za-z_][A-Za-z0-9_]*(?::[a-z]+)?)\s*=\s*(.+)$", re.DOTALL)
_PYTHON_CAPTURE = re.compile(r"^\s*(@[A-Za-z_][A-Za-z0-9_]*(?::[a-z]+)?)\s*<\s*(.+)$", re.DOTALL)

@dataclass
class SessionState:
    """Mutable settings that may change during one interactive session.

    Attributes:
        verbose: Whether external process launches are traced.
        exit_requested: Whether the ``exit`` built-in requested session end.
        python: Persistent namespace for native Python input.
        plugins: Explicitly enabled commands loaded for this session.
        virtual_environments: Saved ``PATH`` and ``VIRTUAL_ENV`` values for
            nested activations performed by pyesh.
        welcome_enabled: Whether interactive startup displays the splash.
        welcome_template: Optional user-defined multiline splash template.
        welcome_path: Persistent toggle file for an interactive session.
    """

    verbose: bool = False
    cwd: Path = field(default_factory=Path.cwd)
    environment: dict = field(default_factory=lambda: dict(os.environ))
    argv0: str = "pyesh"
    argv: List[str] = field(default_factory=list)
    last_background_pid: Optional[int] = None
    pipefail: bool = False
    pending_heredocs: List[bytes] = field(default_factory=list)
    force_exit: bool = False
    exit_warning_shown: bool = False
    exit_requested: bool = False
    exit_status: int = 0
    last_status: int = 0
    previous_directory: Optional[str] = None
    directory_stack: List[str] = field(default_factory=list)
    aliases: dict = field(default_factory=dict)
    history: CommandHistory = field(default_factory=CommandHistory)
    jobs: JobTable = field(default_factory=JobTable)
    python: NativePythonSession = field(default_factory=NativePythonSession)
    plugins: PluginManager = field(default_factory=PluginManager)
    virtual_environments: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    welcome_enabled: bool = False
    welcome_template: str = ""
    welcome_path: Optional[Path] = None

    def __post_init__(self) -> None:
        """Install public Python helpers in the session namespace.

        Returns:
            None.
        """
        self.environment.setdefault("NULL_DEVICE", os.devnull)
        self.python.environment = self.environment
        self.python.namespace["argv"] = self.argv
        self.python.namespace["env"] = self.environment
        self.python.namespace["sh"] = lambda command: execute_command_line(command, state=self, record_history=False)

        def capture(command: str, type: str = "str"):
            """Capture one foreground job into a typed Python value.

            Args:
                command: Pyesh command source.
                type: Typed-pipeline decoder name.

            Returns:
                Decoded command output.
            """
            reference = parse_reference("@value:{0}".format(type))
            if reference is None:
                raise ValueError("unsupported capture type: {0}".format(type))
            jobs = parse_command_line(command)
            if len(jobs) != 1 or jobs[0].background:
                raise ValueError("capture requires one foreground job")
            for item in jobs[0].commands:
                _resolve_command(item, self)
                item.arguments = expand_arguments(item.arguments, state=self,
                    command_substitute=lambda nested: _command_substitute(nested, self))
            if len(jobs[0].commands) == 1:
                stream = StringIO()
                with redirect_stdout(stream):
                    builtin_status = _run_builtin(jobs[0].commands[0], self)
                if builtin_status is not None:
                    self.last_status = builtin_status
                    return decode_variable(reference, stream.getvalue().encode("utf-8"))
            status, output = run_pipeline_captured(
                jobs[0].commands, verbose=self.verbose, cwd=self.cwd,
                environment=self.environment, pipefail=self.pipefail,
            )
            self.last_status = status
            return decode_variable(reference, output)

        self.python.namespace["capture"] = capture

def _venv_root(activation_file: Path) -> Optional[Path]:
    """Recognize a standard virtual-environment activation script path.

    Args:
        activation_file: Candidate file supplied to ``source``.

    Returns:
        Virtual-environment root, or ``None`` for a regular command file.
    """
    parent = activation_file.parent
    name = activation_file.name.lower()
    if parent.name == "bin" and name == "activate":
        return parent.parent.resolve()
    if parent.name.lower() == "scripts" and name in ("activate", "activate.bat", "activate.ps1"):
        return parent.parent.resolve()
    return None

def _prepare_boot_virtual_environment(environment=None) -> Optional[Path]:
    """Normalize an inherited active virtual environment for startup.

    Args:
        environment: Optional session environment mapping.

    Returns:
        Active environment root, or ``None`` outside a virtual environment.
    """
    target = os.environ if environment is None else environment
    configured = target.get("VIRTUAL_ENV")
    root = Path(configured).expanduser().resolve() if configured else None
    if root is not None and not virtual_environment_scripts(root).is_dir():
        root = None
    if root is None:
        return None
    scripts = str(virtual_environment_scripts(root).resolve())
    entries = [entry for entry in target.get("PATH", "").split(os.pathsep) if entry]
    target["VIRTUAL_ENV"] = str(root)
    target["PATH"] = os.pathsep.join([scripts] + [entry for entry in entries if entry != scripts])
    return root

def _source_file(arguments: List[str], state: SessionState) -> int:
    """Activate a virtual environment or execute a pyesh command file.

    Args:
        arguments: ``source`` followed by exactly one path.
        state: Mutable session including activation restoration state.

    Returns:
        Zero on success or a nonzero command/file status.
    """
    if len(arguments) != 2:
        print_error("pyesh: source: expected exactly one file")
        return 2
    path = Path(arguments[1]).expanduser()
    if not path.is_file():
        print_error("pyesh: source: no such file: {0}".format(path))
        return 1
    root = _venv_root(path)
    if root is not None:
        scripts = path.parent.resolve()
        old_path = state.environment.get("PATH", "")
        state.virtual_environments.append((old_path, state.environment.get("VIRTUAL_ENV")))
        state.environment["VIRTUAL_ENV"] = str(root)
        state.environment["PATH"] = os.pathsep.join((str(scripts), old_path))
        return 0
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print_error("pyesh: source: could not read {0}: {1}".format(path, error))
        return 1
    return execute_script(source, state, str(path))

def _deactivate_virtual_environment(arguments: List[str], state: SessionState) -> int:
    """Restore values saved by the latest virtual-environment activation.

    Args:
        arguments: The ``deactivate`` command with no extra arguments.
        state: Session containing saved activation state.

    Returns:
        Zero on success or nonzero when no activation can be restored.
    """
    if len(arguments) != 1:
        print_error("pyesh: deactivate: no arguments expected")
        return 2
    if not state.virtual_environments:
        print_error("pyesh: deactivate: no pyesh-activated virtual environment")
        return 1
    old_path, old_virtual_env = state.virtual_environments.pop()
    state.environment["PATH"] = old_path
    if old_virtual_env is None:
        state.environment.pop("VIRTUAL_ENV", None)
    else:
        state.environment["VIRTUAL_ENV"] = old_virtual_env
    return 0

def _welcome(arguments: List[str], state: SessionState) -> int:
    """Show or control the session welcome splash.

    Args:
        arguments: ``welcome`` with optional ``on``, ``off``, or ``status``.
        state: Session containing the startup toggle and custom template.

    Returns:
        Zero on success or one for invalid arguments/templates.
    """
    if len(arguments) > 2:
        print_error("pyesh: welcome: expected on, off, or status")
        return 1
    if len(arguments) == 2:
        mode = arguments[1].lower()
        if mode == "on":
            enabled = True
        elif mode == "off":
            enabled = False
        elif mode != "status":
            print_error("pyesh: welcome: expected on, off, or status")
            return 1
        else:
            enabled = state.welcome_enabled
        if mode in ("on", "off") and state.welcome_path is not None:
            try:
                save_welcome_enabled(state.welcome_path, enabled)
            except (OSError, UnicodeError) as error:
                print_error("pyesh: welcome: could not save setting: {0}".format(error))
                return 1
        state.welcome_enabled = enabled
        print("welcome: {0}".format("on" if state.welcome_enabled else "off"))
        return 0
    try:
        print_welcome(__version__, template=state.welcome_template, environment=state.environment, directory=state.cwd)
    except ValueError as error:
        print_error("pyesh: welcome: {0}".format(error))
        print_welcome(__version__, environment=state.environment, directory=state.cwd)
        return 1
    return 0

def _run_builtin(command: Command, state: SessionState) -> Optional[int]:
    """Apply redirections around an in-process command.

    Args:
        command: Parsed command.
        state: Active shell session.

    Returns:
        Built-in status, or ``None`` for an external command.
    """
    name = command.arguments[0]
    if name not in CORE_COMMANDS and name not in state.plugins.command_names():
        return None
    if name == "man" and len(command.arguments) > 1 and not (len(command.arguments) == 2 and command.arguments[1] in TOPICS):
        return run_pipeline([command], verbose=state.verbose, jobs=state.jobs, cwd=state.cwd, environment=state.environment, pipefail=state.pipefail)
    if (not command.redirections and command.input_path is None and command.output_path is None and command.heredoc_data is None):
        return _run_builtin_inner(command, state)
    # Preserve the existing restrictions on session-control commands.
    if name in ("welcome", "source", "deactivate", "verbose"):
        print_error("pyesh: {0}: redirection is not supported".format(name))
        return 2 if name in ("source", "deactivate") else 1
    try:
        with ExitStack() as stack:
            if command.heredoc_data is not None:
                if name != "read":
                    print_error("pyesh: heredoc input is only supported for read built-in")
                    return 1
                stream = StringIO(command.heredoc_data.decode("utf-8"))
                previous_input = sys.stdin
                stack.callback(setattr, sys, "stdin", previous_input)
                sys.stdin = stream
            elif command.input_path is not None:
                if name != "read":
                    print_error("pyesh: input redirection is only supported for read")
                    return 1
                stream = stack.enter_context(open(command.input_path, encoding="utf-8"))
                previous_input = sys.stdin
                stack.callback(setattr, sys, "stdin", previous_input)
                sys.stdin = stream
            redirects = command.redirections or ([(">>" if command.append_output else ">", command.output_path)] if command.output_path is not None else [])
            for operator, path in redirects:
                if operator == "2>&1":
                    stack.enter_context(redirect_stderr(sys.stdout))
                    continue
                if operator == "1>&2":
                    stack.enter_context(redirect_stdout(sys.stderr))
                    continue
                if operator in ("0>&-", "1>&-", "2>&-"):
                    stream = stack.enter_context(open(os.devnull,
                        "r" if operator == "0>&-" else "w", encoding="utf-8"))
                    if operator == "0>&-":
                        previous_input = sys.stdin
                        stack.callback(setattr, sys, "stdin", previous_input)
                        sys.stdin = stream
                    elif operator == "1>&-":
                        stack.enter_context(redirect_stdout(stream))
                    else:
                        stack.enter_context(redirect_stderr(stream))
                    continue
                stream = stack.enter_context(open(path, "a" if operator in (">>", "2>>") else "w", encoding="utf-8"))
                if operator in (">", ">>", "&>"):
                    stack.enter_context(redirect_stdout(stream))
                if operator in ("2>", "2>>", "&>"):
                    stack.enter_context(redirect_stderr(stream))
            return _run_builtin_inner(replace(
                command, input_path=None, output_path=None, append_output=False, redirections=[]
            ), state)
    except OSError as error:
        print_error("pyesh: could not redirect output: {0}".format(error))
        return 1

def _run_builtin_inner(command: Command, state: SessionState) -> Optional[int]:
    """Run a standalone built-in with optional output redirection.

    Args:
        command: Parsed command and redirection paths.
        state: Mutable session controls used by stateful built-ins.

    Returns:
        ``None`` when the command is external, otherwise its shell status.
    """
    if command.arguments[0] in state.plugins.command_names():
        if state.verbose:
            print_builtin_trace(command.arguments)
        if command.input_path is not None:
            print_error("pyesh: input redirection is not valid for plugin commands")
            return 1
        if command.output_path is None:
            return state.plugins.run(command.arguments)
        try:
            mode = "a" if command.append_output else "w"
            with Path(command.output_path).open(mode, encoding="utf-8") as output:
                with redirect_stdout(output):
                    return state.plugins.run(command.arguments)
        except OSError as error:
            print_error("pyesh: could not redirect output: {0}".format(error))
            return 1
    builtin_names = tuple(CORE_COMMANDS)
    if command.arguments[0] not in builtin_names:
        return None
    if command.arguments[0] == "man" and len(command.arguments) > 1:
        is_pyesh_topic = (
            len(command.arguments) == 2 and command.arguments[1] in TOPICS
        )
        if not is_pyesh_topic:
            return run_pipeline([command], verbose=state.verbose, jobs=state.jobs, cwd=state.cwd, environment=state.environment, pipefail=state.pipefail)
    if state.verbose:
        print_builtin_trace(command.arguments)
    if command.arguments[0] == "welcome":
        if command.input_path is not None or command.output_path is not None:
            print_error("pyesh: welcome: redirection is not supported")
            return 1
        return _welcome(command.arguments, state)
    if command.arguments[0] in ("source", "deactivate"):
        if command.input_path is not None or command.output_path is not None:
            print_error("pyesh: {0}: redirection is not supported".format(command.arguments[0]))
            return 2
        if command.arguments[0] == "source":
            return _source_file(command.arguments, state)
        return _deactivate_virtual_environment(command.arguments, state)
    if command.arguments[0] == "verbose":
        if command.input_path is not None or command.output_path is not None:
            print_error("pyesh: verbose: redirection is not supported")
            return 1
        if len(command.arguments) > 2:
            print_error("pyesh: verbose: expected on, off, or status")
            return 1
        mode = command.arguments[1].lower() if len(command.arguments) == 2 else "status"
        if mode == "on":
            state.verbose = True
        elif mode == "off":
            state.verbose = False
        elif mode != "status":
            print_error("pyesh: verbose: expected on, off, or status")
            return 1
        print("verbose: {0}".format("on" if state.verbose else "off"))
        return 0
    if command.arguments[0] == "plugins":
        if len(command.arguments) > 1:
            print_error("pyesh: plugins: no arguments expected")
            return 1
        descriptions = state.plugins.describe()
        if descriptions:
            for description in descriptions:
                print(description)
        else:
            print("no enabled pyesh plugin commands")
        return 0
    if command.arguments[0] == "command":
        args = command.arguments[1:]
        if args and args[0] in ("-v", "-V"):
            try:
                return describe_commands(args[1:], state, terse=args[0] == "-v")
            except ValueError as error:
                print_error("pyesh: command: {0}".format(error))
                return 2
        return 0
    return run_builtin(command.arguments, state)

def _write_raw_output(data: bytes) -> None:
    """Write captured bytes back to the active standard output.

    Args:
        data: Exact pipeline output bytes.

    Returns:
        None.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        buffer.flush()
    else:
        sys.stdout.write(data.decode("utf-8", errors="replace"))
        sys.stdout.flush()

def _save_python_pipe_file(command: Command, data: bytes) -> None:
    """Write or append exact captured bytes for a virtual endpoint.

    Args:
        command: Virtual endpoint containing optional redirection metadata.
        data: Exact bytes to retain.

    Returns:
        None.

    Raises:
        ValueError: If the destination cannot be written.
    """
    if command.output_path is None:
        return
    mode = "ab" if command.append_output else "wb"
    try:
        with Path(command.output_path).open(mode) as output:
            output.write(data)
    except OSError as error:
        raise ValueError("could not write Python pipeline file {0}: {1}".format(command.output_path, error)) from error

def _execute_python_assignment(command_line: str, state: SessionState) -> Optional[int]:
    """Execute ``@name[:datatype] = expression`` assignment syntax.

    Args:
        command_line: Unparsed terminal input.
        state: Session whose persistent Python namespace receives the value.

    Returns:
        The execution status, or ``None`` when this is not an assignment.

    Raises:
        ValueError: If the variable reference or conversion is invalid.
    """
    match = _PYTHON_ASSIGNMENT.fullmatch(command_line)
    if match is None:
        return None
    reference = parse_reference(match.group(1))
    if reference is None:
        raise ValueError("invalid Python variable assignment")
    temporary_name = "__pyesh_assignment_value__"
    status = state.python.execute("{0} = ({1})".format(temporary_name, match.group(2)))
    if status != 0:
        return status
    try:
        raw_value = encode_variable(PythonPipeReference(temporary_name, reference.datatype), state.python.namespace)
        state.python.namespace[reference.name] = decode_variable(reference, raw_value)
    finally:
        state.python.namespace.pop(temporary_name, None)
    return 0

def _rewrite_python_capture(command_line: str) -> str:
    """Rewrite variable-first command capture into ordinary pipeline syntax.

    ``@result < command arg`` is a convenient equivalent of
    ``command arg | @result``. A single word after ``<`` remains file input so
    ``@result < file.txt`` keeps its conventional redirection meaning.

    Args:
        command_line: Raw terminal input before shell parsing.

    Returns:
        Rewritten pipeline text, or the original input when it is not the
        variable-first capture form.
    """
    match = _PYTHON_CAPTURE.fullmatch(command_line)
    if match is None:
        return command_line
    reference, source = match.groups()
    source_jobs = parse_command_line(source)
    if (
        len(source_jobs) == 1
        and len(source_jobs[0].commands) == 1
        and len(source_jobs[0].commands[0].arguments) == 1
        and source_jobs[0].commands[0].input_path is None
        and source_jobs[0].commands[0].output_path is None
    ):
        return command_line
    return "{0} | {1}".format(source, reference)

def _load_python_pipe_file(
    command: Command, reference: PythonPipeReference, state: SessionState
) -> int:
    """Read a redirected file into a typed Python variable.

    Args:
        command: Standalone endpoint containing the input path.
        reference: Destination variable and datatype.
        state: Session whose Python namespace receives the content.

    Returns:
        Zero after a successful read and conversion.

    Raises:
        ValueError: If the file cannot be read or decoded.
    """
    try:
        data = Path(command.input_path or "").read_bytes()
    except OSError as error:
        raise ValueError("could not read Python pipeline file {0}: {1}".format(command.input_path, error)) from error
    state.python.namespace[reference.name] = decode_variable(reference, data)
    return 0

def _execute_python_pipeline(commands: List[Command], state: SessionState, verbose: bool) -> int:
    """Execute a pipeline containing typed Python variable endpoints.

    Args:
        commands: Parsed real commands and virtual endpoint commands.
        state: Session containing the persistent Python namespace.
        verbose: Whether to trace conversions and child processes.

    Returns:
        The final real command status, or zero when converting variables only.

    Raises:
        ValueError: If endpoint placement, conversion, or file output fails.
    """
    references = [
        parse_reference(command.arguments[0]) if len(command.arguments) == 1 else None
        for command in commands
    ]
    endpoint_indexes = [index for index, reference in enumerate(references) if reference]
    if any(index not in (0, len(commands) - 1) for index in endpoint_indexes):
        raise ValueError("Python variable endpoints are valid only at pipeline edges")
    if not endpoint_indexes:
        raise ValueError("internal Python pipeline routing error")

    source: Optional[PythonPipeReference] = references[0]
    capture: Optional[PythonPipeReference] = (references[-1] if len(commands) > 1 else None)
    if len(commands) == 1 and source is not None and commands[0].input_path is not None:
        return _load_python_pipe_file(commands[0], source, state)
    if source is not None and commands[0].input_path is not None:
        raise ValueError("Python pipeline input cannot also use < redirection")
    if capture is not None and commands[-1].input_path is not None:
        raise ValueError("Python pipeline capture cannot use < redirection")

    input_data = None
    first = 1 if source is not None else 0
    last = len(commands) - 1 if capture is not None else len(commands)
    real_commands = commands[first:last]
    if source is not None and real_commands and real_commands[0].input_path is not None:
        raise ValueError("Python pipeline input cannot be combined with command < input")
    if source is not None:
        if verbose:
            print_python_pipe_trace(commands[0].arguments[0], "input")
        input_data = encode_variable(source, state.python.namespace)

    if real_commands and capture is not None:
        status, output = run_pipeline_captured(real_commands, input_data=input_data, verbose=verbose, cwd=state.cwd, environment=state.environment, pipefail=state.pipefail)
    elif real_commands:
        status = run_pipeline(real_commands, input_data=input_data, verbose=verbose, cwd=state.cwd, environment=state.environment, pipefail=state.pipefail)
        output = b""
    else:
        status, output = 0, input_data or b""

    if capture is not None:
        if verbose:
            print_python_pipe_trace(commands[-1].arguments[0], "capture")
        _save_python_pipe_file(commands[-1], output)
        state.python.namespace[capture.name] = decode_variable(capture, output)
    elif source is not None and not real_commands:
        _save_python_pipe_file(commands[0], output)
        if commands[0].output_path is None:
            _write_raw_output(output)
    return status

def execute_command_line(command_line: str, state: Optional[SessionState] = None, record_history: bool = True) -> int:
    """Execute one line and retain its history and status.

    Args:
        command_line: Pyesh source line.
        state: Optional active shell session.
        record_history: Add source to session history when true.

    Returns:
        Final command status.
    """
    session = state or SessionState()
    if session.exit_requested:
        return session.exit_status
    if record_history:
        session.history.add(command_line)
    try:
        status = _execute_command_line(command_line, session)
    except ValueError:
        session.last_status = 2
        raise
    except KeyboardInterrupt:
        session.last_status = 130
        raise
    session.last_status = status
    return status

def python_input_incomplete(source: str) -> bool:
    """Check whether a Python compound statement needs more input.

    Args:
        source: Candidate Python source.

    Returns:
        ``True`` when a continuation line is required.
    """
    if not re.match(r"^\s*(?:async\s+def|def|class|if|for|while|try|with)\b", source):
        return False
    try:
        return codeop.compile_command(source, symbol="exec") is None
    except (SyntaxError, OverflowError, ValueError):
        return False

def _append_python_continuation(source: str, continuation: str) -> str:
    """Append interactive Python input with a convenient inferred indent.

    The continuation prompt is line-oriented rather than a Python-aware editor.
    When a user enters an unindented line immediately after a suite header,
    infer one standard indentation level. Explicit whitespace is always kept.
    
    Args:
        source: Current Python source.
        continuation: New line to append.
    
    Returns:
        Combined source with inferred indentation.
    """
    previous_line = source.splitlines()[-1]
    if continuation and not continuation[0].isspace() and previous_line.rstrip().endswith(":"):
        indentation = previous_line[: len(previous_line) - len(previous_line.lstrip())]
        continuation = indentation + "    " + continuation
    return source + "\n" + continuation

def execute_script(
    source: str,
    state: SessionState,
    filename: str = "<string>",
    record_history: bool = False,
) -> int:
    """Execute pyesh source, collecting Python compound statements.

    Args:
        source: Complete native script text.
        state: Active shell session.
        filename: Diagnostic source name.
        record_history: Add each executable command or Python block to history.

    Returns:
        Final command or explicit exit status.
    """
    lines = source.splitlines()
    status, index = 0, 0
    while index < len(lines):
        line = lines[index]
        index += 1
        while shell_input_incomplete(line) and index < len(lines):
            line += "\n" + lines[index]
            index += 1
        line = collapse_line_continuations(line)
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        block = line
        heredocs = []
        for match in re.finditer(r"<<(-?)(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2", line):
            strip_tabs, quoted, delimiter = bool(match.group(1)), bool(match.group(2)), match.group(3)
            body = []
            while index < len(lines):
                candidate = lines[index]
                index += 1
                compared = candidate.lstrip("\t") if strip_tabs else candidate
                if compared == delimiter:
                    break
                body.append(compared if strip_tabs else candidate)
            else:
                raise ValueError("{0}:{1}: unterminated heredoc {2}".format(filename, index, delimiter))
            content = "\n".join(body) + "\n"
            if not quoted:
                content = expand_arguments([ShellWord((Segment(content, "double"),))], state=state,
                    command_substitute=lambda nested: _command_substitute(nested, state))[0]
            heredocs.append(content.encode("utf-8"))
        state.pending_heredocs.extend(heredocs)
        while python_input_incomplete(block) and index < len(lines):
            block += "\n" + lines[index]
            index += 1
        if python_input_incomplete(block):
            raise ValueError("{0}:{1}: incomplete Python block".format(filename, index))
        try:
            status = execute_command_line(block, state=state, record_history=record_history)
        except ValueError as error:
            raise ValueError("{0}:{1}: {2}".format(filename, index, error)) from error
        if state.exit_requested:
            return state.exit_status
    return status

def _expand_alias(command: Command, state: SessionState) -> None:
    """Expand the command's first word through session aliases.

    Args:
        command: Command to modify.
        state: Active shell session.

    Returns:
        None.
    """
    seen = set()
    while command.arguments and command.arguments[0] in state.aliases:
        name = command.arguments[0]
        if name in seen:
            raise ValueError("alias cycle: {0}".format(name))
        seen.add(name)
        replacement = parse_command_line(state.aliases[name])[0].commands[0].arguments
        command.arguments = replacement + command.arguments[1:]
        if replacement[0] == name:
            break

def _resolve_command(command: Command, state: SessionState) -> None:
    """Apply aliases and ``command`` bypass semantics.

    Args:
        command: Command to modify.
        state: Active shell session.

    Returns:
        None.
    """
    _expand_alias(command, state)
    # command suppresses alias expansion for its operand, retaining built-ins.
    while command.arguments[0] == "command" and len(command.arguments) > 1:
        if command.arguments[1] in ("-v", "-V"):
            break
        if command.arguments[1] == "--":
            command.arguments = command.arguments[2:] or ["command"]
        elif command.arguments[1].startswith("-"):
            raise ValueError("command: unsupported option")
        else:
            command.arguments = command.arguments[1:]

def _command_substitute(source: str, state: SessionState) -> str:
    """Execute one foreground job for command substitution.

    Args:
        source: Nested pyesh source.
        state: Active shell session.

    Returns:
        UTF-8 stdout without trailing newlines.
    """
    jobs = parse_command_line(source)
    if len(jobs) != 1 or jobs[0].background:
        raise ValueError("command substitution requires one foreground job")
    job = jobs[0]
    for command in job.commands:
        _resolve_command(command, state)
        command.arguments = expand_arguments(command.arguments, state=state, command_substitute=lambda nested: _command_substitute(nested, state))
    if len(job.commands) == 1:
        stream = StringIO()
        with redirect_stdout(stream):
            status = _run_builtin(job.commands[0], state)
        if status is not None:
            state.last_status = status
            return stream.getvalue().rstrip("\r\n")
    if any(command.arguments[0] in CORE_COMMANDS for command in job.commands):
        raise ValueError("stateful built-ins are not valid in command substitution")
    status, output = run_pipeline_captured(job.commands, verbose=state.verbose, cwd=state.cwd, environment=state.environment, pipefail=state.pipefail)
    state.last_status = status
    try:
        return output.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError as error:
        raise ValueError("command substitution output is not UTF-8") from error

def _builtin_child_arguments() -> List[str]:
    """Return the child-process prefix for pipeline-safe built-ins."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--_pyesh-builtin-child"]
    return [sys.executable, str(Path(__file__).with_name("_builtin_child.py"))]

def _execute_command_line(command_line: str, state: Optional[SessionState] = None) -> int:
    """Parse and execute one line of pyesh command syntax.

    Args:
        command_line: Raw command text.
        state: Mutable session controls. A default state is used for one-off
            calls from alternate frontends.

    Returns:
        The last executed job status. An ``exit`` built-in sets
        ``state.exit_requested`` and returns the requested status.

    Raises:
        ValueError: If command syntax is invalid.
    """
    session = state or SessionState()
    assignment_status = _execute_python_assignment(command_line, session)
    if assignment_status is not None:
        if session.verbose:
            print_python_trace(command_line)
        return assignment_status
    command_line = _rewrite_python_capture(command_line)
    first_word = command_line.lstrip().split(None, 1)[0] if command_line.strip() else ""
    shell_command = (first_word in CORE_COMMANDS or first_word in session.aliases
                     or first_word in session.plugins.command_names())
    if not shell_command and session.python.should_execute(command_line):
        if session.verbose:
            print_python_trace(command_line)
        return session.python.execute(command_line)
    jobs = parse_command_line(command_line)
    pending = iter(session.pending_heredocs)
    try:
        for job in jobs:
            for command in job.commands:
                if any(operator in ("<<", "<<-") for operator, _ in command.redirections):
                    command.heredoc_data = next(pending)
                    command.redirections = [(operator, path) for operator, path in command.redirections
                                            if operator not in ("<<", "<<-")]
    except StopIteration:
        raise ValueError("heredoc body is missing") from None
    finally:
        session.pending_heredocs.clear()
    status = 0
    for job in jobs:
        session.last_status = status if job is not jobs[0] else session.last_status
        if job.run_if_previous_succeeded and status != 0:
            continue
        if job.run_if_previous_failed and status == 0:
            continue
        for command in job.commands:
            _resolve_command(command, session)
            command.arguments = expand_arguments(command.arguments, state=session, command_substitute=lambda source: _command_substitute(source, session))
            if command.input_path is not None:
                command.input_path = expand_arguments([command.input_path], state=session, command_substitute=lambda source: _command_substitute(source, session))[0]
            if command.output_path is not None:
                command.output_path = expand_arguments([command.output_path], state=session, command_substitute=lambda source: _command_substitute(source, session))[0]
            command.redirections = [(operator, expand_arguments([path], state=session, command_substitute=lambda source: _command_substitute(source, session))[0] if path is not None else None) for operator, path in command.redirections]
        if len(job.commands) > 1 or job.background:
            for command in job.commands:
                if command.arguments[0] in ("echo", "printf", "pwd"):
                    command.arguments = _builtin_child_arguments() + command.arguments
                elif command.arguments[0] in session.plugins.command_names():
                    plugin_name = session.plugins.pipeline_plugin(command.arguments[0])
                    if plugin_name is not None:
                        command.arguments = _builtin_child_arguments() + ["--plugin", plugin_name] + command.arguments
        python_pipe_commands = [command for command in job.commands if command.arguments and command.arguments[0].startswith("@")]
        if python_pipe_commands:
            if job.background:
                raise ValueError("Python variable pipelines cannot run in background")
            for command in python_pipe_commands:
                if any(operator not in (">", ">>") for operator, _ in command.redirections):
                    raise ValueError("stderr redirection is not valid for Python variable endpoints")
                if len(command.arguments) != 1 or parse_reference(command.arguments[0]) is None:
                    raise ValueError("Python pipeline endpoint must be @variable or @variable:datatype")
            real_commands = [command for command in job.commands if not command.arguments[0].startswith("@")]
            if any(command.arguments[0] in CORE_COMMANDS or command.arguments[0] in session.plugins.command_names() for command in real_commands):
                raise ValueError("built-ins cannot be used in Python variable pipelines")
            status = _execute_python_pipeline(job.commands, state=session, verbose=session.verbose)
            continue
        if len(job.commands) == 1 and not job.background:
            builtin_status = _run_builtin(job.commands[0], session)
            if builtin_status is not None:
                status = builtin_status
                if session.exit_requested:
                    return session.exit_status
                continue
        if any(command.arguments[0] in CORE_COMMANDS or command.arguments[0] in session.plugins.command_names() for command in job.commands):
            print_error("pyesh: built-ins cannot run in pipelines or the background")
            status = 1
            continue
        status = run_pipeline(job.commands, background=job.background, verbose=session.verbose, jobs=session.jobs, cwd=session.cwd, environment=session.environment, pipefail=session.pipefail)
        if job.background and session.jobs.jobs:
            latest = session.jobs.jobs[max(session.jobs.jobs)]
            session.last_background_pid = latest.pgid or latest.processes[0].pid
    return status

def run_shell(
    input_fn: Callable[[str], str] = input,
    config: Optional[ShellConfig] = None,
    history: Optional[CommandHistory] = None,
    state: Optional[SessionState] = None,
    startup: bool = True,
    login: bool = False,
) -> int:
    """Run an interactive pyesh session until exit or EOF.

    Args:
        input_fn: Prompting function, injectable for alternate UIs.
        config: Optional shell presentation settings.
        history: Optional session history instance.
        state: Optional session state instance.
        startup: Whether to load user files and run startup commands.
        login: Whether to load login profile files.

    Returns:
        The requested exit status, or zero at end-of-file.
    """
    settings = config or ShellConfig()
    command_history = history or CommandHistory(settings.history_limit)
    state = state or SessionState(verbose=settings.verbose, history=command_history)
    state.history = command_history
    if input_fn is input and startup:
        state.jobs.enable_terminal()
    files: Optional[UserFiles] = None
    prompt_template = settings.prompt

    if input_fn is input:
        files = user_files()
        state.welcome_path = files.welcome
        try:
            # Environment and PATH must be ready before startup commands run.
            load_environment(files.environment, state.environment)
            load_search_paths(files.paths, state.environment)
            apply_profile_environment(settings, state.environment)
            if not settings.terminal.colors:
                state.environment.setdefault("NO_COLOR", "1")
            active_venv = _prepare_boot_virtual_environment(state.environment)
            if prompt_template is None:
                prompt_template = load_prompt_template(files.prompt)
            state.welcome_enabled, state.welcome_template = load_welcome_config(files.welcome)
            if settings.welcome_enabled is not None:
                state.welcome_enabled = settings.welcome_enabled
            if settings.welcome_template is not None:
                state.welcome_template = settings.welcome_template
            if settings.plugins_enabled:
                selected_plugins = (settings.plugins if settings.plugins is not None else enabled_plugins(files.plugins))
                state.plugins.load_enabled(selected_plugins)
                for plugin_name, plugin_error in state.plugins.errors.items():
                    print_error("pyesh: plugin {0} failed to load: {1}".format(plugin_name, plugin_error))
            command_history.extend(read_history(files.history, settings.history_limit))
            startup_files = ([files.profile] if login else []) + [files.rc]
            if active_venv is not None:
                startup_files.extend(([active_venv / ".pyesh_profile"] if login else []) + [active_venv / ".pyeshrc"])
            for startup_file in startup_files:
                if startup_file.is_file():
                    try:
                        execute_script(startup_file.read_text(encoding="utf-8"), state, str(startup_file))
                    except ValueError as error:
                        state.last_status = 2
                        print_error("pyesh: startup: {0}".format(error))
                    if state.exit_requested:
                        return state.exit_status
            try:
                execute_script("\n".join(settings.startup_commands), state, "<profile>")
            except ValueError as error:
                state.last_status = 2
                print_error("pyesh: startup: {0}".format(error))
            if state.exit_requested:
                return state.exit_status
        except (OSError, UnicodeError, ValueError) as error:
            print_error("pyesh: could not load user files: {0}".format(error))

    if state.verbose:
        print_startup_python(state.environment)
    if state.welcome_enabled:
        _welcome(["welcome"], state)

    # Alternate frontends remain independent and provide their own input.
    prompt_session = None
    if input_fn is input:
        prompt_session = create_prompt_session(command_history, extra_commands=state.plugins.command_names(), config=settings.terminal, environment=state.environment, cwd=state.cwd)

    status = 0
    def finish_or_warn() -> bool:
        """Apply the interactive job shutdown policy.

        Returns:
            ``True`` when the shell may exit.
        """
        active = state.jobs.active()
        stopped = [job for job in active if job.suspended]
        if stopped and not state.force_exit and not state.exit_warning_shown:
            print_error("pyesh: stopped jobs exist; use exit again or exit --force")
            state.exit_warning_shown = True
            state.exit_requested = False
            return False
        if active:
            survivors = state.jobs.shutdown()
            if survivors:
                print_error("pyesh: {0} job(s) survived shutdown".format(len(survivors)))
        return True
    try:
        while True:
            try:
                try:
                    plain_prompt = build_prompt(directory=state.cwd, template=prompt_template, status=status, environment=state.environment)
                except ValueError as error:
                    print_error("pyesh: prompt: {0}".format(error))
                    prompt_template = None
                    plain_prompt = build_prompt(directory=state.cwd, status=status, environment=state.environment)
                if prompt_session is not None:
                    from .terminal import sync_prompt_history
                    sync_prompt_history(prompt_session, command_history)
                    if prompt_session.completer is not None:
                        prompt_session.completer._cwd = state.cwd
                command = (prompt_session.prompt(formatted_prompt(plain_prompt)) if prompt_session is not None else input_fn(plain_prompt))
                while shell_input_incomplete(command):
                    continuation = prompt_session.prompt("... ") if prompt_session is not None else input_fn("... ")
                    command += "\n" + continuation
                while python_input_incomplete(command):
                    continuation = prompt_session.prompt("... ") if prompt_session is not None else input_fn("... ")
                    command = _append_python_continuation(command, continuation)
                for match in re.finditer(r"<<(-?)(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2", command):
                    strip_tabs, quoted, delimiter = bool(match.group(1)), bool(match.group(2)), match.group(3)
                    body = []
                    while True:
                        heredoc_line = prompt_session.prompt("heredoc> ") if prompt_session is not None else input_fn("heredoc> ")
                        compared = heredoc_line.lstrip("\t") if strip_tabs else heredoc_line
                        if compared == delimiter:
                            break
                        body.append(compared if strip_tabs else heredoc_line)
                    content = "\n".join(body) + "\n"
                    if not quoted:
                        content = expand_arguments([ShellWord((Segment(content, "double"),))], state=state,
                            command_substitute=lambda nested: _command_substitute(nested, state))[0]
                    state.pending_heredocs.append(content.encode("utf-8"))
            except EOFError:
                print()
                if finish_or_warn():
                    return 0
                continue
            except KeyboardInterrupt:
                print()
                status = 130
                continue

            try:
                if "\n" in command or "\r" in command:
                    status = execute_script(command, state, "<paste>", record_history=True)
                else:
                    status = execute_command_line(command, state=state)
            except ValueError as error:
                print_error("pyesh: parse error: {0}".format(error))
                status = 2
                continue
            except KeyboardInterrupt:
                print()
                status = 130
                continue
            if state.exit_requested:
                if finish_or_warn():
                    return state.exit_status
    finally:
        if files is not None:
            try:
                write_history(files.history, command_history.entries())
            except (OSError, UnicodeError) as error:
                print_error("pyesh: could not save history: {0}".format(error))
