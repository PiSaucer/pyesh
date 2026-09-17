# pyesh

Python Expanded Shell: a cross-platform, Python-oriented interactive and scripting shell with direct process execution, typed Python pipelines, configurable user files, and command plugins.

pyesh is its own shell language rather than a Bash interpreter. Explicit `.sh` and `.ps1` files continue to run through installed Bash and PowerShell runtimes.

## Highlights

* Job tracking with `jobs`, `wait`, `fg`, `bg`, `kill`, and `disown`; POSIX terminal job control.
* Environment, aliases, history, directory stacks, portable output, and input built-ins.
* Pipelines, conditions, per-stage redirection, heredocs, and `pipefail`.
* Session variables, special parameters, command substitution, home expansion, and globs.
* Stateful native Python at the prompt.
* Typed `@variable:datatype` pipeline input and capture.
* Explicit Python, Bash, and PowerShell script dispatch.
* `source`/`deactivate` support for Python virtual environments.
* Colorful live syntax highlighting, arrow-key history, and Tab completion.
* Custom prompt, environment, PATH, startup, history, and plugin files.
* Named JSON profiles for complete terminal and session customization.
* Persistent Rich-powered customizable welcome splash.
* Active-venv Python selection and optional venv-local pyesh startup files.
* Stateful Python automation API.

## Install and run

Requires Python 3.9 or newer:

```bash
python -m pip install -e .
pyesh --init
pyesh
pyesh -c 'echo "hello $(printf world)"'
pyesh automation.pyesh one two
printf 'echo from-stdin\n' | pyesh -
```

`pyesh` and `python -m pyesh` are equivalent.

```plaintext
user@machine project (main) % echo "hello"
hello
user@machine project (main) % numbers = [1, 2, 3]
user@machine project (main) % @numbers:lines | @copy:lines
user@machine project (main) % copy
['1', '2', '3']
```

Run `help` or `man` inside the shell. Use `pyesh --help` for command-line options and `pyesh --version` for package and interpreter locations. Run `welcome` for a customizable splash summarizing the current runtime and session. Configure its template and automatic startup in `~/.pyesh_welcome`.

## Documentation

The [documentation](docs/README.md) links the complete project guides. See the [Changelog](CHANGELOG.md) and [development guide](docs/development.md) for project history and development workflow.

## Quick examples

Operators and scripts:

```plaintext
./examples/hello.py
./examples/hello.sh | grep Bash
failing-command || echo fallback
echo first > output.txt ; echo second >> output.txt
```

Virtual environment:

```plaintext
python -m venv .venv
source .venv/bin/activate
deactivate
```

Python automation:

```python
from pyesh import PyeshSession

session = PyeshSession(verbose=True)
status = session.run_argv(["python", "./examples/hello.py"])
```

## Language boundary

Python syntax supplies control flow and reusable functions. Bash functions, Bash parameter-expansion extensions, process substitution, and arbitrary file descriptor manipulation are not implemented. POSIX interactive job control is supported; Windows cannot suspend/resume jobs. Plugin capabilities beyond commands remain planned.

## License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for more information.
