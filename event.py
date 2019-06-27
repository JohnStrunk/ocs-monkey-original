"""
A simple event-based execution engine.

Events are actions that are to be executed at a specific time (in the future).
An instance of Dispatcher maintains a queue of pending future events that will
be executed when their time arrives.
"""

import abc
import logging
import queue
import time
from typing import Callable, List  # pylint: disable=unused-import


LOGGER = logging.getLogger(__name__)

class Dispatcher:
    """
    Dispatcher tracks and runs events.

    Events will be executed at or after their scheduled time. In the normal
    case, they will be executed very close to the scheduled time. However, the
    dispatcher is single-threaded and runs each Event to completion. Therefore,
    if there are many events scheduled for around the same time, some may get
    delayed due to Event processing overhead. Events will be executed in order,
    however.

    Events with the same timestamp have an undefined ordering.

    The standard way to use this class is to:
    - Create the Dispatcher
    - Add one or more Events
    - Call Dispatcher.run()

    Events have the option of scheduling future events (by returning them from
    Event.execute()). This means that as long as there are more Events scheduled
    in the future, run() will continue to execute. Once the queue is empty,
    run() will return since all Events have been processed.
    """

    # All scheduled Events are tracked in this PriorityQueue, ordered by
    # increasing Event timestamp (Event.when).
    _event_queue: 'queue.PriorityQueue[Event]'

    def __init__(self) -> None:
        """Create a new Dispatcher."""
        self._event_queue = queue.PriorityQueue()

    def add(self, *events: 'Event') -> None:
        """
        Add event(s) to the queue.

        Parameters:
            events: The events to be scheduled

        """
        for event in events:
            LOGGER.debug("enqueue: %s", event)
            self._event_queue.put(event)

    def run(self) -> None:
        """Process Events until the queue is empty."""
        try:
            while True:
                event = self._event_queue.get_nowait()
                now = time.time()
                delta = event.when - now
                if delta > 0:
                    time.sleep(delta)
                LOGGER.debug("execute: %s", event)
                self.add(*event.execute())
        except queue.Empty:
            pass


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

    def __str__(self) -> str:
        """Return string representation of an Event."""
        return f"{self.when}"

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


class Periodic(Event):  # xpylint: disable=too-few-public-methods
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
        self._action = [action]
        self._interval = interval
        super().__init__(when=time.time() + self._interval)

    def execute(self) -> 'List[Event]':
        """Execute the supplied periodic action."""
        if self._action[0]():
            return [Periodic(self._interval, self._action[0])]
        return []
