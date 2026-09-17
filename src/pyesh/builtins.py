# builtins.py

import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import sys
from typing import List, Optional

from .console import print_error
from .help import show_help, show_manual

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def _where(command: str, state=None) -> List[str]:
    """Find executable matches in session PATH order.

    Args:
        command: Command name or explicit path.
        state: Optional active shell session.

    Returns:
        Unique executable paths.
    """
    path = (state.environment.get("PATH", "") if state is not None else None)
    if os.path.dirname(command):
        discovered = shutil.which(command, path=path)
        return [discovered] if discovered is not None else []
    matches = []
    seen = set()
    for directory in os.get_exec_path(state.environment if state is not None else None):
        discovered = shutil.which(command, path=directory)
        if discovered is not None:
            normalized = os.path.normcase(os.path.abspath(discovered))
            if normalized not in seen:
                matches.append(discovered)
                seen.add(normalized)
    return matches

def _change_directory(destination: str, state) -> None:
    """Change the isolated session directory.

    Args:
        destination: Absolute or session-relative directory.
        state: Active shell session.

    Returns:
        None.
    """
    previous = str(state.cwd)
    candidate = Path(os.path.expanduser(destination))
    if not candidate.is_absolute():
        candidate = state.cwd / candidate
    candidate = candidate.resolve(strict=True)
    if not candidate.is_dir():
        raise NotADirectoryError(str(candidate))
    state.cwd = candidate
    state.previous_directory = previous
    state.environment["OLDPWD"] = previous
    state.environment["PWD"] = str(state.cwd)

def _directory_command(name, args, state):
    """Run a directory-state built-in.

    Args:
        name: Built-in command name.
        args: Command arguments.
        state: Active shell session.

    Returns:
        Zero on success.
    """
    if name == "pwd":
        if args:
            raise ValueError("no arguments expected")
        print(state.cwd)
    elif name == "cd":
        if len(args) > 1:
            raise ValueError("expected at most one directory")
        target = args[0] if args else state.environment.get("HOME", str(Path.home()))
        if target == "-":
            if state.previous_directory is None:
                raise ValueError("previous directory is not set")
            target = state.previous_directory
        _change_directory(target, state)
        if args == ["-"]:
            print(state.cwd)
    elif name == "dirs":
        if args:
            raise ValueError("no arguments expected")
        print(shlex.join([str(state.cwd)] + list(reversed(state.directory_stack))))
    elif name == "pushd":
        if len(args) > 1:
            raise ValueError("expected at most one directory")
        if not args and not state.directory_stack:
            raise ValueError("directory stack is empty")
        previous = str(state.cwd)
        target = args[0] if args else state.directory_stack[-1]
        _change_directory(target, state)
        if not args:
            state.directory_stack.pop()
        state.directory_stack.append(previous)
        _directory_command("dirs", [], state)
    else:
        if args:
            raise ValueError("no arguments expected")
        if not state.directory_stack:
            raise ValueError("directory stack is empty")
        _change_directory(state.directory_stack[-1], state)
        state.directory_stack.pop()
        _directory_command("dirs", [], state)
    return 0

def _environment(name, args, state):
    """Run ``export`` or ``unset`` against session state.

    Args:
        name: Built-in command name.
        args: Variable operands.
        state: Active shell session.

    Returns:
        Zero on success.
    """
    if name == "export" and not args:
        for key in sorted(state.environment):
            print("export {0}={1}".format(key, shlex.quote(state.environment[key])))
        return 0
    if not args:
        raise ValueError("expected a variable name")
    # Validate the entire request before changing process-wide environment state.
    for argument in args:
        key = argument.split("=", 1)[0] if name == "export" else argument
        if not _NAME.fullmatch(key) or "\0" in argument:
            raise ValueError("invalid environment variable: {0}".format(key))
    for argument in args:
        if name == "unset":
            state.environment.pop(argument, None)
            state.python.namespace.pop(argument, None)
        else:
            key, separator, value = argument.partition("=")
            if separator:
                state.environment[key] = value
                state.python.namespace[key] = value
            elif key in state.python.namespace:
                state.environment[key] = "" if state.python.namespace[key] is None else str(state.python.namespace[key])
            else:
                state.environment[key] = state.environment.get(key, "")
    return 0

def _aliases(name, args, state):
    """Define, remove, or display aliases.

    Args:
        name: ``alias`` or ``unalias``.
        args: Alias operands.
        state: Active shell session.

    Returns:
        Command status.
    """
    if name == "unalias":
        if args == ["-a"]:
            state.aliases.clear()
            return 0
        if not args:
            raise ValueError("expected an alias name or -a")
        status = 0
        for key in args:
            if key not in state.aliases:
                print_error("pyesh: unalias: no such alias: {0}".format(key))
                status = 1
            else:
                del state.aliases[key]
        return status
    if not args:
        args = sorted(state.aliases)
    from .parsing import parse_command_line
    for argument in args:
        key, separator, value = argument.partition("=")
        if separator:
            if not _NAME.fullmatch(key):
                raise ValueError("invalid alias name: {0}".format(key))
            jobs = parse_command_line(value)
            if (len(jobs) != 1 or len(jobs[0].commands) != 1 or jobs[0].background
                    or jobs[0].commands[0].input_path is not None
                    or jobs[0].commands[0].redirections):
                raise ValueError("alias value must be a single command with arguments")
            state.aliases[key] = value
        elif key in state.aliases:
            print("alias {0}={1}".format(key, shlex.quote(state.aliases[key])))
        else:
            raise ValueError("no such alias: {0}".format(key))
    return 0

def describe_commands(args, state, all_matches=False, terse=False):
    """Describe command resolution.

    Args:
        args: Command names.
        state: Active shell session.
        all_matches: Display every match when true.
        terse: Display only resolvable names or paths.

    Returns:
        Zero when every command resolves, otherwise one.
    """
    from .plugins import CORE_COMMANDS
    if not args:
        raise ValueError("expected a command name")
    status = 0
    for name in args:
        descriptions = []
        if name in state.aliases:
            descriptions.append("{0}: alias for {1}".format(name, state.aliases[name]))
        if name in CORE_COMMANDS:
            descriptions.append("{0}: pyesh built-in command".format(name))
        if name in state.plugins.command_names():
            descriptions.append("{0}: pyesh plugin command".format(name))
        paths = _where(name, state)
        descriptions.extend(paths)
        if not descriptions:
            print_error("pyesh: {0} not found".format(name))
            status = 1
        elif terse:
            print(paths[0] if descriptions[0] in paths else name)
        else:
            for description in descriptions if all_matches else descriptions[:1]:
                print(description)
    return status

def _escapes(text):
    """Decode the supported portable backslash escapes.

    Args:
        text: Input text.

    Returns:
        Decoded text.
    """
    mapping = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\\": "\\"}
    def substitute(match):
        """Decode one matched escape.

        Args:
            match: Regular-expression match.

        Returns:
            Decoded character sequence.
        """
        value = match.group(1)
        if value.startswith("0"):
            return chr(int(value[1:] or "0", 8))
        if value.startswith("x"):
            return chr(int(value[1:], 16))
        return mapping[value] if value in mapping else "\\" + value
    return re.sub(r"\\(0[0-7]{0,3}|x[0-9a-fA-F]{1,2}|.)", substitute, text)

def _printf(args):
    """Implement the portable ``printf`` subset.

    Args:
        args: Format and value arguments.

    Returns:
        Zero on success.
    """
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        raise ValueError("expected a format")
    template, values = _escapes(args[0]), args[1:]
    pattern = re.compile(r"%([-+ #0]*\d*(?:\.\d+)?)([sbdif%])")
    index = 0
    output = []
    while True:
        cursor = 0
        consumed = False
        for match in pattern.finditer(template):
            literal = template[cursor:match.start()]
            if "%" in literal:
                raise ValueError("unsupported printf format")
            output.append(literal)
            flags, kind = match.groups()
            if kind == "%":
                if flags:
                    raise ValueError("invalid percent format")
                output.append("%")
            else:
                consumed = True
                value = values[index] if index < len(values) else ""
                index += 1
                if kind in "di":
                    value = int(value or "0", 16 if value.lower().startswith(("0x", "-0x", "+0x")) else 10)
                elif kind == "f":
                    value = float(value or "0")
                elif kind == "b":
                    value = _escapes(value)
                    kind = "s"
                output.append(("%" + flags + kind) % value)
            cursor = match.end()
        if "%" in template[cursor:]:
            raise ValueError("unsupported printf format")
        output.append(template[cursor:])
        if not consumed or index >= len(values):
            break
    sys.stdout.write("".join(output))
    return 0

def _read(args, state):
    """Read one logical line into session variables.

    Args:
        args: Optional flags and variable names.
        state: Active shell session.

    Returns:
        Zero for a terminated line, otherwise one at EOF.
    """
    raw = False
    if args and args[0] == "-r":
        raw, args = True, args[1:]
    if not args:
        args = ["REPLY"]
    if any(not _NAME.fullmatch(name) or name.startswith("__") for name in args):
        raise ValueError("expected Python variable names (excluding __ names)")
    line = sys.stdin.readline()
    if not line:
        return 1
    terminated = line.endswith("\n")
    while not raw and line.endswith("\\\n"):
        line = line[:-2] + sys.stdin.readline()
        terminated = line.endswith("\n")
    line = line[:-1] if terminated else line
    if not raw:
        line = re.sub(r"\\(.)", r"\1", line)
    values = [line] if args == ["REPLY"] else line.split(None, len(args) - 1)
    for index, name in enumerate(args):
        state.python.namespace[name] = values[index] if index < len(values) else ""
    return 0 if terminated else 1

def _job_command(name, args, state):
    """Run a job-control built-in.

    Args:
        name: Job-control command name.
        args: Command operands.
        state: Active shell session.

    Returns:
        Command status.
    """
    if name == "jobs":
        if args:
            raise ValueError("no arguments expected")
        for line in state.jobs.listing():
            print(line)
        return 0
    if name == "wait":
        return state.jobs.wait_for(args)
    if name in ("fg", "bg"):
        if len(args) > 1:
            raise ValueError("expected at most one job ID")
        job = state.jobs.select(args[0] if args else None)
        if name == "fg":
            return state.jobs.foreground(job)
        if os.name != "posix":
            raise ValueError("resuming stopped jobs is only supported on POSIX")
        job.send(signal.SIGCONT)
        return 0
    if args == ["-l"]:
        print(" ".join(item.name[3:] for item in signal.Signals))
        return 0
    signum = signal.SIGTERM
    if args and args[0] == "-s":
        if len(args) < 3:
            raise ValueError("expected -s SIGNAL TARGET")
        specification, args = args[1], args[2:]
    elif args and args[0].startswith("-") and args[0] != "--":
        specification, args = args[0][1:], args[1:]
    else:
        specification = "TERM"
    try:
        signum = int(specification) if specification.isdigit() else int(
            getattr(signal, "SIG" + specification.upper().removeprefix("SIG")))
    except (AttributeError, ValueError):
        raise ValueError("unknown signal: {0}".format(specification)) from None
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        raise ValueError("expected a PID or %JOB")
    status = 0
    for target in args:
        try:
            if target.startswith("%"):
                state.jobs.select(target).send(signum)
            else:
                pid = int(target)
                if pid <= 0:
                    raise ValueError("PID must be positive; use %JOB for a process group")
                os.kill(pid, signum)
        except (OSError, ValueError) as error:
            print_error("pyesh: kill: {0}: {1}".format(target, error))
            status = 1
    return status

def run_builtin(arguments: List[str], state=None) -> Optional[int]:
    """Run a core built-in when one matches.

    Args:
        arguments: Built-in name followed by arguments.
        state: Optional active shell session.

    Returns:
        Integer status, or ``None`` for an external command.
    """
    if state is None:
        from .shell import SessionState
        state = SessionState()
    if not arguments:
        return 0
    name, args = arguments[0], arguments[1:]
    try:
        if name == "help":
            return show_help(args)
        if name == "man":
            return show_manual(args)
        if name in ("pwd", "cd", "pushd", "popd", "dirs"):
            return _directory_command(name, args, state)
        if name in ("where", "type"):
            all_matches = name == "where" or bool(args and args[0] == "-a")
            return describe_commands(args[1:] if args and args[0] == "-a" else args,
                                     state, all_matches=all_matches)
        if name == "exit":
            force = bool(args and args[0] == "--force")
            args = args[1:] if force else args
            if len(args) > 1:
                raise ValueError("expected [--force] [status]")
            state.exit_status = (int(args[0], 10) % 256) if args else state.last_status
            state.force_exit = force
            state.exit_requested = True
            return state.exit_status
        if name in ("export", "unset"):
            return _environment(name, args, state)
        if name == "shift":
            if len(args) > 1 or (args and not args[0].isdigit()):
                raise ValueError("expected an optional non-negative count")
            count = int(args[0]) if args else 1
            if count > len(state.argv):
                return 1
            del state.argv[:count]
            return 0
        if name == "set":
            if args == ["-o", "pipefail"]: state.pipefail = True
            elif args == ["+o", "pipefail"]: state.pipefail = False
            else: raise ValueError("expected -o pipefail or +o pipefail")
            return 0
        if name in ("alias", "unalias"):
            return _aliases(name, args, state)
        if name == "history":
            if args == ["-c"]:
                state.history.clear()
                return 0
            if len(args) > 1 or (args and (not args[0].isdigit())):
                raise ValueError("expected an optional count or -c")
            entries = state.history.entries()
            start = max(0, len(entries) - int(args[0])) if args else 0
            for index in range(start, len(entries)):
                print("{0:5}  {1}".format(index + 1, entries[index]))
            return 0
        if name == "echo":
            newline = not (args and args[0] == "-n")
            print(" ".join(args if newline else args[1:]), end="\n" if newline else "")
            return 0
        if name == "printf":
            return _printf(args)
        if name == "read":
            return _read(args, state)
        if name == "disown":
            state.jobs.disown(args)
            return 0
        if name == "exec":
            if not args: raise ValueError("expected a command")
            from .backends import prepare_command
            prepared = prepare_command(args, state.environment)
            if os.name == "posix":
                os.chdir(str(state.cwd))
                os.execvpe(prepared[0], prepared, state.environment)
            import subprocess
            status = subprocess.run(prepared, cwd=str(state.cwd), env=state.environment).returncode
            state.exit_requested, state.exit_status = True, status
            return status
        if name in ("jobs", "wait", "fg", "bg", "kill"):
            return _job_command(name, args, state)
    except (ValueError, TypeError) as error:
        print_error("pyesh: {0}: {1}".format(name, error))
        return 2
    except OSError as error:
        print_error("pyesh: {0}: {1}".format(name, error))
        return 1
    return None
