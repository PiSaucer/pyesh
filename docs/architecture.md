# Architecture

pyesh keeps presentation, parsing, execution, and stateful behavior separated, so alternate frontends can reuse the same core APIs.

| Module                 | Responsibility                                                    |
| ---------------------- | ----------------------------------------------------------------- |
| `pyesh.cli`            | CLI argument parsing and version report                           |
| `pyesh.shell`          | Session orchestration and command routing                         |
| `pyesh.parsing`        | Quote-aware words, operators, redirections, and expansion         |
| `pyesh.execution`      | Direct subprocesses, pipelines, capture, and background reaping   |
| `pyesh.backends`       | Explicit `.py`, `.sh`, and `.ps1` runtime selection               |
| `pyesh.jobs`           | Session job IDs/statuses, child reaping, POSIX terminal ownership |
| `pyesh.builtins`       | Small general-purpose stateful built-ins                          |
| `pyesh.python_runtime` | Persistent native Python namespace                                |
| `pyesh.python_pipes`   | Typed variable serialization                                      |
| `pyesh.plugins`        | Entry-point discovery and command registration                    |
| `pyesh.user_files`     | Initialization, startup files, PATH, and history persistence      |
| `pyesh.prompt`         | Dynamic prompt data and formatting                                |
| `pyesh.console`        | Colors, diagnostics, and trace presentation                       |
| `pyesh.terminal`       | Interactive editing, syntax colors, and completion                |
| `pyesh.api`            | Public embedding API                                              |

## Routing overview

One input line is classified and routed in this order:

1. typed `@name:type = expression` assignment;
2. variable-first capture rewrite;
3. unambiguous native Python;
4. pyesh operator parsing and argument expansion;
5. typed Python pipeline endpoints;
6. standalone built-in or plugin command;
7. external foreground/background pipeline.

Variable and command substitution occurs after parsing and before command routing. Commands such as `cd`, `source`, and venv activation execute in the pyesh process against isolated `SessionState`. External commands, stateless built-ins in pipelines, and pipeline-safe plugins cross a subprocess boundary. Interactive, script, CLI, and public API entry points share the same evaluator.

## Compatibility policy

pyesh supports Python 3.9+, so new syntax and APIs unavailable in 3.9 require a fallback. Runtime dependencies are intentionally minimized. Configuration and history use deterministic text formats and standard-library facilities.
