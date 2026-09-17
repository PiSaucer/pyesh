# __init__.py
__version__ = "1.0.0"

# Expose api for importing as package
from .api import PyeshSession, run_command
__all__ = ["PyeshSession", "__version__", "run_command"]
