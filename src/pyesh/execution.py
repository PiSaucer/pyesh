# execution.py

import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
from typing import IO, List, Optional, Tuple

from .backends import RuntimeUnavailableError, is_explicit_path, prepare_command
from .console import print_error, print_execution_trace
from .parsing import Command
from .jobs import JobTable

def split_command(command: str) -> List[str]:
    """Split one command line without invoking a system shell.

    Args:
        command: Raw command text entered by the user.

    Returns:
        Parsed arguments suitable for direct subprocess execution.

    Raises:
        ValueError: If quoting or escaping is incomplete.
    """
    return shlex.split(command, posix=os.name != "nt")

def _prepare(arguments, cwd=None, environment=None):
    """Resolve explicit paths and script runtimes.

    Args:
        arguments: Command argument vector.
        cwd: Optional session directory.
        environment: Optional session environment.

    Returns:
        Prepared subprocess arguments.
    """
    values = list(arguments)
    if values and cwd is not None and is_explicit_path(values[0]) and not os.path.isabs(values[0]):
        values[0] = str(Path(cwd) / values[0])
    return prepare_command(values, environment)

def _normalize_status(code: int) -> int:
    """Convert raw return code into a standard shell exit status.

    Args:
        code: Process return code from Python subprocess.

    Returns:
        Standard status code. Signals (negative codes) become 128 + abs(code).
    """
    if code < 0:
        return 128 + abs(code)
    return code

def run_external(arguments: List[str], verbose: bool = False) -> int:
    """Run an external program directly without a system shell.

    Args:
        arguments: Program name followed by its arguments.
        verbose: Whether to print the resolved process argument vector.

    Returns:
        The program exit status, 127 when it cannot be found, or 126 when the
        operating system cannot start it for another reason.
    """
    if not arguments:
        return 0
    try:
        prepared = prepare_command(arguments)
        if verbose:
            print_execution_trace(prepared)
        completed = subprocess.run(prepared, check=False)
    except KeyboardInterrupt:
        return 130
    except RuntimeUnavailableError as error:
        print_error("pyesh: {0}".format(error))
        return 127
    except FileNotFoundError:
        print_error("pyesh: command not found: {0}".format(arguments[0]))
        return 127
    except OSError as error:
        print_error("pyesh: could not run {0}: {1}".format(arguments[0], error))
        return 126
    return _normalize_status(completed.returncode)

def _child_environment(environment=None) -> dict:
    """Create an environment encouraging terminal-aware program colors.

    Args:
        environment: Optional source environment.

    Returns:
        A copy of the current environment. For an interactive terminal it sets
        ``CLICOLOR``, which is honored by tools including macOS/BSD ``ls``.
    """
    environment = dict(os.environ if environment is None else environment)
    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        environment.setdefault("CLICOLOR", "1")
    return environment

def _wait_for_processes(processes: List[subprocess.Popen]) -> bool:
    """Reap a collection of child processes.

    Args:
        processes: Processes belonging to one pipeline.

    Returns:
        True if waiting was interrupted by KeyboardInterrupt, False otherwise.
    """
    interrupted = False
    for process in processes:
        while True:
            try:
                process.wait()
                break
            except KeyboardInterrupt:
                interrupted = True
    return interrupted

def _redirect_streams(command, standard_output, opened_files):
    """Resolve output destinations in lexical order.

    Args:
        command: Parsed command containing redirections.
        standard_output: Initial stdout destination.
        opened_files: Collection retaining opened streams.

    Returns:
        Resolved stdout and stderr destinations.
    """
    standard_error = None
    redirects = command.redirections
    if not redirects and command.output_path is not None:
        redirects = [(">>" if command.append_output else ">", command.output_path)]
    for operator, path in redirects:
        if operator == "2>&1":
            standard_error = (1 if standard_output is None else subprocess.STDOUT if standard_output == subprocess.PIPE else standard_output)
            continue
        if operator == "1>&2":
            standard_output = 2
            continue
        if operator == "1>&-":
            standard_output = subprocess.DEVNULL
            continue
        if operator == "2>&-":
            standard_error = subprocess.DEVNULL
            continue
        stream = open(path, "ab" if operator in (">>", "2>>") else "wb")
        opened_files.append(stream)
        if operator in (">", ">>", "&>"):
            standard_output = stream
        if operator in ("2>", "2>>", "&>"):
            standard_error = stream
    return standard_output, standard_error

def _start_grouped(arguments, group, **kwargs):
    """Start a subprocess in a POSIX process group.

    Args:
        arguments: Child argument vector.
        group: Process-group ID, or zero for a new group.
        **kwargs: Additional ``Popen`` options.

    Returns:
        The started subprocess.
    """
    if sys.version_info >= (3, 11):
        return subprocess.Popen(arguments, process_group=group, **kwargs)
    read_fd, write_fd = os.pipe()
    process = None
    try:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("_job_child.py")),
             str(group), str(write_fd)] + arguments,
            pass_fds=(write_fd,), **kwargs
        )
        os.close(write_fd)
        write_fd = None
        error = os.read(read_fd, 100)
        if error:
            process.wait()
            code = int(error)
            raise OSError(code, os.strerror(code), arguments[0])
        return process
    finally:
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)

def _abort_pipeline(processes, pgid=None):
    """Terminate processes after a partial pipeline launch.

    Args:
        processes: Children already started.
        pgid: Optional POSIX process-group ID.

    Returns:
        None.
    """
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for process in processes:
        try:
            process.kill()
        except OSError:
            pass
    _wait_for_processes(processes)

def run_pipeline(
    commands: List[Command],
    background: bool = False,
    verbose: bool = False,
    input_data: Optional[bytes] = None,
    jobs: Optional[JobTable] = None,
    cwd=None,
    environment=None,
    pipefail: bool = False,
) -> int:
    """Execute commands connected by operating-system pipes.

    Args:
        commands: Parsed commands in pipeline order.
        background: Whether to return without waiting for completion.
        verbose: Whether to trace each resolved process before it starts.
        input_data: Optional bytes supplied as the first command's stdin.

    Returns:
        Zero after a background launch, otherwise the final command's status.
        Returns 126 or 127 when startup fails.
    """
    processes: List[subprocess.Popen] = []
    opened_files: List[IO[bytes]] = []
    previous_output = None
    interrupted = False
    pgid = None
    input_file = tempfile.TemporaryFile() if input_data is not None else None
    if input_file is not None:
        input_file.write(input_data)
        input_file.seek(0)

    try:
        for index, command in enumerate(commands):
            standard_input = (
                input_file if index == 0 and input_file is not None else previous_output
            )
            if command.input_path is not None:
                standard_input = open(command.input_path, "rb")
                opened_files.append(standard_input)
            if command.heredoc_data is not None:
                heredoc = tempfile.TemporaryFile()
                heredoc.write(command.heredoc_data)
                heredoc.seek(0)
                opened_files.append(heredoc)
                standard_input = heredoc
            if any(operator == "0>&-" for operator, _ in command.redirections):
                standard_input = subprocess.DEVNULL

            standard_output = subprocess.PIPE if index < len(commands) - 1 else None
            standard_output, standard_error = _redirect_streams(
                command, standard_output, opened_files
            )
            if (background and index == 0 and standard_input is None
                    and (jobs is None or jobs.terminal_fd is None)):
                standard_input = subprocess.DEVNULL

            prepared_arguments = _prepare(command.arguments, cwd, environment)
            if verbose:
                print_execution_trace(prepared_arguments)
            process_options = dict(
                stdin=standard_input, stdout=standard_output, stderr=standard_error,
                env=_child_environment(environment), cwd=cwd,
            )
            if jobs is not None and os.name == "posix":
                process = _start_grouped(prepared_arguments, pgid or 0, **process_options)
                pgid = pgid or process.pid
            else:
                if jobs is not None and background and os.name == "nt":
                    process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                process = subprocess.Popen(prepared_arguments, **process_options)
            processes.append(process)
            if previous_output is not None:
                previous_output.close()
            previous_output = process.stdout
    except KeyboardInterrupt:
        interrupted = True
    except RuntimeUnavailableError as error:
        print_error("pyesh: {0}".format(error))
        if previous_output is not None:
            previous_output.close()
        _abort_pipeline(processes, pgid)
        return 127
    except FileNotFoundError as error:
        command_name = commands[len(processes)].arguments[0]
        redirection_failed = bool(error.filename and error.filename != command_name)
        if redirection_failed:
            print_error("pyesh: could not open {0}: {1}".format(error.filename, error))
        else:
            print_error("pyesh: command not found: {0}".format(command_name))
        if previous_output is not None:
            previous_output.close()
        _abort_pipeline(processes, pgid)
        return 1 if redirection_failed else 127
    except OSError as error:
        name = commands[len(processes)].arguments[0]
        print_error("pyesh: could not run {0}: {1}".format(name, error))
        if previous_output is not None:
            previous_output.close()
        _abort_pipeline(processes, pgid)
        return 126
    finally:
        if input_file is not None:
            input_file.close()
        for opened_file in opened_files:
            opened_file.close()

    if interrupted:
        _abort_pipeline(processes, pgid)
        return 130
    if jobs is not None and processes:
        text = " | ".join(shlex.join(command.arguments) for command in commands)
        job = jobs.track(processes, text, pgid=pgid, background=background)
        if background:
            if jobs.terminal_fd is not None:
                print("[{0}] {1}".format(job.number, processes[0].pid))
            return 0
        status = jobs.foreground(job)
        if pipefail:
            failures = [_normalize_status(p.returncode or 0) for p in processes if p.returncode]
            return failures[-1] if failures else status
        return status
    if background:
        # A small daemon waiter prevents completed background children from
        # remaining as zombies while allowing the prompt to return immediately.
        threading.Thread(
            target=_wait_for_processes, args=(processes,), daemon=True
        ).start()
        return 0
    if _wait_for_processes(processes) or interrupted:
        return 130
    statuses = [_normalize_status(process.returncode or 0) for process in processes]
    return next((code for code in reversed(statuses) if code), statuses[-1] if statuses else 0) if pipefail else (statuses[-1] if statuses else 0)

def run_pipeline_captured(
    commands: List[Command],
    input_data: Optional[bytes] = None,
    verbose: bool = False,
    cwd=None,
    environment=None,
    pipefail: bool = False,
) -> Tuple[int, bytes]:
    """Execute a foreground pipeline while capturing its final stdout.

    Args:
        commands: Real external commands in pipeline order.
        input_data: Optional bytes supplied as the first command's stdin.
        verbose: Whether to trace each resolved process before launch.
        cwd: Optional session working directory.
        environment: Optional session environment.
        pipefail: Whether to return a non-zero status if any command fails.

    Returns:
        ``(status, output_bytes)`` for the final command. Startup failures
        return their normal status and empty output.
    """
    processes: List[subprocess.Popen] = []
    opened_files: List[IO[bytes]] = []
    previous_output = None
    input_file = tempfile.TemporaryFile() if input_data is not None else None
    if input_file is not None:
        input_file.write(input_data)
        input_file.seek(0)

    try:
        for index, command in enumerate(commands):
            standard_input = (
                input_file if index == 0 and input_file is not None else previous_output
            )
            if command.input_path is not None:
                standard_input = open(command.input_path, "rb")
                opened_files.append(standard_input)
            if command.heredoc_data is not None:
                heredoc = tempfile.TemporaryFile()
                heredoc.write(command.heredoc_data)
                heredoc.seek(0)
                opened_files.append(heredoc)
                standard_input = heredoc
            if any(operator == "0>&-" for operator, _ in command.redirections):
                standard_input = subprocess.DEVNULL
            standard_output = subprocess.PIPE
            standard_output, standard_error = _redirect_streams(
                command, standard_output, opened_files
            )
            prepared_arguments = _prepare(command.arguments, cwd, environment)
            if verbose:
                print_execution_trace(prepared_arguments)
            process = subprocess.Popen(
                prepared_arguments,
                stdin=standard_input,
                stdout=standard_output,
                stderr=standard_error,
                env=_child_environment(environment), cwd=cwd,
            )
            processes.append(process)
            if previous_output is not None:
                previous_output.close()
            previous_output = process.stdout
        output, _ = processes[-1].communicate()
        for process in processes[:-1]:
            try:
                process.wait()
            except KeyboardInterrupt:
                pass
        statuses = [_normalize_status(process.returncode or 0) for process in processes]
        status = next((code for code in reversed(statuses) if code), statuses[-1]) if pipefail else statuses[-1]
        return status, output or b""
    except KeyboardInterrupt:
        _wait_for_processes(processes)
        return 130, b""
    except RuntimeUnavailableError as error:
        print_error("pyesh: {0}".format(error))
        return 127, b""
    except FileNotFoundError as error:
        command_name = commands[len(processes)].arguments[0]
        print_error("pyesh: command not found: {0}".format(command_name))
        return 127, b""
    except OSError as error:
        command_name = commands[len(processes)].arguments[0]
        print_error("pyesh: could not run {0}: {1}".format(command_name, error))
        return 126, b""
    finally:
        if previous_output is not None:
            previous_output.close()
        if input_file is not None:
            input_file.close()
        for opened_file in opened_files:
            opened_file.close()
        for process in processes:
            if process.poll() is None:
                try:
                    process.wait()
                except KeyboardInterrupt:
                    pass
