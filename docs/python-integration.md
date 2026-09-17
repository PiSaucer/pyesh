# Native Python and typed pipelines

## Persistent Python input

Python assignments, imports, definitions, calls, and expressions can run directly at the prompt. Names remain available for the life of the session:

```plaintext
items = [1, 2, 3]
sum(items)
6
```

Compound statements use continuation input and provide Python-first control flow. The namespace includes `sh(command)`, `capture(command, type="str")`, `argv`, and the isolated `env` mapping.

At an interactive continuation prompt, indentation for the first line of a suite is optional. pyesh infers four spaces when an unindented line follows a header ending in `:`:

```plaintext
for x in range(5):
... print(x)
0
1
2
3
4
```

Leading whitespace supplied explicitly is preserved, and nested suite headers receive one additional inferred level.

A new bare name remains a shell command, preserving normal inputs such as `ls`. Known Python names and unambiguous Python syntax use the native namespace. Expression values other than `None` are printed with `repr`.

Shell-style environment references outside Python string literals become Python values:

```plaintext
print($HOME)
home = $HOME
```

A missing environment name becomes `None`. `$NAME` text inside a quoted Python string is unchanged.

## Typed assignment

`@name:type = expression` evaluates a Python expression, converts it through the selected datatype, and stores it under `name`:

```plaintext
@answer:int = "42"
@payload:json = {"ready": True}
```

Omitting `:type` selects `str`.

## Pipeline endpoints

An `@name:type` endpoint at the beginning provides bytes to a pipeline. At the end it captures stdout into the Python namespace:

```plaintext
words = ["alpha", "beta"]
@words:lines | grep beta | @match:str
```

Both endpoints may be used without an external command for a typed round trip:

```plaintext
payload = {"answer": 42}
@payload:json | @copy:json
```

Endpoints are valid only at pipeline edges and cannot be backgrounded. Stateless built-ins and plugin commands marked pipeline-safe execute as child processes; state-changing built-ins remain invalid in typed pipelines.

## Datatypes

| Type    | Encoding into a pipeline            | Decoding from a pipeline           |
| ------- | ----------------------------------- | ---------------------------------- |
| `str`   | UTF-8 of `str(value)`               | UTF-8 text with newlines preserved |
| `bytes` | Exact bytes-like value              | Exact `bytes`                      |
| `json`  | Sorted JSON plus newline            | Parsed JSON value                  |
| `lines` | Iterable items, one UTF-8 line each | `list[str]` using `splitlines()`   |
| `int`   | Decimal integer bytes               | Stripped decimal `int`             |
| `float` | Decimal float bytes                 | Stripped Python `float`            |

Missing variables, unsupported datatypes, invalid UTF-8, and failed numeric or JSON conversion produce an error without ending the interactive session.

## Capture and files

Normal capture:

```plaintext
printf "42\n" | @answer:int
```

Variable-first shorthand when the command has arguments:

```plaintext
@answer:int < echo "42"
```

A single word after `<` is a file path instead:

```plaintext
@notes:str < notes.txt
@config:json < config.json
```

Capture can retain the exact bytes in a file while also decoding the variable:

```plaintext
command | @text:str > output.txt
command | @raw:bytes >> archive.bin
```

The file is written before decoding, so raw output remains available if typed conversion fails. A producer variable can also be written directly:

```plaintext
@raw:bytes > output.bin
```

## Trust boundary

Native Python executes with the same privileges and access as pyesh. Only run trusted Python source. Typed pipeline conversion is serialization, not a sandbox.
