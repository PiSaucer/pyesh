# Shell language

pyesh parses a deliberately limited shell language and starts processes with argument lists. It does not pass user command text to `shell=True`.

## Commands and quoting

Whitespace separates arguments. Single quotes suppress expansion; double quotes allow variables and command substitution without field splitting or globbing:

```plaintext
python -c "print('hello world')"
```

Bare commands are resolved through `PATH`. Files in the current directory are not implicitly executable; use `./script.py` on POSIX or an explicit Windows path. This prevents current-directory files from shadowing trusted commands.

## Operators

| Operator     | Meaning                                              |
| ------------ | ---------------------------------------------------- |
| `a | b`      | Pipe stdout from `a` to stdin of `b`                 |
| `a && b`     | Run `b` only if `a` returns zero                     |
| `a || b`     | Run `b` only if `a` returns nonzero                  |
| `a ; b`      | Run `b` after `a` regardless of status               |
| `a &`        | Start `a` in the background and return to the prompt |
| `a < file`   | Read command stdin from a file                       |
| `a > file`   | Replace a file with command stdout                   |
| `a >> file`  | Append command stdout to a file                      |
| `a 2> file`  | Replace a file with command stderr                   |
| `a 2>> file` | Append command stderr to a file                      |
| `a 2>&1`     | Send stderr to the current stdout destination        |
| `a &> file`  | Replace a file with both stdout and stderr           |
| `a 1>&2`     | Send stdout to the current stderr destination        |
| `a N>&-`     | Close descriptor 0, 1, or 2                          |
| `a <<WORD`   | Read multiline input through a heredoc               |

Redirection is supported on every pipeline stage. Stateless `echo`, `printf`, and `pwd`, plus plugin commands declared pipeline-safe, can run in pipelines and background jobs. State-changing built-ins remain in the shell process Background launch returns zero; use `wait` for its eventual status.

```plaintext
command 2> error.log
command > output.log 2>&1
command &> output.log
command &> output.log &
producer | consumer > output.log 2> error.log &
```

Redirections are applied from left to right: `> output.log 2>&1` sends both streams to the file, while `2>&1 > output.log` keeps stderr at the original stdout destination. The `2` must touch `>`; in `command 2 > file`, it is an ordinary argument. Quoted or escaped operators remain literal arguments. Stderr can be redirected on any real pipeline command, including before a Python capture endpoint. Python variable endpoints themselves do not accept stderr redirection.

Standalone built-ins and plugin commands support these output redirections, except the session-control commands `source`, `deactivate`, `verbose`, and `welcome`, which continue to reject redirection. Only stdout and stderr output redirections listed above are supported; arbitrary descriptor manipulation is rejected.

## Expansion

Arguments receive these expansions before execution:

* `$NAME` and `${NAME}` session variables, falling back to the environment
* `$?`, `$$`, `$!`, `$0`, `$1` onward, and `$@`
* nested `$(command)` substitution
* `~` user-home expansion
* filesystem globs using `*`, `?`, and `[...]`

Unmatched globs remain literal. Expansion also applies to redirection paths. Native Python has separate `$NAME` behavior described in [Python integration](python-integration.md).

## Built-ins

| Commands                                                         | Behavior                                                         |
| ---------------------------------------------------------------- | ---------------------------------------------------------------- |
| `cd [DIRECTORY]`, `cd -`, `pwd`                                  | Change directory, return to the previous directory, or print cwd |
| `pushd [DIRECTORY]`, `popd`, `dirs`                              | Push, pop, swap, or display the directory stack                  |
| `export [NAME[=VALUE] ...]`, `unset NAME ...`                    | Export values or remove session/environment names                |
| `history [COUNT]`, `history -c`                                  | List recent commands or clear pyesh history                      |
| `alias [NAME[=COMMAND] ...]`, `unalias NAME ...`, `unalias -a`   | Define/list/inspect or remove session aliases                    |
| `echo [-n] [TEXT ...]`, `printf [--] FORMAT [ARG ...]`           | Portable text output                                             |
| `read [-r] [NAME ...]`                                           | Read a line into native Python string variables                  |
| `jobs`, `wait [%JOB ...]`, `fg [%JOB]`, `bg [%JOB]`              | Inspect, wait for, foreground, or resume jobs                    |
| `kill [-s SIGNAL or -SIGNAL] PID or %JOB ...`, `kill -l`         | Signal a process or job; list signal names                       |
| `command [--] COMMAND ...`, `command -v NAME`, `command -V NAME` | Bypass aliases or inspect resolution                             |
| `type [-a] NAME ...`, `where NAME ...`                           | Describe command resolution or list all matches                  |
| `source FILE`, `deactivate`                                      | Activate/restore a venv or execute a pyesh command file          |
| `verbose [on\|off\|status]`, `welcome [on\|off\|status]`         | Control tracing and the welcome splash                           |
| `plugins`, `help [TOPIC]`, `man [TOPIC]`                         | Inspect enabled plugins and built-in help                        |
| `exit [STATUS]`                                                  | Exit with STATUS modulo 256, or the last status if omitted       |
| `shift [COUNT]`                                                  | Remove positional arguments                                      |
| `set -o pipefail`, `set +o pipefail`                             | Control pipeline failure status                                  |
| `disown [%JOB ...]`                                              | Remove jobs from shell shutdown management                       |
| `exec COMMAND ...`                                               | Replace the shell on POSIX, or run then exit on Windows          |

`cd`, environment changes, and venv activation affect the hosting process. Aliases and the directory stack belong to the session. Failed directory changes leave the stack and previous directory intact. `pushd` without a directory swaps cwd with the top entry; `dirs` prints cwd first. `PWD` and `OLDPWD` track successful directory changes.

Native Python values are the session variable store. `export NAME` copies its string representation into the child environment; `unset` removes both forms. Lists and tuples expand to multiple unquoted command arguments.

Aliases expand only at a shell command's first word, before argument expansion. They can call other aliases; cycles are rejected, and a direct self-alias such as `alias echo='echo prefix'` expands once. Values must be one command with arguments, without pipeline, sequencing, background, or redirection operators. For example:

```plaintext
alias greet='echo hello'
greet world
command echo without-the-alias
unalias greet
```

Put aliases that should be available in every interactive session in `~/.pyeshrc`, one command per line. For example:

```plaintext
alias ll='ls -la'
alias gs='git status'
alias up='cd ..'
```

`type` checks aliases, core built-ins, enabled plugin commands, then PATH. `type -a` and `where` show all matches. `command` bypasses alias expansion for its operand but retains built-in/plugin resolution. `command -v` prints the resolved name/path; `command -V` describes it.

History is shared by the API and interactive shell. `history -c` clears pyesh's in-memory history and the next prompt's navigation; normal interactive shutdown writes the cleared history plus subsequent commands to `.pyesh_history`. Startup and sourced file contents are not separately added. No other shell's history is touched.

`echo` joins arguments with spaces; only an initial `-n` is special, and backslashes are literal. `printf` supports `%s`, `%b` (escaped string), `%d`, `%i`, `%f`, and `%%`, fixed flags/width/precision, and repeated formatting for extra arguments. Missing values default to empty strings or zero. Common backslash escapes, octal `\0NNN`, and hex `\xHH` are supported; unsupported conversions return an error. This is a bounded subset of Bash printf, without `%q`, `%n`, `*` widths, or `\c`.

`read` defaults to `REPLY`, preserving the whole line without its newline. Named variables split whitespace; the final name receives the remainder and missing fields become empty strings. Backslash escapes and backslash-newline continuation are handled unless `-r` is used. `read` supports `< FILE`, returns 1 at EOF (including a partial final line), and stores strings in the native Python namespace. `__` names are reserved. For example:

```plaintext
read -r message < message.txt
print(message)
@message | python -c "import sys; print(sys.stdin.read().upper())"
```

`man` resolves pyesh topics first, otherwise starts the operating-system manual program; use a section such as `man 1 printf` to access a system topic sharing a built-in name.

## Jobs and terminal control

Job IDs are session-local and are written as `%1`, `%2`, and so on. `jobs` shows IDs, first-process PIDs, Running/Stopped/Done states, and command text. Completed statuses remain available until consumed by `wait` or `fg`. Bare `wait` waits for all recorded jobs and returns the final selected status; `wait %1 %2` selects jobs explicitly. A stopped job returns 128 plus its stop signal and remains tracked. Ctrl+C during `wait` returns 130 without terminating the jobs.

On POSIX, each external pipeline runs in its own process group. In the interactive CLI, foreground jobs receive terminal ownership. Ctrl+Z stops the foreground group; `bg` resumes it in the background, while `fg` resumes it with terminal access and waits. Both default to the latest active job. pyesh restores its terminal ownership/settings after a foreground job finishes or stops. `kill %1` sends TERM to the pipeline group; `kill -KILL %1` forces termination, and positive numeric PIDs target individual processes.

Interactive POSIX background commands inherit terminal stdin: a command trying to read it normally stops until brought to the foreground. API sessions and non-terminal background execution use the null device unless `< FILE` is supplied. Output stays attached unless redirected. On Windows, launch/list/wait/foreground-wait and supported process signals work, but POSIX stop/resume and terminal ownership are unavailable; `bg` reports that limitation. `kill %JOB` targets each recorded process on Windows.

Python variable pipelines remain foreground-only and do not participate in terminal job control. On exit, pyesh warns once about stopped jobs, then hangs up managed jobs with a bounded grace period; `exit --force` skips the warning. Use `disown` for jobs that should survive. The job manager reaps children while retaining completed statuses; long-lived sessions should use `wait` to discard consumed records.

## Exit statuses and errors

The status of the final executed foreground command is used by `&&`, `||`, the automation API, and the prompt's `{status}` field. Built-ins return nonzero for failures, so `cd missing && next` skips `next`. Invalid built-in usage generally returns 2, operating errors return 1. A command missing from `PATH` returns 127. An operating-system launch failure returns 126. Diagnostics are written to stderr and colored red when stderr is an interactive color terminal.

## Native scripts and Python control flow

Run source with `pyesh -c COMMAND`, `pyesh FILE.pyesh`, or `pyesh -`. Non-interactive modes do not load startup files unless `--startup` is supplied. Python compound statements support multiline input. The Python namespace exposes `sh(command)`, `capture(command, type="str")`, `argv`, and `env`.
