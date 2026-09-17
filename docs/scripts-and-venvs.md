# Scripts, runtimes, and virtual environments

## Explicit script dispatch

When an explicitly addressed file starts with a shebang, pyesh uses that interpreter. The shebang takes precedence over the filename suffix, so extensionless scripts work as expected:

```plaintext
#!/usr/bin/env bash
```

Common Bash, Python, and PowerShell shebangs use pyesh's cross-platform runtime discovery. Other shebang interpreter paths and arguments are passed directly, without `shell=True`.

When a file has no shebang, pyesh selects a real interpreter for these suffixes:

| Suffix | Runtime                                                     |
| ------ | ----------------------------------------------------------- |
| `.py`  | Active virtual-environment Python, otherwise pyesh's Python |
| `.sh`  | A discovered Bash executable                                |
| `.ps1` | `pwsh`, `powershell`, or Windows PowerShell                 |

Examples:

```plaintext
./examples/hello.py
./examples/hello.sh
./examples/hello.ps1
```

Explicit script files do not require executable permission. Bash discovery also checks common Git for Windows locations. PowerShell scripts use `-NoProfile -File`. Missing runtimes produce actionable errors; pyesh does not emulate Bash or PowerShell.

Bare script names use `PATH` only:

```plaintext
hello.py       # PATH lookup; does not implicitly run ./hello.py
./hello.py     # explicit local script
```

When `VIRTUAL_ENV` identifies a valid environment, explicit `.py` scripts use that environment's `bin/python` or `Scripts/python.exe`. Otherwise they use the interpreter running pyesh. Explicit paths remain a security boundary against current-directory command shadowing.

## Virtual environments

Create and activate a venv in the current pyesh session:

```plaintext
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```plaintext
python -m venv .venv
source .venv/Scripts/activate.ps1
```

pyesh recognizes standard `bin/activate` and `Scripts/activate`, `activate.bat`, or `activate.ps1` paths. It sets `VIRTUAL_ENV` and prepends the activation script's directory to `PATH`; it does not interpret the activation script language. The default prompt gains a `(.venv)` prefix.

Restore the previous values saved by pyesh:

```plaintext
deactivate
```

Activations are stacked, so nested pyesh activations can be unwound in reverse order. `deactivate` only restores environments activated in the current pyesh session.

## Already-active environments at boot

When pyesh starts from an active virtual environment—or inherits a valid `VIRTUAL_ENV`—it normalizes that environment's executable directory to the front of `PATH`. The environment's Python is then used for explicit `.py` scripts and shown in verbose startup output and the welcome screen.

After user startup files, pyesh sources the active environment's `.pyeshrc` when it exists. Login sessions also source its `.pyesh_profile` first:

```plaintext
<venv>/.pyesh_profile
<venv>/.pyeshrc
```

These contain pyesh commands, not Bash or PowerShell activation syntax. pyesh does not execute a venv's shell-specific activation script automatically.

## pyesh command files

For any source file that is not a recognized venv activation path, `source` reads UTF-8 lines and executes them as pyesh commands in the current session:

```plaintext
source setup.pyesh
```

`.pyesh` is a naming convention, not a required suffix. Changes to the working directory, environment, native Python namespace, verbose mode, and exit state remain after sourcing. Blank lines and comment lines are ignored.

For deterministic automation, use `pyesh FILE.pyesh [ARG ...]`, `pyesh -c COMMAND [ARG ...]`, or `pyesh - [ARG ...]`. These modes skip startup files and plugins unless `--startup` is supplied. Script arguments are exposed through `$0`, `$1` onward, `$@`, and Python `argv`.
