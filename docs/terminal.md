# Terminal behavior

## Interactive editing

The interactive shell colors input as it is typed. Commands and built-ins, operators, quoted strings, environment and Python-pipeline variables, options, and numbers each use a distinct color. Syntax coloring is presentation-only; the normal pyesh parser remains the source of truth for execution.

Set the conventional `NO_COLOR` environment variable to disable input and output colors. Arrow-key history and Tab completion are provided by the same cross-platform editor on Windows, macOS, and Linux.

Named JSON profiles can independently enable or disable colors, syntax highlighting, completion, completion while typing, and mouse support. They can also set every input token style. See [Configuration and user files](configuration.md#json-profiles).

## Line editing and completion

The interactive editor provides:

* up/down history navigation;
* Tab completion of built-ins and loaded plugin commands;
* executable discovery from `PATH`;
* filesystem completion for later arguments;
* current-directory command completion with an explicit `./` or `.\\` prefix.

Completion matching is case-insensitive and preserves the spelling of the matching command or filesystem entry. Directories end with the platform path separator. Typed `./` and `~/` prefixes are preserved. Alternate frontends that pass their own input function remain independent of this editor.

## Colors

Interactive diagnostics are red, help headings and traces use presentation colors, and the final parenthesized prompt segment is green. Redirected output does not receive ANSI color codes. Set `NO_COLOR` to disable pyesh colors.

Interactive external commands inherit `CLICOLOR=1` unless already set. Each program decides whether and how to color its own output.

## Verbose execution tracing

Start with tracing:

```bash
pyesh --verbose
```

Or change it during a session:

```plaintext
verbose on
verbose status
verbose off
```

`exec:` shows the resolved executable and arguments immediately before process launch. `builtin:` identifies commands running inside pyesh. `python:` and `python-pipe` identify native execution and typed endpoint conversion.

When verbose mode is already enabled at boot—through `--verbose` or startup configuration—pyesh also prints the active Python version and resolved executable before the first prompt. If a valid virtual environment is active, the displayed executable and script runtime are taken from that environment rather than an unrelated global Python.

This is portable launch tracing, not kernel syscall tracing. pyesh does not replace tools such as `strace`, `dtruss`, or Process Monitor.

## Interrupts and background processes

Ctrl+C at an idle prompt discards the current input and presents a new prompt. Ctrl+D/EOF applies the normal job-shutdown policy. Background commands return immediately and are managed with `jobs`, `wait`, `fg`, `bg`, `kill`, and `disown`. On POSIX, Ctrl+Z stops a foreground process group and terminal state is restored before the next prompt. Windows supports launch, listing, waiting, and termination but not POSIX suspension/resumption.
