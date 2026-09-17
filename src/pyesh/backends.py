# backends.py

import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Iterable, List, Optional

class RuntimeUnavailableError(RuntimeError):
    """Raised when a script requires an interpreter that is not installed."""

def active_virtual_environment(environment=None) -> Optional[Path]:
    """Resolve the virtual environment active for this pyesh process.

    Args:
        environment: Optional session environment mapping.

    Returns:
        The environment root reported by the running interpreter or
        ``VIRTUAL_ENV``, or ``None`` when neither identifies a directory.
    """
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        prefix = Path(sys.prefix)
        if prefix.is_dir():
            return prefix.resolve()
    configured = (os.environ if environment is None else environment).get("VIRTUAL_ENV")
    if configured:
        root = Path(configured).expanduser()
        if root.is_dir():
            return root.resolve()
    return None

def virtual_environment_scripts(root: Path) -> Path:
    """Return the executable directory for a virtual environment.

    Args:
        root: Virtual-environment root.

    Returns:
        ``Scripts`` on Windows or ``bin`` on other platforms.
    """
    return root / ("Scripts" if os.name == "nt" else "bin")

def active_python_executable(environment=None) -> str:
    """Choose the active venv Python, falling back to this interpreter.

    Args:
        environment: Optional session environment mapping.

    Returns:
        Resolved Python executable path.
    """
    root = active_virtual_environment(environment)
    if root is not None:
        scripts = virtual_environment_scripts(root)
        names = (
            ("python.exe", "python")
            if os.name == "nt"
            else ("python", "python3")
        )
        for name in names:
            candidate = scripts / name
            if candidate.is_file() and os.access(str(candidate), os.X_OK):
                # Preserve the venv launcher path instead of resolving its
                # symlink to the base interpreter. Python uses that path to
                # locate the environment's adjacent pyvenv.cfg.
                return str(candidate.absolute())
    return str(Path(sys.executable).resolve())

def is_explicit_path(value: str) -> bool:
    """Determine whether command text explicitly addresses a filesystem path.

    Args:
        value: Command name or path as entered after parsing.

    Returns:
        ``True`` for absolute paths and values containing a platform path
        separator. A bare filename is deliberately not a local path.
    """
    path = Path(value)
    separators = [separator for separator in (os.sep, os.altsep) if separator]
    return path.is_absolute() or any(separator in value for separator in separators)

def _first_executable(candidates: Iterable[Optional[str]], environment=None) -> Optional[str]:
    """Return the first existing executable from candidate names or paths.

    Args:
        candidates: Executable names, absolute paths, or missing values.

    Returns:
        The resolved executable path, or ``None`` when none can be used.
    """
    for candidate in candidates:
        if not candidate:
            continue
        discovered = shutil.which(candidate, path=(environment or os.environ).get("PATH"))
        if discovered:
            return discovered
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(str(path), os.X_OK):
            return str(path)
    return None

def discover_bash(environment=None) -> Optional[str]:
    """Discover Bash, including common Git for Windows installations.

    Args:
        environment: Optional environment used for lookup.

    Returns:
        An executable path, or ``None`` when Bash is unavailable.
    """
    values = os.environ if environment is None else environment
    program_files = values.get("ProgramFiles")
    program_files_x86 = values.get("ProgramFiles(x86)")
    local_app_data = values.get("LOCALAPPDATA")
    return _first_executable(
        [
            "bash",
            str(Path(program_files) / "Git" / "bin" / "bash.exe")
            if program_files
            else None,
            str(Path(program_files_x86) / "Git" / "bin" / "bash.exe")
            if program_files_x86
            else None,
            str(Path(local_app_data) / "Programs" / "Git" / "bin" / "bash.exe")
            if local_app_data
            else None,
        ], values
    )

def discover_powershell(environment=None) -> Optional[str]:
    """Discover PowerShell Core or Windows PowerShell.

    Args:
        environment: Optional environment used for lookup.

    Returns:
        An executable path, preferring cross-platform ``pwsh``, or ``None``.
    """
    values = os.environ if environment is None else environment
    system_root = values.get("SystemRoot")
    windows_powershell = (
        str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        if system_root
        else None
    )
    return _first_executable(["pwsh", "powershell", windows_powershell], values)

def _read_shebang(script: Path) -> Optional[List[str]]:
    """Read an interpreter argument vector from a script's first line.

    Args:
        script: Candidate script path.

    Returns:
        Parsed shebang arguments, or ``None``.
    """
    try:
        with script.open("rb") as source:
            first_line = source.readline(4097)
    except OSError:
        return None
    if not first_line.startswith(b"#!") or len(first_line) > 4096:
        return None
    try:
        return shlex.split(first_line[2:].decode("utf-8").strip(), posix=True) or None
    except (UnicodeDecodeError, ValueError):
        return None

def _known_shebang_command(shebang: List[str], script: Path, environment=None) -> Optional[List[str]]:
    """Prepare a portable command for a recognized shebang interpreter.

    Args:
        shebang: Parsed interpreter and arguments.
        script: Script path.
        environment: Optional lookup environment.

    Returns:
        Prepared argv, or ``None`` for an unknown interpreter.
    """
    interpreter = Path(shebang[0]).name.lower()
    interpreter_arguments = shebang[1:]
    if interpreter in ("env", "env.exe") and len(interpreter_arguments) == 1:
        interpreter = Path(interpreter_arguments[0]).name.lower()
        interpreter_arguments = []

    if interpreter in ("python", "python3", "python.exe", "python3.exe"):
        return [active_python_executable(environment)] + interpreter_arguments + [str(script)]
    if interpreter in ("bash", "bash.exe"):
        bash = discover_bash(environment)
        if bash is None:
            raise RuntimeUnavailableError("Bash is required for {0}; install Bash or Git for Windows".format(script))
        return [bash] + interpreter_arguments + [str(script)]
    if interpreter in ("pwsh", "pwsh.exe", "powershell", "powershell.exe"):
        powershell = discover_powershell(environment)
        if powershell is None:
            raise RuntimeUnavailableError("PowerShell is required for {0}; install pwsh or Windows PowerShell".format(script))
        return [powershell] + interpreter_arguments + [str(script)]
    return None

def prepare_command(arguments: List[str], environment=None) -> List[str]:
    """Select an explicit interpreter for a recognized script file.

    Args:
        arguments: Program or script path followed by arguments.

    Returns:
        A new direct-execution argument list. Non-script commands are returned
        unchanged in a new list.

    Raises:
        RuntimeUnavailableError: If a Bash or PowerShell script is requested
            and its real runtime cannot be discovered.
    """
    if not arguments:
        return []
    script = Path(arguments[0])
    if not is_explicit_path(arguments[0]):
        # Bare names belong to PATH lookup. This prevents an untrusted file in
        # the current directory from silently becoming executable shell input.
        return list(arguments)
    if not script.is_file():
        return list(arguments)

    shebang = _read_shebang(script)
    if shebang is not None:
        prepared = _known_shebang_command(shebang, script, environment)
        if prepared is not None:
            return prepared + arguments[1:]
        return shebang + [str(script)] + arguments[1:]

    suffix = script.suffix.lower()
    if suffix == ".py":
        return [active_python_executable(environment), str(script)] + arguments[1:]
    if suffix == ".sh":
        bash = discover_bash(environment)
        if bash is None:
            raise RuntimeUnavailableError("Bash is required for {0}; install Bash or Git for Windows".format(script))
        return [bash, str(script)] + arguments[1:]
    if suffix == ".ps1":
        powershell = discover_powershell(environment)
        if powershell is None:
            raise RuntimeUnavailableError("PowerShell is required for {0}; install pwsh or Windows PowerShell".format(script))
        return [powershell, "-NoProfile", "-File", str(script)] + arguments[1:]
    return list(arguments)
