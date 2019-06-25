"""
A simple event-based execution engine.

Events are actions that are to be executed at a specific time (in the future).
An instance of Dispatcher maintains a queue of pending future events that will
be executed when their time arrives.
"""

from .dispatcher import Dispatcher
from .event import Event
from .periodic import OneShot, Periodic
