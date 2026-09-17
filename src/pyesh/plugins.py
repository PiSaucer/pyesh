# plugins.py

from dataclasses import dataclass, field
from importlib import metadata
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from .console import print_error

PLUGIN_API_VERSION = 1
CORE_COMMANDS = {
    "cd", "deactivate", "exit", "help", "man", "plugins", "pwd", "source",
    "verbose", "welcome", "where", "jobs", "wait", "fg", "bg", "kill",
    "export", "unset", "history", "alias", "unalias", "pushd", "popd", "dirs",
    "echo", "printf", "read", "command", "type", "shift", "set", "disown", "exec"
}
PluginHandler = Callable[[Sequence[str]], int]

@dataclass(frozen=True)
class PluginCommand:
    """A command contributed by one plugin.

    Attributes:
        name: Public command name.
        handler: Callable receiving arguments after the command name.
        help: One-line user-facing description.
    """

    name: str
    handler: PluginHandler
    help: str
    pipeline_safe: bool = False

@dataclass(frozen=True)
class Plugin:
    """The object returned by a `pyesh.plugins` entry-point factory.

    Attributes:
        name: Stable plugin identity matching its entry-point name.
        api_version: Supported pyesh plugin API version.
        commands: Commands contributed by the plugin.
    """

    name: str
    api_version: int = PLUGIN_API_VERSION
    commands: Sequence[PluginCommand] = field(default_factory=tuple)

@dataclass(frozen=True)
class DiscoveredPlugin:
    """Read-only plugin distribution metadata that requires no code loading."""

    name: str
    value: str
    distribution: str
    version: str

def discover_plugins() -> List[DiscoveredPlugin]:
    """Discover plugin metadata without importing plugin code.

    Returns:
        Deterministically sorted entry-point metadata.
    """
    entry_points = metadata.entry_points()
    if hasattr(entry_points, "select"):
        selected = entry_points.select(group="pyesh.plugins")
    else:  # Python 3.9 compatibility with the older mapping interface.
        selected = entry_points.get("pyesh.plugins", [])
    discovered = []
    for entry_point in selected:
        distribution = getattr(entry_point, "dist", None)
        discovered.append(
            DiscoveredPlugin(
                name=entry_point.name,
                value=entry_point.value,
                distribution=getattr(distribution, "name", "unknown"),
                version=getattr(distribution, "version", "unknown"),
            )
        )
    return sorted(discovered, key=lambda plugin: plugin.name)

def _entry_points_by_name() -> Mapping[str, object]:
    """Return discovered entry-point objects keyed by stable name.

    Returns:
        Entry-point objects keyed by declared plugin name.
    """
    entry_points = metadata.entry_points()
    selected = (
        entry_points.select(group="pyesh.plugins")
        if hasattr(entry_points, "select")
        else entry_points.get("pyesh.plugins", [])
    )
    result: Dict[str, object] = {}
    for entry_point in selected:
        if entry_point.name in result:
            raise ValueError("duplicate plugin entry point: {0}".format(entry_point.name))
        result[entry_point.name] = entry_point
    return result

class PluginManager:
    """Loaded plugin commands for one pyesh session."""

    def __init__(self) -> None:
        """Create an empty manager with no imported plugin code."""
        self._plugins: Dict[str, Plugin] = {}
        self._commands: Dict[str, PluginCommand] = {}
        self._errors: Dict[str, str] = {}

    @property
    def errors(self) -> Mapping[str, str]:
        """Return plugin loading failures keyed by plugin name.

        Returns:
            A copy of plugin error messages.
        """
        return dict(self._errors)

    def load_enabled(self, names: Iterable[str]) -> None:
        """Load explicitly enabled entry points and validate registrations.

        Args:
            names: Stable entry-point names to load.

        Returns:
            None. Individual failures are retained in ``errors``.
        """
        try:
            available = _entry_points_by_name()
        except Exception as error:
            self._errors["discovery"] = str(error)
            return
        for name in sorted(set(names)):
            entry_point = available.get(name)
            if entry_point is None:
                self._errors[name] = "enabled plugin is not installed"
                continue
            try:
                factory = entry_point.load()
                plugin = factory()
                self._register(name, plugin)
            except BaseException as error:
                self._errors[name] = "{0}: {1}".format(type(error).__name__, error)

    def _register(self, entry_point_name: str, plugin: object) -> None:
        """Validate and register one loaded plugin.

        Args:
            entry_point_name: Declared distribution entry-point name.
            plugin: Factory result to validate.

        Returns:
            None.
        """
        if not isinstance(plugin, Plugin):
            raise TypeError("plugin factory must return pyesh.plugins.Plugin")
        if plugin.name != entry_point_name:
            raise ValueError("plugin name must match its entry-point name")
        if plugin.api_version != PLUGIN_API_VERSION:
            raise ValueError("unsupported plugin API {0}; expected {1}".format(plugin.api_version, PLUGIN_API_VERSION))
        pending: Dict[str, PluginCommand] = {}
        for command in plugin.commands:
            if not command.name or not command.name.replace("-", "a").isalnum():
                raise ValueError("invalid plugin command name: {0}".format(command.name))
            if command.name in CORE_COMMANDS or command.name in self._commands:
                raise ValueError("plugin command collision: {0}".format(command.name))
            if command.name in pending:
                raise ValueError("duplicate plugin command: {0}".format(command.name))
            pending[command.name] = command
        self._plugins[plugin.name] = plugin
        self._commands.update(pending)

    def command_names(self) -> List[str]:
        """Return loaded plugin command names in deterministic order.

        Returns:
            Sorted public command names.
        """
        return sorted(self._commands)

    def pipeline_plugin(self, command_name: str) -> Optional[str]:
        """Resolve the owner of a pipeline-safe plugin command.

        Args:
            command_name: Public command name.

        Returns:
            Plugin name, or ``None`` when the command is not pipeline-safe.
        """
        command = self._commands.get(command_name)
        if command is None or not command.pipeline_safe:
            return None
        return next((name for name, plugin in self._plugins.items() if command in plugin.commands), None)

    def run(self, arguments: Sequence[str]) -> Optional[int]:
        """Run a contributed command when one matches.

        Args:
            arguments: Command name followed by arguments.

        Returns:
            ``None`` when no plugin command matches, otherwise its integer
            status. Plugin exceptions are reported and converted to status 1.
        """
        command = self._commands.get(arguments[0]) if arguments else None
        if command is None:
            return None
        try:
            status = command.handler(arguments[1:])
            if not isinstance(status, int):
                raise TypeError("plugin command must return an integer status")
            return status
        except BaseException as error:
            print_error("pyesh: plugin command {0} failed: {1}: {2}".format(command.name, type(error).__name__, error))
            return 1

    def describe(self) -> List[str]:
        """Return human-readable loaded command and error descriptions.

        Returns:
            Sorted command descriptions followed by loading errors.
        """
        lines = [
            "{0}: {1}".format(name, self._commands[name].help)
            for name in self.command_names()
        ]
        lines.extend(
            "{0}: ERROR: {1}".format(name, error)
            for name, error in sorted(self._errors.items())
        )
        return lines
