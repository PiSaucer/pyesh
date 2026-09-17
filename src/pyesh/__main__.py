# __main__.py
# Entry point for the pyesh command-line application
# python -m pyesh

import sys
from .cli import main
if __name__ == "__main__":
    sys.exit(main())
