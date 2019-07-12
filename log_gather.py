"""Gather log files from the cluster."""

import abc
import logging
from typing import List  # pylint: disable=unused-import

_collectors: 'List[Collector]' = []
_LOGGER = logging.getLogger(__name__)

class Collector(abc.ABC):
    """Collectors grab logs upon failure."""

    def __init__(self, name: str) -> None:
        """Initialize the collecter by recording its name."""
        self._name = name
        super().__init__()

    @abc.abstractmethod
    def gather(self, path: str) -> bool:
        """
        Gather the logs.

        Parameters:
            path: Path into which logs should be written

        Returns:
            True if logs were successfully collected.

        """

    def __str__(self) -> str:
        """Return the name of the collector as teh string representation."""
        return self._name

def gather(path: str) -> None:
    """
    Gather all log files.

    Parameters:
        path: Path into which log files should be placed

    """
    for collector in _collectors:
        _LOGGER.info("Gathering logs with %s", collector)
        if collector.gather(path):
            _LOGGER.info("...success")
        else:
            _LOGGER.warning("Failed collecting logs with %s", collector)

def add(collector: Collector) -> None:
    """Add a log collector."""
    _collectors.append(collector)
