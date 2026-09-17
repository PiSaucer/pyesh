# api.py

from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence
from .execution import run_pipeline
from .parsing import Command
from .shell import SessionState, execute_command_line, execute_script

class PyeshSession:
    """A reusable command-execution session for Python applications.

    The session preserves controls changed by built-ins, such as verbose mode,
    across calls. Commands use the hosting Python process's working directory,
    environment, and standard streams.
    """
    def __init__(self, verbose: bool = False, plugins: Optional[Iterable[str]] = None) -> None:
        """Create an automation session.

        Args:
            verbose: Whether to trace resolved built-ins and process launches.
            plugins: Installed plugin entry-point names to load explicitly.
        """
        self._state = SessionState(verbose=verbose)
        if plugins is not None:
            self._state.plugins.load_enabled(plugins)

    @property
    def plugin_errors(self) -> Mapping[str, str]:
        """Return plugin loading failures keyed by plugin name.

        Returns:
            A copy of loading error messages.
        """
        return self._state.plugins.errors

    @property
    def verbose(self) -> bool:
        """Return whether execution tracing is enabled.

        Returns:
            The current verbose setting.
        """
        return self._state.verbose

    @property
    def exit_requested(self) -> bool:
        """Return whether the session received the ``exit`` built-in.

        Returns:
            ``True`` after an exit request.
        """
        return self._state.exit_requested

    @property
    def exit_status(self) -> int:
        """Return the status retained by an explicit exit request.

        Returns:
            The normalized process exit status.
        """
        return self._state.exit_status

    @property
    def cwd(self) -> Path:
        """Return the session working directory.

        Returns:
            The absolute session working directory.
        """
        return self._state.cwd

    @property
    def environment(self) -> Mapping[str, str]:
        """Return a copy of the session child environment.

        Returns:
            Environment variables keyed by name.
        """
        return dict(self._state.environment)

    @property
    def variables(self) -> Mapping[str, object]:
        """Return a copy of user-visible session variables.

        Returns:
            Python-backed values keyed by variable name.
        """
        return {key: value for key, value in self._state.python.namespace.items()
                if not key.startswith("__") and key not in ("sh", "capture", "env", "argv")}

    def set_cwd(self, path) -> None:
        """Set the isolated session working directory.

        Args:
            path: Existing directory to use.

        Returns:
            None.
        """
        candidate = Path(path).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            raise NotADirectoryError(str(candidate))
        self._state.cwd = candidate
        self._state.environment["PWD"] = str(candidate)

    def set_environment(self, name: str, value: Optional[str]) -> None:
        """Set or remove one session environment variable.

        Args:
            name: Environment variable name.
            value: String value, or ``None`` to remove the name.

        Returns:
            None.
        """
        if value is None:
            self._state.environment.pop(name, None)
        else:
            self._state.environment[name] = str(value)

    def run(self, command_line: str) -> int:
        """Execute one pyesh command line.

        Args:
            command_line: Commands and supported pyesh operators to execute.

        Returns:
            The final executed job's exit status. The ``exit`` built-in returns
            the requested status and sets ``exit_requested``.

        Raises:
            ValueError: If the command line has invalid syntax.
        """
        if self._state.exit_requested:
            return self._state.exit_status
        return execute_command_line(command_line, state=self._state)

    def run_all(self, command_lines: Iterable[str], stop_on_error: bool = False) -> int:
        """Execute command lines in order.

        Args:
            command_lines: Command lines to execute.
            stop_on_error: Stop after the first nonzero status when true.

        Returns:
            The final executed status, or zero for an empty iterable. Execution
            also stops when a command requests session exit.

        Raises:
            ValueError: If any command line has invalid syntax.
        """
        status = 0
        for command_line in command_lines:
            status = self.run(command_line)
            if self.exit_requested or (stop_on_error and status != 0):
                break
        return status

    def run_script(self, source: str, filename: str = "<string>", argv: Iterable[str] = ()) -> int:
        """Execute native pyesh source in this session.

        Args:
            source: Complete pyesh source text.
            filename: Diagnostic name and ``$0`` value.
            argv: Positional arguments exposed through ``argv`` and ``$1`` onward.

        Returns:
            The final command or explicit exit status.
        """
        self._state.argv0 = filename
        self._state.argv[:] = list(argv)
        return execute_script(source, self._state, filename)

    def run_file(self, path, argv: Iterable[str] = ()) -> int:
        """Read and execute a UTF-8 pyesh script.

        Args:
            path: Script path.
            argv: Positional script arguments.

        Returns:
            The final command or explicit exit status.
        """
        source_path = Path(path).expanduser().resolve(strict=True)
        return self.run_script(source_path.read_text(encoding="utf-8"), str(source_path), argv)

    def run_argv(self, arguments: Sequence[str]) -> int:
        """Execute an argument vector without parsing shell syntax.

        Args:
            arguments: Program followed by literal arguments.

        Returns:
            The child process exit status.
        """
        if not arguments:
            return 0
        status = run_pipeline([Command(arguments=list(arguments))], jobs=self._state.jobs,
                              cwd=self._state.cwd, environment=self._state.environment,
                              verbose=self._state.verbose, pipefail=self._state.pipefail)
        self._state.last_status = status
        return status

    def close(self) -> None:
        """Hang up jobs still managed by this session.

        Returns:
            None.
        """
        self._state.jobs.shutdown()

    def __enter__(self):
        """Enter a managed session context.

        Returns:
            This session.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Close the session when leaving a managed context.

        Args:
            exc_type: Active exception type, when present.
            exc_value: Active exception value, when present.
            traceback: Active exception traceback, when present.

        Returns:
            None.
        """
        self.close()

def run_command(command_line: str, verbose: bool = False) -> int:
    """Execute one command line in a new pyesh automation session.

    Args:
        command_line: Commands and supported pyesh operators to execute.
        verbose: Whether to trace resolved execution.

    Returns:
        The final command status.

    Raises:
        ValueError: If the command line has invalid syntax.
    """
    return PyeshSession(verbose=verbose).run(command_line)
