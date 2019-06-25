"""Defines the Event class."""

import abc
from typing import Callable, List  # pylint: disable=unused-import


class Event(abc.ABC):
    """Event is some action that should be executed at a specific time."""

    # Time at which this event should be triggered
    _when: float

    def __init__(self, when: float) -> None:
        """
        Initialize an Event with its time.

        Parameters:
          time: The time of this event (float since epoch)

        """
        self._when = when

    @abc.abstractmethod
    def execute(self) -> 'List[Event]':
        """
        Execute the event's action, returning a list of 0 or more new Events.

        Returns:
          A list of one or more new Events to be scheduled.

        """
        return []

    @property
    def when(self) -> float:
        """Get the time for this Event."""
        return self._when

    def __eq__(self, other: object) -> bool:
        """Equal."""
        if not isinstance(other, Event):
            return NotImplemented
        return self.when == other.when

    def __ne__(self, other: object) -> bool:
        """Not equal."""
        if not isinstance(other, Event):
            return NotImplemented
        return self.when != other.when

    def __lt__(self, other: object) -> bool:
        """Less."""
        if not isinstance(other, Event):
            return NotImplemented
        return self.when < other.when

    def __le__(self, other: object) -> bool:
        """Less or equal."""
        if not isinstance(other, Event):
            return NotImplemented
        return self.when <= other.when

    def __gt__(self, other: object) -> bool:
        """Greater."""
        if not isinstance(other, Event):
            return NotImplemented
        return self.when > other.when

    def __ge__(self, other: object) -> bool:
        """Greater or equal."""
        if not isinstance(other, Event):
            return NotImplemented
        return self.when >= other.when
