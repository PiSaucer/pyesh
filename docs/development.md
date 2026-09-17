# Development and releases

## Set up

```bash
python -m pip install -e '.[dev]'
```

The development extra installs artifact build and validation tools. On Windows, install `.[windows-executable]` to build the standalone executable from the checked-in PyInstaller spec. Rich and prompt-toolkit provide terminal presentation and interactive editing at runtime.

## Validate changes

```bash
python -m compileall -q src
python -m build
git diff --check
```

Keep code compatible with Python 3.9.

## Repository layout

```plaintext
src/pyesh/    Package source
examples/     Runnable cross-runtime examples
docs/         User and developer documentation
```

## Versioning

The authoritative version is `pyesh.__version__` in `src/pyesh/__init__.py`. Package versions use semantic versioning without a leading `v`. Git release tags use `vMAJOR.MINOR.PATCH` and must match the package version after removing the `v`. The publish workflow validates the tag directly against the version assignment without importing runtime dependencies.

Update `CHANGELOG.md` before release. Publishing is gated by the repository's release workflow and must not occur from an ordinary branch push.

## Publishing

`.github/workflows/publish.yml` runs only for a published GitHub Release. It validates the tag, builds and checks both Python artifacts, uploads them to the GitHub Release, and publishes through the protected `pypi` environment using trusted publishing. After publication, its Windows job builds a standalone `pyesh-windows-x64.exe`, verifies `--version`, and attaches it to the same GitHub Release.

The Windows executable is configured in `packaging/pyinstaller/pyesh-windows.spec`. Add future PyInstaller customization there, including icons, Windows version resources, bundled data, binaries, hidden imports, runtime hooks, exclusions, and UPX settings. The adjacent `pyesh_launcher.py` is the stable absolute-import entry point used by the spec.

## Contribution boundaries

* Preserve direct argument-list execution; do not introduce `shell=True`.
* Keep built-ins, parsing, execution, history, configuration, and presentation focused and separate.
* Preserve `pyesh` and `python -m pyesh` equivalence.
* Document only behavior that is actually implemented.
* Do not commit user configuration, history, credentials, caches, build output, or generated distributions.
