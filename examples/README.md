# pyesh examples

## Basic usage and external commands

Install pyesh, start it, and enter a program plus arguments:

```console
$ pyesh
pyesh> python --version
pyesh> cd examples
pyesh> pwd
pyesh> help
pyesh> man cd
pyesh> exit
```

Initialize user-owned environment, PATH, startup, and history files with:

```bash
pyesh --init
```

For complete usage documentation, see the [documentation index](../docs/README.md).

Commands are executed directly. Operators including `|`, `&&`, `||`, `>`, and
`>>`, plus nested command substitution with `$()`, are implemented by pyesh.

Run native automation without interactive startup files:

```bash
pyesh -c 'echo "hello $(printf world)"'
pyesh task.pyesh first second
printf 'echo from-stdin\n' | pyesh -
```

## Python script

The working external-command path can run Python explicitly:

```console
pyesh> ./examples/hello.py
```

pyesh recognizes `.py` and uses the active Python interpreter, so executable permission and a shebang are not required.

## Native Python input

Assignments and expressions execute directly in a persistent session namespace:

```console
pyesh> a = 10
pyesh> a * 2
20
pyesh> print(a)
10
```

Ordinary bare command names remain external commands.

Use Python control flow with the session helpers:

```python
for name in ["Ada", "Grace"]:
    sh("echo " + name)

captured = capture("printf 42", "int")
```

Typed variables can provide pipeline input or capture output:

```console
pyesh> words = ["alpha", "beta"]
pyesh> @words:lines | grep beta | @matched:str > matched.txt
pyesh> print(matched)
beta
```

## Bash script

pyesh discovers a real Bash runtime and uses it automatically:

```console
pyesh> ./examples/hello.sh
```

On Windows, common Git for Windows Bash locations are also searched. Full Bash script compatibility comes from that real Bash runtime; pyesh reports an error when none is installed.

## PowerShell script

pyesh discovers `pwsh` or Windows PowerShell for `.ps1` files:

```console
pyesh> ./examples/hello.ps1
```

## Virtual environment

```console
pyesh> python -m venv .venv
pyesh> source .venv/bin/activate
(.venv) user@machine pyesh (main) % python --version
(.venv) user@machine pyesh (main) % deactivate
```

On Windows, source `.venv/Scripts/activate.ps1` instead.

## Expansion and operators

```console
pyesh> echo examples/*.py
pyesh> failing-command || echo fallback
pyesh> echo first > output.txt ; echo second >> output.txt
```

## Automating pyesh from Python

The installed package exposes a reusable session API:

```python
from pyesh import PyeshSession

session = PyeshSession(verbose=True)
status = session.run("./examples/hello.py")
```

Run [`automate.py`](automate.py) from the repository root for a stateful multi-command example:

```bash
python examples/automate.py
```

## History

The shell persists bounded newline-delimited history in `~/.pyesh_history`.
Use `history [COUNT]` to inspect it and `history -c` to clear the current
session and its next persisted snapshot.

## Prompt customization

Run `pyesh --init`, then edit `~/.pyesh_prompt`. For example:

```plaintext
[{status}] {user} in {folder}{branch_segment} $
```

The supported fields are `{user}`, `{host}`, `{folder}`, `{path}`, `{branch}`, `{branch_segment}`, `{status}`, `{venv}`, and `{venv_segment}`. See [configuration](../docs/configuration.md) for all user files and loading rules.
