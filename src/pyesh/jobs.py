# jobs.py

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional

def shell_status(code: int) -> int:
    """Normalize a subprocess return code.

    Args:
        code: Raw subprocess return code.

    Returns:
        Shell-style status, including signal offsets.
    """
    return 128 - code if code < 0 else code

@dataclass
class BackgroundJob:
    """Track the processes and runtime state of a background shell job."""
    processes: List[subprocess.Popen]
    text: str
    pgid: Optional[int] = None
    number: int = 0
    stopped: Dict[int, int] = field(default_factory=dict)
    terminal_settings: object = None
    condition: threading.Condition = field(default_factory=threading.Condition)

    @property
    def done(self) -> bool:
        """Return whether every child has exited.

        Returns:
            ``True`` when all child statuses are available.
        """
        return all(process.returncode is not None for process in self.processes)

    @property
    def suspended(self) -> bool:
        """Return whether every live child is stopped.

        Returns:
            ``True`` for a fully suspended job.
        """
        active = [p for p in self.processes if p.returncode is None]
        return bool(active) and all(p.pid in self.stopped for p in active)

    @property
    def status(self) -> int:
        """Return the job's current shell status.

        Returns:
            Final-stage or stop-signal status.
        """
        if self.suspended:
            return 128 + next(iter(self.stopped.values()))
        return shell_status(self.processes[-1].returncode or 0)

    def refresh(self) -> None:
        """Refresh child state while holding the condition lock.

        Returns:
            None.
        """
        for process in self.processes:
            if process.returncode is not None:
                continue
            if os.name != "posix":
                process.poll()
                continue
            flags = os.WNOHANG | os.WUNTRACED | getattr(os, "WCONTINUED", 0)
            while True:
                pid, status = os.waitpid(process.pid, flags)
                if not pid:
                    break
                if os.WIFSTOPPED(status):
                    self.stopped[pid] = os.WSTOPSIG(status)
                elif os.WIFCONTINUED(status):
                    self.stopped.pop(pid, None)
                else:
                    process.returncode = os.waitstatus_to_exitcode(status)
                    self.stopped.pop(pid, None)
                    break

    def reap(self) -> None:
        """Reap children while retaining their status for ``wait``.

        Returns:
            None.
        """
        with self.condition:
            while not self.done:
                self.refresh()
                self.condition.notify_all()
                if not self.done:
                    self.condition.wait(0.03)

    def send(self, signum: int) -> None:
        """Send a signal to the job.

        Args:
            signum: Numeric signal value.

        Returns:
            None.
        """
        with self.condition:
            self.refresh()
            if self.done:
                raise ValueError("job has already completed")
            if self.pgid is not None:
                os.killpg(self.pgid, signum)
            else:
                for process in self.processes:
                    if process.returncode is None:
                        process.send_signal(signum)
            if signum == getattr(signal, "SIGCONT", None):
                self.stopped.clear()
            self.condition.notify_all()

    def wait(self, interrupt_job: bool = False) -> int:
        """Wait for completion or suspension.

        Args:
            interrupt_job: Forward interruption to the job when true.

        Returns:
            Current shell status.
        """
        with self.condition:
            while not self.done and not self.suspended:
                try:
                    self.condition.wait(0.05)
                except KeyboardInterrupt:
                    if not interrupt_job:
                        return 130
                    self.send(signal.SIGINT)
            return self.status

class JobTable:
    """Keep job identities private to a shell/API session."""
    
    def __init__(self) -> None:
        """Create an empty session-local job table."""
        self.jobs: Dict[int, BackgroundJob] = {}
        self.next_number = 1
        self.terminal_fd: Optional[int] = None

    def enable_terminal(self) -> None:
        """Attach job control to the current POSIX terminal when possible.

        Returns:
            None.
        """
        if os.name != "posix" or threading.current_thread() is not threading.main_thread():
            return
        try:
            fd = sys.stdin.fileno()
            if os.isatty(fd) and os.tcgetpgrp(fd) == os.getpgrp():
                self.terminal_fd = fd
        except (AttributeError, OSError, ValueError):
            pass

    def remember(self, job: BackgroundJob) -> None:
        """Assign and retain a session-local job number.

        Args:
            job: Job to retain.

        Returns:
            None.
        """
        if not job.number:
            job.number = self.next_number
            self.next_number += 1
        self.jobs[job.number] = job

    def track(self, processes, text, pgid=None, background=False):
        """Create and asynchronously reap a job.

        Args:
            processes: Pipeline subprocesses.
            text: Displayable command text.
            pgid: Optional POSIX process-group ID.
            background: Whether to retain the job immediately.

        Returns:
            The tracked job.
        """
        job = BackgroundJob(processes, text, pgid)
        if background:
            self.remember(job)
        threading.Thread(target=job.reap, daemon=True).start()
        return job

    def select(self, value: Optional[str] = None) -> BackgroundJob:
        """Select a retained job by ID or current-job shorthand.

        Args:
            value: Optional job selector.

        Returns:
            The selected job.
        """
        if value is None or value in ("%", "%+", "%%"):
            candidates = [job for job in self.jobs.values() if not job.done]
            if not candidates:
                raise ValueError("no current job")
            return candidates[-1]
        try:
            number = int(value.lstrip("%"))
            return self.jobs[number]
        except (ValueError, KeyError):
            raise ValueError("no such job: {0}".format(value)) from None

    def listing(self) -> List[str]:
        """Render retained jobs.

        Returns:
            Human-readable job lines.
        """
        lines = []
        for number, job in self.jobs.items():
            with job.condition:
                job.refresh()
                state = ("Done ({0})".format(job.status) if job.done else
                         "Stopped" if job.suspended else "Running")
                lines.append("[{0}] {1} {2}  {3}".format(
                    number, job.processes[0].pid, state, job.text))
        return lines

    def give_terminal(self, pgid: int) -> None:
        """Transfer terminal ownership to a process group.

        Args:
            pgid: Target POSIX process-group ID.

        Returns:
            None.
        """
        if self.terminal_fd is None:
            return
        previous = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
        try:
            os.tcsetpgrp(self.terminal_fd, pgid)
        finally:
            signal.signal(signal.SIGTTOU, previous)

    @contextmanager
    def terminal(self, job: BackgroundJob):
        """Temporarily grant a job terminal ownership.

        Args:
            job: Foreground job.

        Returns:
            A context manager restoring shell terminal state.
        """
        settings = None
        if self.terminal_fd is not None:
            import termios
            settings = termios.tcgetattr(self.terminal_fd)
            if job.terminal_settings is not None:
                termios.tcsetattr(self.terminal_fd, termios.TCSANOW, job.terminal_settings)
        try:
            if self.terminal_fd is not None:
                try:
                    self.give_terminal(job.pgid)
                except OSError:
                    # A very short-lived job may be reaped before handoff.
                    if not job.done:
                        raise
            yield
        finally:
            if self.terminal_fd is not None:
                import termios
                if job.suspended:
                    job.terminal_settings = termios.tcgetattr(self.terminal_fd)
                self.give_terminal(os.getpgrp())
                termios.tcsetattr(self.terminal_fd, termios.TCSANOW, settings)

    def foreground(self, job: BackgroundJob, resume: bool = True) -> int:
        """Run or resume a job in the foreground.

        Args:
            job: Job to foreground.
            resume: Send ``SIGCONT`` when appropriate.

        Returns:
            Job status.
        """
        if job.done:
            self.jobs.pop(job.number, None)
            return job.status
        with self.terminal(job):
            if resume and not job.done and os.name == "posix":
                try:
                    job.send(signal.SIGCONT)
                except ValueError:  # Completed between the check and signal.
                    pass
            status = job.wait(interrupt_job=True)
        if job.done:
            self.jobs.pop(job.number, None)
        elif job.suspended:
            self.remember(job)
        return status

    def wait_for(self, values: List[str]) -> int:
        """Wait for selected jobs or all retained jobs.

        Args:
            values: Job selectors; empty selects all.

        Returns:
            Last selected job status.
        """
        targets = [self.select(value) for value in values] if values else list(self.jobs.values())
        status = 0
        for job in targets:
            status = job.wait()
            if job.done:
                self.jobs.pop(job.number, None)
            elif status == 130:
                return status
        return status

    def disown(self, values: List[str]) -> None:
        """Remove jobs from shell lifecycle management.

        Args:
            values: Job selectors; empty selects the current job.

        Returns:
            None.
        """
        targets = [self.select(value) for value in values] if values else [self.select()]
        for job in targets:
            self.jobs.pop(job.number, None)

    def active(self) -> List[BackgroundJob]:
        """Return live retained jobs.

        Returns:
            Jobs with at least one live process.
        """
        return [job for job in self.jobs.values() if not job.done]

    def shutdown(self, timeout: float = 0.5) -> List[BackgroundJob]:
        """Hang up tracked jobs without blocking indefinitely.

        Args:
            timeout: Maximum grace period in seconds.

        Returns:
            Jobs still alive after the grace period.
        """
        for job in self.active():
            try:
                job.send(signal.SIGHUP if os.name == "posix" else signal.SIGTERM)
            except (OSError, ValueError):
                pass
        deadline = time.monotonic() + timeout
        while self.active() and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.active()
