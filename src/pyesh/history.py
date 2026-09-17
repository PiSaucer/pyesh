# history.py

from collections import deque
from typing import Deque, Iterable, List

class CommandHistory:
    """A bounded, in-memory command history for the initial shell."""

    def __init__(self, limit: int = 1_000) -> None:
        """Create an empty history.

        Args:
            limit: Maximum number of commands to retain.

        Raises:
            ValueError: If ``limit`` is not positive.
        """
        if limit <= 0:
            raise ValueError("history limit must be positive")
        self._entries: Deque[str] = deque(maxlen=limit)

    def add(self, command: str) -> None:
        """Add a non-blank command.

        Args:
            command: Command text to normalize and retain.

        Returns:
            None.
        """
        command = command.strip()
        if command:
            self._entries.append(command)

    def clear(self) -> None:
        """Clear this session's history only.

        Returns:
            None.
        """
        self._entries.clear()

    def entries(self) -> List[str]:
        """Return a snapshot of commands from oldest to newest.

        Returns:
            A new list containing the retained commands.
        """
        return list(self._entries)

    def extend(self, commands: Iterable[str]) -> None:
        """Add several commands in iteration order.

        Args:
            commands: Command strings to add.

        Returns:
            None.
        """
        for command in commands:
            self.add(command)
