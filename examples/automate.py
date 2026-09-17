# automate.py
# Automate a stateful pyesh session through its public Python API.

from pyesh import PyeshSession

def main() -> int:
    """Run a short automation sequence and return its final status."""
    session = PyeshSession(verbose=True)
    return session.run_all(
        ["pwd", "./examples/hello.py", "./examples/hello.sh | grep Bash"],
        stop_on_error=True,
    )

if __name__ == "__main__":
    raise SystemExit(main())
