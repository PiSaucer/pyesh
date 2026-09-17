# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- ## [Unreleased] -->

## [1.0.0] - 2026-09-17

### Added

* Interactive, command-string, `.pyesh` file, standard-input, login, and startup-control modes through equivalent `pyesh` and `python -m pyesh` entry points.
* Quote-aware parsing, environment and session variables, special parameters, nested command substitution, home expansion, filesystem globs, multiline Python blocks, and heredocs.
* Pipelines, background jobs, `&&`, `||`, `;`, `pipefail`, per-stage input and output redirection, descriptor duplication and closure, and append modes.
* Job control through `jobs`, `wait`, `fg`, `bg`, `kill`, and `disown`, with retained statuses, POSIX process groups, and terminal ownership where the platform supports them.
* Stateful built-ins for directories, environment variables, aliases, history, input, output, command lookup, virtual environments, script sourcing, session control, and process replacement.
* Stateful native Python assignments, imports, definitions, calls, and expressions at the prompt and through the automation API.
* Typed Python pipeline input, output capture, file loading, and optional exact file retention using `@variable:datatype` references.
* Public `PyeshSession` and `run_command` automation APIs, including command, script, file, and argument-vector execution with isolated session state.
* Non-destructive initialization and loading of pyesh-owned environment, path, profile, startup, history, prompt, welcome, and plugin files.
* Named JSON profiles for terminal and session customization.
* Versioned command plugins loaded only from explicitly enabled installed distributions, with metadata listing, completion, collision checks, and failure isolation.
* Cross-platform line editing, bounded history, case-insensitive command and path completion, and live syntax highlighting.
* A configurable `user@machine folder (branch) %` prompt with home-directory abbreviation and active-virtual-environment support.
* Terminal-aware output colors, `NO_COLOR` support, and a customizable welcome display containing version, Python, platform, directory, and environment details.
* Built-in `help` and `man` documentation, including delegation of non-pyesh topics to the system manual viewer.
* User, language, configuration, extension, API, security, architecture, platform, and development documentation with runnable examples.

[1.0.0]: https://github.com/PiSaucer/pyesh/releases/tag/v1.0.0
