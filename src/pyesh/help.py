# help.py

from typing import Dict, List
from .console import colorize, print_error

TOPICS: Dict[str, str] = {
    "operators": "Shell operators\n    Use |, &&, ||, ;, and & for pipelines, conditions, sequencing, and background launch. Redirections attach to any pipeline stage. Use set -o pipefail to return the last failing stage.",
    "cd": "cd [DIRECTORY]\n    Change the current pyesh working directory. With no argument, use home. cd - returns to the previous directory.",
    "deactivate": "deactivate\n    Restore PATH and VIRTUAL_ENV after a pyesh source activation.",
    "exit": "exit [--force] [STATUS]\n    End the session with STATUS modulo 256, or the last command status if omitted.",
    "help": "help [COMMAND]\n    Show a command summary or detailed help for one built-in command.",
    "man": "man [TOPIC]\n    Show a pyesh manual topic. Unknown topics and system-man arguments are delegated to the installed man program.",
    "pwd": "pwd\n    Print the absolute path of the current pyesh working directory.",
    "source": "source FILE\n    Activate a standard Python virtual environment, or execute FILE as pyesh commands in the current session.",
    "verbose": "verbose [on|off|status]\n    Control live resolved process-launch tracing.",
    "welcome": "welcome [on|off|status]\n    Show the customizable pyesh splash, or control automatic startup display for this session. Configure persistence and content in ~/.pyesh_welcome.",
    "where": "where COMMAND [COMMAND ...]\n    Show every matching pyesh built-in and executable found in PATH order.",
    "python": "Python input\n    Enter assignments, imports, multiline control flow, definitions, calls, and expressions directly. Names persist. Helpers: sh(command), capture(command, type), argv, and env.",
    "python-pipes": "Python variable pipelines\n    Use @name or @name:datatype at pipeline edges. Assign with @name:type = expression; load a file with @name:type < path; capture a command with @name:type < command args. Types: str, bytes, json, lines, int, float. Capture plus > or >> also keeps exact bytes in a file.",
    "files": "User files\n    ~/.pyeshenv sets environment values; ~/.pyesh_paths extends PATH; ~/.pyesh_profile and ~/.pyeshrc run startup commands; ~/.pyesh_prompt formats the prompt; ~/.pyesh_welcome controls the splash; ~/.pyesh_history stores private history.",
    "plugins": "plugins\n    List commands from explicitly enabled installed plugins and report loading failures.",
    'jobs': 'jobs\n    List session job IDs, PIDs, and Running/Stopped/Done states. Completed jobs remain until wait or fg consumes their status.',
    'wait': 'wait [%JOB ...]\n    Wait for selected jobs, or all jobs; return the last selected status. A stopped job returns 128 + its stop signal and remains tracked. Ctrl+C interrupts waiting without killing the job.',
    'fg': 'fg [%JOB]\n    Resume and wait for a job (default: latest active job). On a POSIX interactive terminal, transfer terminal ownership and restore it afterward.',
    'bg': 'bg [%JOB]\n    Resume a stopped POSIX job in the background. Default: latest active job. Unsupported on Windows.',
    'kill': 'kill [-s SIGNAL | -SIGNAL] PID|%JOB ...\n    Send TERM by default, or a signal name/number. %JOB signals the pipeline group on POSIX. kill -l lists signals. Only positive numeric PIDs are accepted.',
    'export': 'export [NAME[=VALUE] ...]\n    Copy Python session values or explicit strings into the child environment. No arguments lists it.',
    'unset': 'unset NAME ...\n    Remove names from both session variables and the child environment.',
    'history': 'history [COUNT] | history -c\n    Show recent session commands or clear pyesh history. Interactive history is saved to .pyesh_history at normal session shutdown.',
    'alias': 'alias [NAME[=COMMAND] ...]\n    Define, inspect, or list session aliases. Quote COMMAND containing spaces. Values contain one command with arguments, without operators or redirections.',
    'unalias': 'unalias NAME ... | unalias -a\n    Remove selected aliases or all session aliases.',
    'pushd': 'pushd [DIRECTORY]\n    Change directory and save the old directory; with no argument swap with the top stack entry.',
    'popd': 'popd\n    Return to the top saved directory and remove it from the stack.',
    'dirs': 'dirs\n    Print the current directory followed by the directory stack, newest first.',
    'echo': 'echo [-n] [TEXT ...]\n    Print arguments separated by spaces. -n suppresses the trailing newline. No escape interpretation.',
    'printf': 'printf [--] FORMAT [ARG ...]\n    Print using %s, %b, %d, %i, %f, and %%, with fixed width/precision. Repeat FORMAT for extra arguments; missing values are empty/zero. Supports common backslash escapes, octal \\0NNN, and hex \\xHH.',
    'read': 'read [-r] [NAME ...]\n    Read stdin into native Python string variables (default REPLY). Split whitespace; the final variable receives the remainder. -r preserves backslashes. Supports < FILE. EOF returns 1; __ names are reserved.',
    'command': 'command [--] COMMAND [ARG ...] | command -v|-V NAME ...\n    Run without expanding aliases on COMMAND, retaining builtin/plugin resolution. -v prints a name/path; -V describes resolution.',
    'type': 'type [-a] NAME ...\n    Describe alias, builtin, plugin, or PATH resolution. -a shows every match.',
    'shift': 'shift [COUNT]\n    Remove COUNT positional arguments; the default is one.',
    'set': 'set -o pipefail | set +o pipefail\n    Enable or disable returning the last nonzero pipeline-stage status.',
    'disown': 'disown [%JOB ...]\n    Remove selected jobs from shell shutdown management.',
    'exec': 'exec COMMAND [ARG ...]\n    Replace pyesh on POSIX, or run COMMAND and exit with its status on Windows.',
}

def topic_names() -> List[str]:
    """Return available help topic names in display order.

    Returns:
        Sorted built-in command names.
    """
    return sorted(TOPICS)

def show_help(arguments: List[str]) -> int:
    """Display short shell help or one detailed built-in topic.

    Args:
        arguments: Words following the ``help`` command.

    Returns:
        Zero on success, nonzero for an invalid request.
    """
    if len(arguments) > 1:
        print_error("pyesh: help: too many arguments")
        return 2
    if arguments:
        topic = arguments[0]
        entry = TOPICS.get(topic)
        if entry is None:
            print_error("pyesh: help: no help topic for {0}".format(topic))
            return 1
        print(colorize("pyesh help", "bold cyan"))
        print(entry)
        return 0

    print(colorize("pyesh built-in commands", "bold cyan"))
    from .plugins import CORE_COMMANDS
    for name in sorted(CORE_COMMANDS):
        print("  " + TOPICS[name].split("\n", 1)[0])
    print("\nPython input")
    print("  Assignments, imports, calls, and expressions run in a persistent namespace.")
    print("\nExternal programs and discovered script runtimes run without `shell=True`.")
    print("Use `pyesh --help` for command-line options and `man COMMAND` for details.")
    return 0

def show_manual(arguments: List[str]) -> int:
    """Display the pyesh manual overview or one built-in entry.

    Args:
        arguments: Optional single manual topic.

    Returns:
        Zero on success, nonzero for an invalid request.
    """
    if len(arguments) > 1:
        print_error("pyesh: man: too many arguments")
        return 2
    if arguments:
        topic = arguments[0]
        entry = TOPICS.get(topic)
        if entry is None:
            print_error("pyesh: man: no manual entry for {0}".format(topic))
            return 1
        heading = {
            "python": "PYESH PYTHON",
            "python-pipes": "PYESH PYTHON PIPELINES",
            "files": "PYESH USER FILES",
        }.get(topic, "PYESH BUILTIN")
        print(colorize(heading, "bold cyan"))
        print(entry)
        return 0

    print(colorize("PYESH(1)", "bold cyan"))
    print("NAME\n    pyesh - Python Expanded Shell")
    print("\nSYNOPSIS\n    pyesh | pyesh -c COMMAND [ARG ...] | pyesh FILE.pyesh [ARG ...] | pyesh -")
    print("\nDESCRIPTION")
    print("    Run external programs directly and provide a small set of built-ins.")
    print("    Supports |, &, &&, ||, ;, >, >>, <, 2>, 2>>, 2>&1, and &> without invoking a system shell.")
    print("    Expands environment variables, home markers, and filesystem globs.")
    print("    Supports unified variables, special parameters, command substitution, and heredocs.")
    print("    Executes .py, .sh, and .ps1 files through discovered real runtimes.")
    from .plugins import CORE_COMMANDS
    builtins = sorted(CORE_COMMANDS)
    print("\nBUILT-INS\n    {0}".format(", ".join(builtins)))
    print("\nNATIVE PYTHON\n    Run `man python` for routing and session behavior.")
    print("\nPYTHON PIPELINES\n    Run `man python-pipes` for typed @variable endpoints.")
    print("\nUSER FILES\n    Run `man files` for startup and history files.")
    print("\nSEE ALSO\n    Run `man TOPIC` for a pyesh topic or system manual page.")
    return 0
