"""Defines the Dispatcher class."""

import queue
import time

from .event import Event

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

    def add(self, *events: Event) -> None:
        """
        Add event(s) to the queue.

        Parameters:
            events: The events to be scheduled

        """
        for event in events:
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
                self.add(*event.execute())
        except queue.Empty:
            pass
