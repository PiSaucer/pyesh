# prompt.py

import getpass
import os
import socket
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

DEFAULT_PROMPT_TEMPLATE = (
    "{platform_icon} {venv_segment}{user}@{host} "
    "{folder}{branch_segment} % "
)

PLATFORM_ICONS = {
    "darwin": "",
    "linux": "🐧",
    "steamos": "",
    "ubuntu": "",
    "win32": "",
}

@lru_cache(maxsize=1)
def _current_platform_name() -> str:
    """Return the platform name, including recognized Linux distributions."""
    if sys.platform != "linux":
        return sys.platform
    try:
        release = Path("/etc/os-release").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return sys.platform
    for line in release.splitlines():
        key, separator, value = line.partition("=")
        distribution = value.strip().strip("\"'")
        if separator and key == "ID" and distribution in PLATFORM_ICONS:
            return distribution
    return sys.platform

def platform_icon(platform_name: Optional[str] = None) -> str:
    """Return the prompt icon for the current operating system."""
    name = _current_platform_name() if platform_name is None else platform_name
    return PLATFORM_ICONS.get(name, "◇")

def git_branch(directory: Path) -> Optional[str]:
    """Find the current Git branch without invoking a command shell.

    Args:
        directory: Working directory whose repository should be inspected.

    Returns:
        The branch name, a short detached-HEAD identifier, or ``None`` when the
        directory is not in a Git work tree or Git is unavailable.
    """
    commands = (
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        ["git", "rev-parse", "--short", "HEAD"],
    )
    for command in commands:
        try:
            result = subprocess.run(
                command,
                cwd=str(directory),
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError:
            return None
        branch = result.stdout.strip()
        if result.returncode == 0 and branch:
            return branch
    return None

def folder_name(directory: Path) -> str:
    """Create the compact folder component used in the prompt.

    Args:
        directory: Current working directory.

    Returns:
        ``~`` for the user's home directory, the final directory name, or the
        full anchor for a filesystem root.
    """
    if directory == Path.home():
        return "~"
    return directory.name or str(directory)

def build_prompt(
    directory: Optional[Path] = None,
    template: Optional[str] = None,
    status: int = 0,
    environment=None,
) -> str:
    """Build a shell-style prompt for the current session state.

    Args:
        directory: Directory to display and inspect. Defaults to the process
            working directory.
        template: Optional format string. Supported fields are ``user``,
            ``host``, ``folder``, ``path``, ``branch``, ``branch_segment``,
            ``status``, ``venv``, ``venv_segment``, and ``platform_icon``.
        status: Exit status of the previously executed command.
        environment: Optional environment mapping. Defaults to None.

    Returns:
        Prompt text in ``icon user@machine folder (branch) % `` form. The
        branch section is omitted outside a Git repository.
    """
    current = directory or Path.cwd()
    active_environment = os.environ if environment is None else environment
    user = getpass.getuser()
    machine = socket.gethostname().split(".", 1)[0]
    branch = git_branch(current)
    values = {
        "user": user,
        "host": machine,
        "folder": folder_name(current),
        "path": str(current),
        "branch": branch or "",
        "branch_segment": " ({0})".format(branch) if branch else "",
        "status": status,
        "platform_icon": platform_icon(),
        "venv": Path(active_environment["VIRTUAL_ENV"]).name
        if active_environment.get("VIRTUAL_ENV")
        else "",
        "venv_segment": "({0}) ".format(Path(active_environment["VIRTUAL_ENV"]).name)
        if active_environment.get("VIRTUAL_ENV")
        else "",
    }
    try:
        rendered = (template or DEFAULT_PROMPT_TEMPLATE).format(**values)
    except (KeyError, ValueError) as error:
        raise ValueError("invalid prompt template: {0}".format(error)) from error
    return rendered if rendered.endswith(" ") else rendered + " "
