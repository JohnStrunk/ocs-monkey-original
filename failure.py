"""
Framework for chaos-monkey failures.

This file contains the base classes for failures that can be injected by the
chaos framework.
"""

import abc


class Error(Exception):
    """Base class for execptions from the failure framework."""


class Failure(abc.ABC):
    """
    A specific instance of a type of Failure.

    For example, a "type" of failure could be deleting a pod. This Failure
    object, being a specific instance, would be deleting a specific pod.
    """

    @abc.abstractmethod
    def is_safe(self) -> bool:
        """Determine if SUT should survive this Failure."""

    @abc.abstractmethod
    def invoke(self) -> None:
        """Invoke the failure on the system."""

    def repair(self) -> None:
        """Repair damage to the infrastructure caused by the failure."""

    @abc.abstractmethod
    def mitigated(self, timeout_seconds: float = 0) -> bool:
        """
        Determine (and/or) wait for the SUT to mitigate the failure.

        Parameters:
            timeout_seconds: Maximum time to wait for the SUT to mitigate

        Returns:
            True if the failure has been mitigated

        """


class FailureType(abc.ABC):  # pylint: disable=too-few-public-methods
    """
    Defines a "type" or "class" of failure that could be invoked.

    This defines a type of failure, for example deleting an OSD pod. When the
    FailureType is create()-ed, it will generate a specific instance of this
    type of failure. The created Failure (following the above example) would be
    for a specific pod. It is this specific Failure that would then be inkoked.
    """

    @abc.abstractmethod
    def get(self) -> Failure:
        """
        Get an instance of this type of failure.

        The failure instance that is returned is expected to be "safe" (i.e.,
        failure.is_safe() should return True).

        Returns:
            The new Failure instance.

        """
