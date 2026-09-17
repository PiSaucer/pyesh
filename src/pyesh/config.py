# config.py

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple

DEFAULT_TERMINAL_STYLES = {
    "command": "bold #00afff",
    "builtin": "bold #00d7d7",
    "operator": "bold #ff5fff",
    "string": "#5fd75f",
    "variable": "#d787ff",
    "option": "#ffd75f",
    "number": "#5fd7ff",
}

@dataclass(frozen=True)
class TerminalConfig:
    """Interactive line-editor presentation settings."""
    colors: bool = True
    syntax_highlighting: bool = True
    completion: bool = True
    complete_while_typing: bool = False
    mouse_support: bool = False
    styles: Optional[Mapping[str, str]] = None

@dataclass(frozen=True)
class ShellConfig:
    """Settings used by the interactive presentation layer.

    Attributes:
        prompt: Optional fixed prompt. When omitted, pyesh displays the current user, machine, folder, and Git branch.
        history_limit: Maximum commands retained by the session history.
        verbose: Whether to trace resolved process launches before execution.
        plugins_enabled: Whether interactive startup may load enabled plugins.
    """
    prompt: Optional[str] = None
    history_limit: int = 1_000
    verbose: bool = False
    plugins_enabled: bool = True
    plugins: Optional[Tuple[str, ...]] = None
    terminal: TerminalConfig = TerminalConfig()
    welcome_enabled: Optional[bool] = None
    welcome_template: Optional[str] = None
    environment: Tuple[Tuple[str, str], ...] = ()
    paths: Tuple[str, ...] = ()
    startup_commands: Tuple[str, ...] = ()

def default_data_directory() -> Path:
    """Find the platform-appropriate per-user pyesh data directory.

    Returns:
        The data directory path. The directory is not created by this function.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / "pyesh" if base else Path.home() / "pyesh"
    base = os.environ.get("XDG_DATA_HOME")
    return Path(base) / "pyesh" if base else Path.home() / ".local" / "share" / "pyesh"
