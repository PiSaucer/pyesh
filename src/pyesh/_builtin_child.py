# _builtin_child.py

import sys
from pathlib import Path
from typing import List, Optional

# Resolve the installed/source package beside this file, independent of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pyesh.builtins import run_builtin
from pyesh.plugins import PluginManager

def main(arguments: Optional[List[str]] = None) -> Optional[int]:
    """Run a stateless built-in or an explicitly selected plugin command."""
    values = sys.argv[1:] if arguments is None else arguments
    if len(values) >= 3 and values[0] == "--plugin":
        manager = PluginManager()
        manager.load_enabled([values[1]])
        return manager.run(values[2:]) if not manager.errors else 1
    if not values or values[0] not in ("echo", "printf", "pwd"):
        return 2
    return run_builtin(values)

if __name__ == "__main__":
    raise SystemExit(main())
