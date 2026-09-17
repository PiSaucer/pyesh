# pyesh documentation

## User guides

* [Getting started](getting-started.md) — install, initialize, and run pyesh
* [Shell language](shell-language.md) — commands, operators, expansion, and built-ins
* [Native Python and typed pipelines](python-integration.md)
* [Configuration and user files](configuration.md)
* [Scripts, runtimes, and virtual environments](scripts-and-venvs.md)
* [Terminal behavior](terminal.md) — completion, history, colors, and tracing

## Extending and embedding

* [Python automation API](python-api.md)
* [Command plugins](plugins.md)

## Project reference

* [Security and platform behavior](security-and-platforms.md)
* [Architecture](architecture.md)
* [Development and releases](development.md)
* [Changelog](../CHANGELOG.md)

## Quick reference

```plaintext
pyesh                  Start an interactive session
pyesh --init           Create missing user files
pyesh --version        Show pyesh and Python versions and locations
pyesh --verbose        Start with execution tracing
pyesh --safe           Start without plugins
pyesh --list-plugins   Inspect installed plugin metadata
pyesh -c COMMAND       Execute source without startup files
pyesh FILE.pyesh       Execute a native pyesh script
pyesh -                Execute source from stdin
```

Inside pyesh, use `help`, `help COMMAND`, `man`, or `man COMMAND`. Run `welcome` for a runtime and session overview.
