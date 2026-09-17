# Security and platform behavior

## Execution boundary

pyesh parses supported operators itself and invokes subprocesses with argument lists. It does not use `shell=True` or interpolate the complete input into a system shell command. This avoids an implicit second parser but does not make command input safe: entered commands, sourced files, native Python, and plugins are executable code.

## Local command policy

Bare names are resolved only through `PATH`. A current-directory file requires an explicit path such as `./tool.py`, `../tool.sh`, or an absolute path. This prevents an untrusted local file named like a global command from silently shadowing it. Tab completion preserves this policy by prefixing local command files with `./` or `.\\`.

## Trust levels

* External commands inherit the isolated pyesh session environment, directory, and standard streams.
* Native Python runs inside pyesh with full process privileges.
* Sourced pyesh files mutate the current session.
* Plugins are imported into the pyesh process and are fully trusted code.
* Bash and PowerShell files execute through real discovered runtimes.

Do not run untrusted commands, Python, source files, activation paths, or plugins. Do not construct automation command strings from untrusted input. Embedding applications should use `PyeshSession.run_argv()` for literal argument vectors instead of concatenating command text.

## User data

pyesh uses its own `.pyesh_history` and never changes another shell's history. History writes are atomic and request mode `0600` where supported. User files may contain sensitive paths, environment values, or commands and should not be committed. pyesh does not manage secrets.

## Platform notes

### macOS and Linux

`prompt-toolkit` supplies cross-platform editing and completion. POSIX script paths use `/`; standard venv activation is `bin/activate`.

### Windows

The same interactive editor runs on Windows. pyesh uses Windows-aware tokenization, searches Git for Windows locations for Bash, discovers both `pwsh` and Windows PowerShell, and recognizes venv files under `Scripts`.

### Runtime availability

`.py` dispatch uses the active session virtual environment when valid, then falls back to pyesh's Python executable. `.sh` and `.ps1` dispatch require the corresponding installed runtime. pyesh does not emulate those languages.

## Error statuses

* 127: command or required runtime unavailable;
* 126: operating-system launch failure;
* 1: ordinary command, plugin, conversion, or file failure in relevant paths;
* 2: selected built-in usage or interactive parse error.

The exact program status is otherwise from the final command.
