# Getting started

## Requirements

pyesh requires Python 3.9 or newer. The project targets Windows, macOS, and Linux where the required operating-system facilities are available. `prompt-toolkit` provides interactive editing and Rich provides terminal presentation.

## Install for development

From the repository root:

```bash
python -m pip install -e .
```

Start either equivalent entry point:

```bash
pyesh
python -m pyesh
```

## Initialize user files

```bash
pyesh --init
```

This creates only missing `.pyesh*` files in the user home directory. It never overwrites an existing file. Set `PYESH_HOME` before running pyesh to place all user files in another directory.

## First session

```plaintext
user@machine project (main) % pwd
/path/to/project
user@machine project (main) % echo "hello"
hello
user@machine project (main) % value = 21
user@machine project (main) % value * 2
42
user@machine project (main) % exit
```

Use `cd PATH` to change directory, `help` for a command summary, and `man` for pyesh topics or installed system manual pages. A new bare word is treated as an external command; clear Python expressions and previously defined Python names use the persistent native Python namespace.

For automation, use `pyesh -c`, a `.pyesh` file, or stdin. Those modes skip startup files by default and expose arguments through `$0`, `$1` onward, `$@`, and Python `argv`.

The pyesh splash is shown by default with its version, active Python executable, platform, current directory, and virtual environment. Run `welcome` to show it again, use `welcome on`, `welcome off`, or `welcome status` for session control, and edit `~/.pyesh_welcome` to customize it or disable it on future startups.

## Command-line options

| Option                 | Behavior                                                  |
| ---------------------- | --------------------------------------------------------- |
| `-h`, `--help`         | Show CLI help and exit                                    |
| `-V`, `--version`      | Show pyesh version/location and Python version/executable |
| `--init`               | Create missing user files and exit                        |
| `--safe`               | Start without loading enabled plugins                     |
| `--list-plugins`       | List installed plugin entry points without importing them |
| `-v`, `--verbose`      | Trace resolved executions from session startup            |
| `-c COMMAND`           | Execute source and return its status                      |
| `-i`, `--interactive`  | Enter a prompt after non-interactive input                |
| `-l`, `--login`        | Load login-profile files                                  |
| `--startup`            | Opt non-interactive execution into startup files          |
| `--no-startup`         | Skip all user startup files and plugins                   |
| `FILE.pyesh [ARG ...]` | Run a native script with positional arguments             |
| `- [ARG ...]`          | Read a native script from stdin                           |

## Next steps

* Learn the [shell language](shell-language.md).
* Configure the [prompt and startup files](configuration.md).
* Use [virtual environments and scripts](scripts-and-venvs.md).
* Exchange data through [typed Python pipelines](python-integration.md).
