# cli.py

import argparse
import platform
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import ShellConfig
from .plugins import discover_plugins
from .profiles import apply_profile_environment, available_profiles, load_profile
from .shell import SessionState, execute_script, run_shell
from .user_files import enabled_plugins, initialize_user_files, load_environment, load_search_paths, startup_commands, user_files

def build_parser() -> argparse.ArgumentParser:
    """Create the public command-line argument parser.

    Returns:
        A configured parser for the ``pyesh`` command.
    """
    parser = argparse.ArgumentParser(prog="pyesh",description="Python Expanded Shell (pyesh)")
    parser.add_argument(
        "--profile",
        metavar="NAME",
        help="Use NAME from .pyesh_profiles.json.",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List configured JSON profiles and exit.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Show the version and exit.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create missing pyesh user files without overwriting existing files.",
    )
    parser.add_argument(
        "--safe",
        action="store_true",
        help="Start without loading plugins.",
    )
    parser.add_argument(
        "--list-plugins",
        action="store_true",
        help="List installed plugin metadata without importing plugin code.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Trace resolved process launches before execution.",
    )
    parser.add_argument("-c", dest="command", metavar="COMMAND", help="Execute COMMAND and exit.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Enter an interactive session after input.")
    parser.add_argument("-l", "--login", action="store_true", help="Load login startup files.")
    startup_group = parser.add_mutually_exclusive_group()
    startup_group.add_argument("--startup", action="store_true", help="Load startup files in non-interactive mode.")
    startup_group.add_argument("--no-startup", action="store_true", help="Skip all user startup files and plugins.")
    parser.add_argument("script", nargs="?", help="A .pyesh script, or - for stdin.")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Script arguments.")
    return parser

def version_report() -> str:
    """Build the deterministic, human-readable runtime version report.

    Returns:
        Lines containing the pyesh version and package location followed by
        the Python version and interpreter executable location.
    """
    package_location = Path(__file__).resolve().parent
    return "\n".join(
        [
            "pyesh {0}".format(__version__),
            "Python {0}".format(platform.python_version()),
            "pyesh location: {0}".format(package_location),
            "Python executable: {0}".format(Path(sys.executable).resolve()),
        ]
    )

def main(argv: Optional[List[str]] = None) -> int:
    """Run the pyesh command-line application.

    Args:
        argv: Arguments excluding the executable name. When omitted, arguments
            are read from ``sys.argv``.

    Returns:
        The process exit status.
    """
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(version_report())
        return 0
    if args.init:
        files = user_files()
        created = initialize_user_files(files)
        if created:
            for path in created:
                print("created {0}".format(path))
        else:
            print("pyesh user files already exist in {0}".format(files.root))
        return 0
    if args.list_plugins:
        discovered = discover_plugins()
        if not discovered:
            print("no installed pyesh plugins")
        for plugin in discovered:
            print("{0} {1} ({2}) -> {3}".format(plugin.name, plugin.version, plugin.distribution, plugin.value))
        return 0
    files = user_files()
    if args.list_profiles:
        try:
            default, names = available_profiles(files.profiles)
        except (OSError, UnicodeError, ValueError) as error:
            parser.error(str(error))
        if not names:
            print("no configured pyesh profiles")
        for name in names:
            print("{0}{1}".format(name, " (default)" if name == default else ""))
        return 0
    try:
        _, profile_config = load_profile(files.profiles, args.profile)
    except (OSError, UnicodeError, ValueError) as error:
        parser.error(str(error))
    config = ShellConfig(
            prompt=profile_config.prompt,
            history_limit=profile_config.history_limit,
            verbose=args.verbose or profile_config.verbose,
            plugins_enabled=not (args.safe or args.no_startup),
            plugins=profile_config.plugins,
            terminal=profile_config.terminal,
            welcome_enabled=profile_config.welcome_enabled,
            welcome_template=profile_config.welcome_template,
            environment=profile_config.environment,
            paths=profile_config.paths,
            startup_commands=profile_config.startup_commands,
        )
    if args.command is not None or args.script is not None:
        state = SessionState(verbose=config.verbose)
        try:
            if args.startup and not args.no_startup:
                load_environment(files.environment, state.environment)
                load_search_paths(files.paths, state.environment)
                apply_profile_environment(config, state.environment)
                if config.plugins_enabled:
                    selected = config.plugins if config.plugins is not None else enabled_plugins(files.plugins)
                    state.plugins.load_enabled(selected)
                startup_files = ([files.profile] if args.login else []) + [files.rc]
                for startup_file in startup_files:
                    execute_script("\n".join(startup_commands(startup_file)), state,
                                   str(startup_file))
                execute_script("\n".join(config.startup_commands), state, "<profile>")
            if args.command is not None:
                command_arguments = ([args.script] if args.script is not None else []) + args.arguments
                state.argv0 = command_arguments[0] if command_arguments else "pyesh"
                state.argv[:] = command_arguments[1:]
                status = execute_script(args.command, state, "-c")
            else:
                state.argv0 = args.script or "pyesh"
                state.argv[:] = args.arguments
                if args.script == "-":
                    source = sys.stdin.read()
                    filename = "<stdin>"
                else:
                    script_path = Path(args.script).expanduser().resolve(strict=True)
                    source = script_path.read_text(encoding="utf-8")
                    filename = str(script_path)
                    state.argv0 = filename
                status = execute_script(source, state, filename)
        except KeyboardInterrupt:
            status = 130
        except (OSError, UnicodeError, ValueError) as error:
            print("pyesh: {0}".format(error), file=sys.stderr)
            status = 2
        if not args.interactive:
            return status
        state.last_status = status
        return run_shell(config=config, state=state, startup=args.startup and not args.no_startup, login=args.login)
    return run_shell(config=config, startup=not args.no_startup, login=args.login)

if __name__ == "__main__":
    sys.exit(main())
