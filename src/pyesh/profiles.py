# profiles.py

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from prompt_toolkit.styles import Style

from .config import DEFAULT_TERMINAL_STYLES, ShellConfig, TerminalConfig

_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROFILE_KEYS = {
    "prompt", "history_limit", "verbose", "plugins", "terminal", "welcome",
    "environment", "paths", "startup_commands",
}
_TERMINAL_KEYS = {
    "colors", "syntax_highlighting", "completion", "complete_while_typing",
    "mouse_support", "styles",
}
_STYLE_KEYS = set(DEFAULT_TERMINAL_STYLES)

def _object(value: Any, label: str) -> Mapping[str, Any]:
    """Require a JSON object.

    Args:
        value: Candidate decoded value.
        label: Diagnostic field name.

    Returns:
        The validated mapping.
    """
    if not isinstance(value, dict):
        raise ValueError("{0} must be a JSON object".format(label))
    return value

def _unknown(value: Mapping[str, Any], allowed: set, label: str) -> None:
    """Reject unknown mapping keys.

    Args:
        value: Mapping to inspect.
        allowed: Accepted keys.
        label: Diagnostic field name.

    Returns:
        None.
    """
    extra = sorted(set(value) - allowed)
    if extra:
        raise ValueError("{0} has unknown setting: {1}".format(label, extra[0]))

def _boolean(value: Any, label: str) -> bool:
    """Require a Boolean setting.

    Args:
        value: Candidate value.
        label: Diagnostic field name.

    Returns:
        The validated Boolean.
    """
    if not isinstance(value, bool):
        raise ValueError("{0} must be true or false".format(label))
    return value

def _strings(value: Any, label: str) -> Tuple[str, ...]:
    """Require an array of non-empty strings.

    Args:
        value: Candidate decoded value.
        label: Diagnostic field name.

    Returns:
        Validated strings as a tuple.
    """
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("{0} must be an array of non-empty strings".format(label))
    return tuple(value)

def available_profiles(path: Path) -> Tuple[Optional[str], List[str]]:
    """Return configured profile names without applying one.

    Args:
        path: Profile JSON path.

    Returns:
        Default profile name and sorted available names.
    """
    document = _read_document(path)
    default = document.get("default_profile")
    if default is not None and not isinstance(default, str):
        raise ValueError("default_profile must be a string or null")
    profiles = _object(document.get("profiles", {}), "profiles")
    return default, sorted(profiles)

def load_profile(path: Path, name: Optional[str]) -> Tuple[Optional[str], ShellConfig]:
    """Load a JSON profile without mutating process state.

    Args:
        path: Profile JSON path.
        name: Explicit profile name, or ``None`` for the configured default.

    Returns:
        Selected name and validated shell configuration.
    """
    document = _read_document(path)
    _unknown(document, {"version", "default_profile", "profiles"}, str(path))
    if document.get("version", 1) != 1:
        raise ValueError("{0}: unsupported profile version".format(path))
    profiles = _object(document.get("profiles", {}), "profiles")
    selected = name if name is not None else document.get("default_profile")
    if selected is None:
        return None, ShellConfig()
    if not isinstance(selected, str) or not selected:
        raise ValueError("default_profile must be a non-empty string or null")
    if selected not in profiles:
        raise ValueError("profile not found: {0}".format(selected))
    profile = _object(profiles[selected], "profile {0}".format(selected))
    _unknown(profile, _PROFILE_KEYS, "profile {0}".format(selected))
    return selected, _parse_profile(profile, selected)

def apply_profile_environment(config: ShellConfig, environment=None) -> None:
    """Apply a profile's environment and PATH additions.

    Args:
        config: Validated shell configuration.
        environment: Optional target environment mapping.

    Returns:
        None.
    """
    target = os.environ if environment is None else environment
    from .user_files import _expand_with
    for name, value in config.environment:
        target[name] = _expand_with(value, target)
    requested = [
        os.path.abspath(_expand_with(item, target))
        for item in config.paths
    ]
    existing = target.get("PATH", "").split(os.pathsep)
    added = []
    for item in requested:
        if item not in added and item not in existing:
            added.append(item)
    target["PATH"] = os.pathsep.join(added + existing)

def _read_document(path: Path) -> Mapping[str, Any]:
    """Read an optional profile JSON document.

    Args:
        path: JSON file path.

    Returns:
        Decoded root mapping, or an empty mapping when absent.
    """
    if not path.is_file():
        return {}
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), str(path))
    except json.JSONDecodeError as error:
        raise ValueError("{0}: invalid JSON at line {1}, column {2}: {3}".format(path, error.lineno, error.colno, error.msg)) from error

def _parse_profile(profile: Mapping[str, Any], name: str) -> ShellConfig:
    """Validate one decoded profile.

    Args:
        profile: Profile settings mapping.
        name: Profile name used in diagnostics.

    Returns:
        Validated shell configuration.
    """
    label = "profile {0}".format(name)
    prompt = profile.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        raise ValueError("{0}.prompt must be a string or null".format(label))
    history_limit = profile.get("history_limit", 1000)
    if isinstance(history_limit, bool) or not isinstance(history_limit, int) or history_limit <= 0:
        raise ValueError("{0}.history_limit must be a positive integer".format(label))
    verbose = _boolean(profile.get("verbose", False), label + ".verbose")
    plugins = None
    if "plugins" in profile:
        plugins = tuple(sorted(set(_strings(profile["plugins"], label + ".plugins"))))

    terminal_data = _object(profile.get("terminal", {}), label + ".terminal")
    _unknown(terminal_data, _TERMINAL_KEYS, label + ".terminal")
    style_data = _object(terminal_data.get("styles", {}), label + ".terminal.styles")
    _unknown(style_data, _STYLE_KEYS, label + ".terminal.styles")
    styles: Dict[str, str] = dict(DEFAULT_TERMINAL_STYLES)
    for key, value in style_data.items():
        if not isinstance(value, str):
            raise ValueError("{0}.terminal.styles.{1} must be a string".format(label, key))
        styles[key] = value
    try:
        Style.from_dict({"pyesh.{0}".format(key): value for key, value in styles.items()})
    except ValueError as error:
        raise ValueError("{0}.terminal.styles has an invalid style: {1}".format(label, error)) from error
    terminal = TerminalConfig(
        colors=_boolean(terminal_data.get("colors", True), label + ".terminal.colors"),
        syntax_highlighting=_boolean(terminal_data.get("syntax_highlighting", True), label + ".terminal.syntax_highlighting"),
        completion=_boolean(terminal_data.get("completion", True), label + ".terminal.completion"),
        complete_while_typing=_boolean(terminal_data.get("complete_while_typing", False), label + ".terminal.complete_while_typing"),
        mouse_support=_boolean(terminal_data.get("mouse_support", False), label + ".terminal.mouse_support"),
        styles=styles,
    )

    welcome = _object(profile.get("welcome", {}), label + ".welcome")
    _unknown(welcome, {"enabled", "template"}, label + ".welcome")
    welcome_enabled = None if "enabled" not in welcome else _boolean(welcome["enabled"], label + ".welcome.enabled")
    welcome_template = welcome.get("template")
    if welcome_template is not None and not isinstance(welcome_template, str):
        raise ValueError("{0}.welcome.template must be a string".format(label))

    environment_data = _object(profile.get("environment", {}), label + ".environment")
    environment = []
    for key, value in environment_data.items():
        if not _ENVIRONMENT_NAME.match(key) or not isinstance(value, str):
            raise ValueError("{0}.environment requires valid names and string values".format(label))
        environment.append((key, value))
    return ShellConfig(
        prompt=prompt,
        history_limit=history_limit,
        verbose=verbose,
        plugins=plugins,
        terminal=terminal,
        welcome_enabled=welcome_enabled,
        welcome_template=welcome_template,
        environment=tuple(environment),
        paths=_strings(profile.get("paths", []), label + ".paths"),
        startup_commands=_strings(profile.get("startup_commands", []), label + ".startup_commands"),
    )
