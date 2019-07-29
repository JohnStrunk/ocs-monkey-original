#!/usr/bin/env python3
"""Chaos monkey randomized fault injector."""

import random
import time
from typing import List, Optional

import failure

def verify_steady_state() -> bool:
    """Verify the steady state hypothesis."""
    return True

def get_failure(types: List[failure.FailureType]) -> failure.Failure:
    """Get a failure instance that is safe to invoke."""
    random.shuffle(types)
    for fail_type in types:
        try:
            instance = fail_type.get()
            return instance
        except failure.NoSafeFailures:
            pass
    raise failure.NoSafeFailures

def main() -> None:
    """Inject randomized faults."""

    # Parameters we should be able to configure
    prob_addl_failure = 0.1
    mttf = 300
    mitigation_timeout = 15 * 60
    steady_state_check_interval = 30

    # Assemble list of potential FailureTypes to induce
    failure_types: List[failure.FailureType] = []

    # A list of the outstanding failures that we (may) need to repair. New
    # failures are appended, and repairs are done from the end as well (i.e.,
    # it's a stack).
    pending_repairs: List[failure.Failure] = []

    while True:
        fail_instance: Optional[failure.Failure] = None
        try:
            fail_instance = get_failure(failure_types)
            fail_instance.invoke()
            pending_repairs.append(fail_instance)
        except failure.NoSafeFailures:
            pass

        if random.random() > prob_addl_failure or not fail_instance:
            # don't cause more simultaneous failures
            if fail_instance:  # we should await mitigation
                time_remaining = mitigation_timeout
                while time_remaining > 0 and not fail_instance.mitigated():
                    sleep_time = 10
                    verify_steady_state()
                    time.sleep(10)
                    time_remaining -= sleep_time
                # Make sure the SUT has recovered (and not timed out)
                if not fail_instance.mitigated():
                    # This shouldn't be an assert... but what should we do?
                    assert False

            verify_steady_state()

            # Repair the infrastructure from all the failures, starting w/ most
            # recent and working back.
            pending_repairs.reverse()
            for repair in pending_repairs:
                repair.repair()
            pending_repairs.clear()

            verify_steady_state()

            # Wait until it's time for next failure, monitoring steady-state
            # periodically
            ss_last_check = 0.0
            while random.random() > (1/mttf):
                if time.time() > ss_last_check + steady_state_check_interval:
                    verify_steady_state()
                    ss_last_check = time.time()
                time.sleep(1)

if __name__ == '__main__':
    main()
