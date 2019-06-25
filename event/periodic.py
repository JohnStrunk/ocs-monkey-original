"""A simple time-based events."""

from typing import Callable, List  # pylint: disable=unused-import

from .event import Event


class OneShot(Event):
    """An event that calls a function at a specific time."""

    # The action function must be a list to work around 2 issues:
    #  - mypy doesn't like assignment to a function variable
    #  - The a bare function is assumed to be a method that would receive self
    # So, we just embed it in a single element list to avoid both problems.
    _action: List[Callable[[], None]]

    def __init__(self, when: float, action: 'Callable[[], None]') -> None:
        """
        Define an event that executes at a specific time.

        Parameters:
            when: The time when the action should execute
            action: A function to call that performs the action

        """
        self._action = [action]
        super().__init__(when=when)

    def execute(self) -> 'List[Event]':
        """Execute the supplied periodic action."""
        self._action[0]()
        return []

class Periodic(Event):  # pylint: disable=too-few-public-methods
    """An event that fires at a constant rate."""

    # The action function must be a list to work around 2 issues:
    #  - mypy doesn't like assignment to a function variable
    #  - The a bare function is assumed to be a method that would receive self
    # So, we just embed it in a single element list to avoid both problems.
    _action: List[Callable[[], bool]]
    _interval: float

    def __init__(self, interval: float, action: 'Callable[[], bool]') -> None:
        """
        Define an event that executes at a fixed interval.

        Parameters:
            interval: The time in seconds between executions
            action: A function to call with each execution.

        If the action function, fn() -> bool, returns True, the event will be
        scheduled for the next time interval. If False, this will be the last
        execution.

        """
        import time
        self._action = [action]
        self._interval = interval
        super().__init__(when=time.time() + self._interval)

    def execute(self) -> 'List[Event]':
        """Execute the supplied periodic action."""
        if self._action[0]():
            return [Periodic(self._interval, self._action[0])]
        return []
