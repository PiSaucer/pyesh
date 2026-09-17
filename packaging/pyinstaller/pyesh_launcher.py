# pyesh_launcher.py
# Entry point for the standalone executables.

import sys

from pyesh.cli import main
from pyesh._builtin_child import main as builtin_child_main

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--_pyesh-builtin-child":
        raise SystemExit(builtin_child_main(sys.argv[2:]))
    raise SystemExit(main())
