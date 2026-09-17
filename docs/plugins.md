# Command plugins

pyesh supports installed plugins that contribute built-in-style commands. Nothing is downloaded or enabled automatically.

## Package entry point

Declare a factory in the plugin distribution:

```toml
[project.entry-points."pyesh.plugins"]
hello = "hello_pyesh:plugin"
```

The entry-point name is the plugin identity and must match `Plugin.name`.

## Plugin contract

```python
from pyesh.plugins import Plugin, PluginCommand

def greet(arguments):
    name = arguments[0] if arguments else "world"
    print("Hello, {0}!".format(name))
    return 0

def plugin():
    return Plugin(
        name="hello",
        commands=(PluginCommand("greet", greet, "Greet a person.", pipeline_safe=True),),
    )
```

`Plugin` fields:

* `name`: exact entry-point name;
* `api_version`: defaults to the current `PLUGIN_API_VERSION` (1);
* `commands`: sequence of `PluginCommand` objects.

`PluginCommand` fields:

* `name`: nonempty alphanumeric/hyphen command name;
* `handler`: callable receiving arguments after the command name;
* `help`: one-line description shown by `plugins`.
* `pipeline_safe`: permits child-process execution in pipelines/background jobs; defaults to `False`.

A handler must return an integer status. Exceptions and invalid return values are isolated, reported, and converted to status 1.

## Enable and inspect

After installing the distribution, add its entry-point name to `~/.pyesh_plugins`, one per line, and restart pyesh:

```plaintext
hello
```

Commands:

```plaintext
plugins
```

CLI inspection and recovery:

```bash
pyesh --list-plugins
pyesh --safe
```

`--list-plugins` reads package metadata without importing plugin code. `--safe` prevents interactive plugin loading. Automation can explicitly use `PyeshSession(plugins=["hello"])`.

## Validation and restrictions

pyesh rejects:

* objects that are not `Plugin` instances;
* mismatched names or API versions;
* collisions with core commands or another plugin;
* duplicate or invalid command names.

Standalone plugin commands run in the shell process. Commands explicitly marked `pipeline_safe=True` may also run in a child process inside pipelines or background jobs. Input redirection remains unsupported for in-process plugin commands; output redirection is supported. Plugin code runs with the user's permissions, including in child mode, so enable only trusted distributions.

Completion providers, prompt segments, history backends, and execution backends are planned but not implemented.
