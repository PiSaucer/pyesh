# _job_child.py

import os
import signal
import sys

def main() -> None:
    """Configure the requested process group and execute the child.

    Returns:
        None. A successful call replaces the helper process.
    """
    group, error_fd = int(sys.argv[1]), int(sys.argv[2])
    os.set_inheritable(error_fd, False)
    try:
        os.setpgid(0, group)
        for name in ("SIGINT", "SIGQUIT", "SIGTSTP", "SIGTTIN", "SIGTTOU", "SIGPIPE"):
            signal.signal(getattr(signal, name), signal.SIG_DFL)
        os.execvpe(sys.argv[3], sys.argv[3:], os.environ)
    except OSError as error:
        os.write(error_fd, str(error.errno).encode("ascii"))
        os._exit(127)

if __name__ == "__main__":
    main()
