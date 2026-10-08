# __init__.py
__version__ = "1.0.0"

__all__ = ["PyeshSession", "__version__", "run_command"]


def __getattr__(name):
    """Load the automation API only when one of its exports is requested."""
    if name in ("PyeshSession", "run_command"):
        from .api import PyeshSession, run_command

        globals().update(PyeshSession=PyeshSession, run_command=run_command)
        return globals()[name]
    raise AttributeError("module {0!r} has no attribute {1!r}".format(__name__, name))
