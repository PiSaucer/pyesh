# Configuration and user files

Run `pyesh --init` to create missing starter files. Existing content is never overwritten.

| File                     | Purpose                                    |
| ------------------------ | ------------------------------------------ |
| `~/.pyeshenv`            | Environment assignments                    |
| `~/.pyesh_paths`         | Directories prepended to `PATH`            |
| `~/.pyesh_profile`       | General startup commands                   |
| `~/.pyeshrc`             | Interactive startup commands               |
| `~/.pyesh_prompt`        | Prompt format template                     |
| `~/.pyesh_welcome`       | Welcome startup toggle and splash template |
| `~/.pyesh_plugins`       | Enabled plugin entry-point names           |
| `~/.pyesh_profiles.json` | Named terminal and session profiles        |
| `~/.pyesh_history`       | Private persistent command history         |

Set `PYESH_HOME` to relocate all nine files. pyesh does not read or modify `.zshrc`, Bash startup files, or PowerShell profiles.

## JSON profiles

Use `pyesh --profile NAME` to select a named profile. With no command-line selection, `default_profile` is used. `pyesh --list-profiles` lists available names and marks the default. A missing profile file means normal built-in and user-file defaults are used.

```json
{
  "version": 1,
  "default_profile": "work",
  "profiles": {
    "work": {
      "prompt": "{venv_segment}{user}:{folder}{branch_segment} $",
      "history_limit": 5000,
      "verbose": false,
      "plugins": ["git-tools", "project-tools"],
      "environment": {
        "EDITOR": "vim",
        "PYESH_MODE": "work"
      },
      "paths": ["~/bin", "$PROJECTS/tools"],
      "startup_commands": ["alias ll='ls -la'"],
      "welcome": {
        "enabled": true,
        "template": "[bold cyan]Work shell[/bold cyan] in {directory}"
      },
      "terminal": {
        "colors": true,
        "syntax_highlighting": true,
        "completion": true,
        "complete_while_typing": false,
        "mouse_support": false,
        "styles": {
          "command": "bold #00afff",
          "builtin": "bold #00d7d7",
          "operator": "bold #ff5fff",
          "string": "#5fd75f",
          "variable": "#d787ff",
          "option": "#ffd75f",
          "number": "#5fd7ff"
        }
      }
    },
    "minimal": {
      "prompt": ">",
      "plugins": [],
      "welcome": {"enabled": false},
      "terminal": {"colors": false, "completion": false}
    }
  }
}
```

All settings are optional. A profile `plugins` array replaces `.pyesh_plugins`; omitting it keeps the existing file-based plugin selection. An empty array therefore explicitly loads no plugins. Plugin names remain installed `pyesh.plugins` entry-point names and are never installed or enabled implicitly. `--safe` takes precedence and loads no plugin code.

Profile environment values expand existing environment variables and `~`. Profile PATH entries are expanded, deduplicated, and prepended after `.pyesh_paths`. Profile startup commands run after `.pyeshrc` and any active environment startup files; login mode also loads `.pyesh_profile`. JSON is validated strictly: misspelled settings, invalid types, unknown style tokens, and unsupported schema versions produce useful diagnostics. Interactive startup continues into a recovery shell with status 2; non-interactive startup fails immediately.

## Loading order

Interactive startup applies:

1. `.pyeshenv`
2. `.pyesh_paths`
3. enabled plugins, unless `--safe` is used
4. existing history
5. `.pyeshrc`
6. active-venv `.pyeshrc`, when present
7. prompt rendering

With `--login`, `.pyesh_profile` is loaded before `.pyeshrc`, and an active virtual environment's `.pyesh_profile` is loaded before its `.pyeshrc`. Non-interactive execution skips startup files unless `--startup` is supplied; `--no-startup` skips all user-controlled startup and plugin loading.

Selected profile environment and PATH overrides are applied after steps 1 and 2. Profile plugin selection is applied at step 3, and profile startup commands run after step 6 (and after active-venv startup files). Profile prompt, welcome, history, and terminal settings override their corresponding defaults.

The welcome configuration is loaded before startup commands. If enabled after `.pyesh_profile` and `.pyeshrc` finish, its splash is shown before the first prompt.

Blank lines and lines whose first non-whitespace character is `#` are ignored.

## Environment and PATH

`.pyeshenv` contains one `NAME=value` assignment per active line. Values expand existing environment references and `~`:

```plaintext
EDITOR=vim
PROJECTS=~/Projects
```

`.pyesh_paths` contains one directory per line. Expanded, unique entries are prepended to the existing `PATH`:

```plaintext
~/.local/bin
$PROJECTS/bin
```

## Startup commands

`.pyesh_profile` and `.pyeshrc` contain ordinary pyesh command lines. They may change directory, enable tracing, run commands, or define native Python names:

```plaintext
verbose off
project_name = "demo"
```

## Prompt template

The first active line in `.pyesh_prompt` is formatted for every prompt. Fields:

| Field              | Value                                                  |
| ------------------ | ------------------------------------------------------ |
| `{user}`           | Current username                                       |
| `{host}`           | Hostname before its first dot                          |
| `{folder}`         | Current directory's final component (`~` at home)      |
| `{path}`           | Complete current path                                  |
| `{branch}`         | Git branch or short detached commit; empty outside Git |
| `{branch_segment}` | Leading space plus parenthesized branch, or empty      |
| `{status}`         | Previous command status                                |
| `{venv}`           | Active `VIRTUAL_ENV` directory name, or empty          |
| `{venv_segment}`   | Parenthesized venv name plus trailing space, or empty  |
| `{platform_icon}`  | Platform icon (`` macOS, `🐧` Linux, `` Ubuntu, `` SteamOS, `` Windows) |

Default:

```plaintext
{platform_icon} {venv_segment}{user}@{host} {folder}{branch_segment} %
```

Custom example:

```plaintext
[{status}] {user}:{folder}{branch_segment} $
```

pyesh appends a trailing space when missing. Unknown or malformed format fields are reported as configuration errors. The last parenthesized prompt segment is colored green in an interactive color terminal.

## History

History is newline-delimited and bounded by `ShellConfig.history_limit` (default 1,000). Newlines within commands are normalized to spaces. Writes are atomic, and pyesh requests owner-only permissions where supported. It never modifies another shell's history.

## Welcome splash

`.pyesh_welcome` begins with an activation setting:

```plaintext
enabled=true
```

The welcome splash is enabled by default. Set this to `enabled=false` to hide
it on startup.

Everything after that setting is an optional multiline format template. When it is empty, pyesh uses its built-in ASCII splash. Available fields are:

* `{version}`
* `{python_version}`
* `{python_executable}`
* `{platform}`
* `{directory}`
* `{venv}`

Templates support Rich console markup, so colors and styles can be customized:

Example:

```plaintext
enabled=true
[bold magenta]Welcome to pyesh {version}[/bold magenta]
[cyan]Python {python_version}:[/cyan] {python_executable}
[green]Working in {directory} using venv {venv}[/green]
```

Within a session, `welcome` displays the splash immediately. `welcome on` and `welcome off` update `enabled=` atomically while preserving comments and the custom template; `welcome status` only reads the active setting. Startup files run before the automatic splash decision, so they may also override the loaded setting.
