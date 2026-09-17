# Python automation API

The stable top-level API exports `PyeshSession` and `run_command`.

## Stateful sessions

```python
from pyesh import PyeshSession

session = PyeshSession(verbose=True)
status = session.run_all(
    [
        "value = 21",
        "value * 2",
        "./examples/hello.py",
    ],
    stop_on_error=True,
)
raise SystemExit(status)
```

### `PyeshSession(verbose=False, plugins=None)`

* `verbose`: enables launch tracing.
* `plugins`: optional iterable of installed plugin entry-point names to load. Interactive user plugin configuration is not loaded automatically.

The session exposes read-only properties:

* `verbose`: current tracing state;
* `exit_requested`: whether `exit` was run;
* `exit_status`: the status retained by `exit`;
* `plugin_errors`: copied mapping of plugin loading failures.
* `cwd`: isolated working directory;
* `environment`: copied child-environment mapping;
* `variables`: copied user-visible Python values.

### `run(command_line)`

Runs one pyesh command line and returns its integer status. Invalid pyesh syntax raises `ValueError`. Once `exit` is requested, later calls return its retained status without execution. `exit N` uses N modulo 256; bare `exit` uses the last command status. Built-in errors now return nonzero statuses.

### `run_all(command_lines, stop_on_error=False)`

Runs input lines in order and returns the final status, or zero for an empty iterable. It stops after `exit`; with `stop_on_error=True`, it also stops at the first nonzero status.

### Script and direct execution

* `run_script(source, filename="<string>", argv=())` executes complete pyesh source.
* `run_file(path, argv=())` reads and executes a UTF-8 native script.
* `run_argv(arguments)` bypasses shell parsing and executes a literal argument vector.
* `set_cwd(path)` and `set_environment(name, value)` explicitly update isolated state.
* `close()` hangs up managed jobs; context-manager exit calls it automatically.

## Session built-ins and jobs

Aliases, directory stacks, job IDs/statuses, and history belong to the session. `read NAME` stores a string in the native Python namespace, usable as `@NAME` or in Python expressions. It does not create an environment variable.

```python
session = PyeshSession()
session.run('printf "hello\\n" > output.txt &')
status = session.run('wait %1')
```

`jobs` lists background and stopped jobs; `wait` consumes completed statuses. `fg` waits and resumes POSIX jobs; terminal ownership is enabled only by the interactive CLI, not by an embedded API session. Background API stdin defaults to the null device unless redirected. Use `close()` or a `with PyeshSession()` block to terminate managed jobs; `disown` excludes selected jobs.

## Stateless helper

```python
from pyesh import run_command

status = run_command("printf 'hello\\n' | grep hello", verbose=True)
```

`run_command(command_line, verbose=False)` creates a new session for one line.

## Process-wide effects

Each `PyeshSession` owns its current directory, environment, variables, arguments, and jobs. Commands inherit this isolated session state; `cd`, `export`, and venv activation do not mutate the embedding process.

Use `run_script`, `run_file`, and injection-safe `run_argv` for automation. The `cwd`, `environment`, and `variables` properties return session state; `set_cwd` and `set_environment` make explicit changes. Call `close()` to hang up tracked jobs, or use `PyeshSession` as a context manager.

Command strings are executable input. Never concatenate untrusted text into a command line. Use `run_argv()` when arguments originate from untrusted or separately validated data.
