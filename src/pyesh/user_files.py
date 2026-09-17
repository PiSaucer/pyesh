# user_files.py

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

_STARTER_CONTENT = {
    ".pyeshenv": "# pyesh environment: one NAME=value assignment per line.\n",
    ".pyesh_paths": "# pyesh PATH additions: one directory per line.\n~/.local/bin\n",
    ".pyesh_profile": "# pyesh session startup commands.\n",
    ".pyeshrc": "# pyesh interactive startup commands.\n# Example: verbose on\n",
    ".pyesh_prompt": (
        "# Prompt fields: {user} {host} {folder} {path} {branch} "
        "{branch_segment} {status} {venv} {venv_segment}\n"
        "{venv_segment}{user}@{host} {folder}{branch_segment} %\n"
    ),
    ".pyesh_welcome": (
        "# enabled=true shows the welcome splash automatically at startup.\n"
        "# Template fields: {version} {python_version} {python_executable} "
        "{platform} {directory} {venv}\n"
        "# Add a multiline template after the enabled setting, or leave it "
        "empty for the built-in splash.\n"
        "enabled=true\n"
    ),
    ".pyesh_plugins": "# Enabled installed plugin entry-point names, one per line.\n",
    ".pyesh_profiles.json": (
        "{\n"
        "  \"version\": 1,\n"
        "  \"default_profile\": \"default\",\n"
        "  \"profiles\": {\n"
        "    \"default\": {}\n"
        "  }\n"
        "}\n"
    ),
    ".pyesh_history": "",
}

@dataclass(frozen=True)
class UserFiles:
    """Resolved paths for pyesh-owned user files.

    Attributes:
        root: Directory containing the user files.
        environment: Environment assignment file.
        paths: Search-path entries file.
        profile: General session startup commands.
        rc: Interactive-session startup commands.
        history: Persistent pyesh-only command history.
        plugins: Explicitly enabled installed plugin names.
        prompt: User-owned prompt format template.
        welcome: Welcome toggle and optional splash template.
    """

    root: Path
    environment: Path
    paths: Path
    profile: Path
    rc: Path
    history: Path
    plugins: Path
    prompt: Path
    welcome: Path
    profiles: Path

def user_files() -> UserFiles:
    """Resolve pyesh user files without creating them.

    ``PYESH_HOME`` provides an explicit override for portable setups,
    and users who do not want files in their operating-system home directory.

    Returns:
        Resolved pyesh user-file paths.
    """
    root = Path(os.environ.get("PYESH_HOME", str(Path.home()))).expanduser()
    return UserFiles(
        root=root,
        environment=root / ".pyeshenv",
        paths=root / ".pyesh_paths",
        profile=root / ".pyesh_profile",
        rc=root / ".pyeshrc",
        history=root / ".pyesh_history",
        plugins=root / ".pyesh_plugins",
        prompt=root / ".pyesh_prompt",
        welcome=root / ".pyesh_welcome",
        profiles=root / ".pyesh_profiles.json",
    )

def initialize_user_files(files: UserFiles) -> List[Path]:
    """Create missing starter files without overwriting user content.

    Args:
        files: Resolved destinations to initialize.

    Returns:
        Paths created during this call.
    """
    files.root.mkdir(parents=True, exist_ok=True)
    created: List[Path] = []
    for name, content in _STARTER_CONTENT.items():
        path = files.root / name
        if path.exists():
            continue
        path.write_text(content, encoding="utf-8")
        if name == ".pyesh_history":
            try:
                path.chmod(0o600)
            except OSError:
                pass
        created.append(path)
    return created

def _content_lines(path: Path) -> Iterable[str]:
    """Yield meaningful lines from an optional UTF-8 user file.

    Args:
        path: File to read.

    Returns:
        An iterable of stripped, nonblank, non-comment lines.
    """
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

def _expand_with(value: str, environment: Dict[str, str]) -> str:
    """Expand environment and home references against a mapping.

    Args:
        value: Source value.
        environment: Expansion environment.

    Returns:
        Expanded string.
    """
    import re
    value = re.sub(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))",
                   lambda match: environment.get(match.group(1) or match.group(2), match.group(0)), value)
    if value == "~" or value.startswith("~/"):
        value = environment.get("HOME", str(Path.home())) + value[1:]
    return value

def load_environment(path: Path, environment: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Load and apply deterministic ``NAME=value`` assignments.

    Args:
        path: `.pyeshenv`-format file.

    Returns:
        Assignments applied to ``os.environ``.

    Raises:
        ValueError: If a meaningful line is not an assignment or has an
            invalid environment variable name.
    """
    target = os.environ if environment is None else environment
    loaded: Dict[str, str] = {}
    for line in _content_lines(path):
        if "=" not in line:
            raise ValueError("{0}: expected NAME=value: {1}".format(path, line))
        name, value = line.split("=", 1)
        name = name.strip()
        if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
            raise ValueError("{0}: invalid environment name: {1}".format(path, name))
        expanded = _expand_with(value.strip(), target)
        target[name] = expanded
        loaded[name] = expanded
    return loaded

def load_search_paths(path: Path, environment: Optional[Dict[str, str]] = None) -> List[str]:
    """Prepend unique directories from `.pyesh_paths` to ``PATH``.

    Args:
        path: File containing one directory per meaningful line.

    Returns:
        Expanded path entries added to the front of ``PATH``.
    """
    target = os.environ if environment is None else environment
    requested = [
        os.path.abspath(_expand_with(line, target))
        for line in _content_lines(path)
    ]
    existing = target.get("PATH", "").split(os.pathsep)
    added: List[str] = []
    for entry in requested:
        if entry not in added and entry not in existing:
            added.append(entry)
    target["PATH"] = os.pathsep.join(added + existing)
    return added

def startup_commands(path: Path) -> List[str]:
    """Read pyesh startup commands from a profile or rc file.

    Args:
        path: `.pyesh_profile` or `.pyeshrc` path.

    Returns:
        Commands in file order.
    """
    return list(_content_lines(path))

def load_prompt_template(path: Path) -> Optional[str]:
    """Read the first active prompt template from a user file.

    Args:
        path: `.pyesh_prompt` file containing a format template.

    Returns:
        The first nonblank, non-comment line, or ``None`` when absent.
    """
    lines = list(_content_lines(path))
    return lines[0] if lines else None

def load_welcome_config(path: Path) -> Tuple[bool, str]:
    """Read the startup toggle and optional multiline welcome template.

    Args:
        path: `.pyesh_welcome` configuration file.

    Returns:
        ``(enabled, template)``. An empty template selects the built-in splash.

    Raises:
        ValueError: If the first active line is not ``enabled=true`` or
            ``enabled=false``.
    """
    if not path.is_file():
        return True, ""
    lines = path.read_text(encoding="utf-8").splitlines()
    setting_index = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        setting_index = index
        break
    if setting_index is None:
        return True, ""
    setting = lines[setting_index].strip().lower()
    if setting not in ("enabled=true", "enabled=false"):
        raise ValueError("{0}: expected enabled=true or enabled=false".format(path))
    template = "\n".join(lines[setting_index + 1 :]).strip("\n")
    return setting == "enabled=true", template

def save_welcome_enabled(path: Path, enabled: bool) -> None:
    """Persist the welcome toggle without changing its custom template.

    Args:
        path: `.pyesh_welcome` destination.
        enabled: New automatic-startup setting.

    Returns:
        None.

    Raises:
        OSError: If the configuration cannot be written.
        UnicodeError: If existing content is not valid UTF-8.
    """
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    replacement = "enabled={0}".format("true" if enabled else "false")
    setting_index = None
    for index, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped in ("enabled=true", "enabled=false"):
            setting_index = index
            break
    if setting_index is None:
        lines.insert(0, replacement)
    else:
        lines[setting_index] = replacement
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)

def enabled_plugins(path: Path) -> List[str]:
    """Read explicitly enabled plugin entry-point names.

    Args:
        path: `.pyesh_plugins` path.

    Returns:
        Sorted, deduplicated plugin names.
    """
    return sorted(set(_content_lines(path)))

def read_history(path: Path, limit: int) -> List[str]:
    """Read the newest commands from pyesh's private history file.

    Args:
        path: `.pyesh_history` path.
        limit: Maximum commands to return.

    Returns:
        At most ``limit`` commands, oldest first.
    """
    if not path.is_file():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    return lines[-limit:]

def write_history(path: Path, commands: Iterable[str]) -> None:
    """Write canonical newline-delimited pyesh history atomically.

    Args:
        path: `.pyesh_history` destination.
        commands: Commands in oldest-to-newest order.

    Returns:
        None.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join("{0}\n".format(command.replace("\n", " ")) for command in commands)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(str(temporary), str(path))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
