#!/usr/bin/env python3
"""Chaos monkey randomized fault injector."""

import argparse
import logging
import os
import random
import time
from typing import List, Optional

import failure
import failure_ocs

CLI_ARGS: argparse.Namespace
RUN_ID = random.randrange(999999999)

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
        except failure.NoSafeFailures as ex:
            print("unsafe: %s (%s)", fail_type, ex)
            # pass
    raise failure.NoSafeFailures

def main() -> None:
    """Inject randomized faults."""

    # Parameters we should be able to configure
    prob_addl_failure = 0.25
    mttf = 150
    mitigation_timeout = 15 * 60
    steady_state_check_interval = 30
    ocs_namespace = "openshift-storage"

    # Assemble list of potential FailureTypes to induce
    failure_types: List[failure.FailureType] = [
        # CSI driver component pods
        failure_ocs.DeletePodType(namespace=ocs_namespace,
                                  labels={"app": "csi-rbdplugin"}),
        failure_ocs.DeletePodType(namespace=ocs_namespace,
                                  labels={"app": "csi-rbdplugin-provisioner"}),
        # ceph component pods
        failure_ocs.DeletePodType(namespace=ocs_namespace,
                                  labels={"app": "rook-ceph-mon"}),
        failure_ocs.DeletePodType(namespace=ocs_namespace,
                                  labels={"app": "rook-ceph-osd"}),
        # operator component pods
        failure_ocs.DeletePodType(namespace=ocs_namespace,
                                  labels={"app": "rook-ceph-operator"}),
        failure_ocs.DeletePodType(namespace=ocs_namespace,
                                  labels={"name": "ocs-operator"}),
    ]

    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--log-dir",
                        default=os.getcwd(),
                        type=str,
                        help="Path to use for log files")
    global CLI_ARGS  # pylint: disable=global-statement
    CLI_ARGS = parser.parse_args()

    log_dir = os.path.join(CLI_ARGS.log_dir, f'ocs-monkey-{RUN_ID}')
    os.mkdir(log_dir)

    handlers = [
        logging.FileHandler(os.path.join(log_dir, "runner.log")),
        logging.StreamHandler()
    ]
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logging.Formatter.converter = time.gmtime
    formatter = \
        logging.Formatter("%(asctime)s %(name)s - %(levelname)s - %(message)s")
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logging.info("starting execution-- run id: %d", RUN_ID)
    logging.info("program arguments: %s", CLI_ARGS)
    logging.info("log directory: %s", log_dir)

    # A list of the outstanding failures that we (may) need to repair. New
    # failures are appended, and repairs are done from the end as well (i.e.,
    # it's a stack).
    pending_repairs: List[failure.Failure] = []

    while True:
        fail_instance: Optional[failure.Failure] = None
        try:
            fail_instance = get_failure(failure_types)
            logging.info("invoking failure: %s", fail_instance)
            fail_instance.invoke()
            pending_repairs.append(fail_instance)
        except failure.NoSafeFailures:
            pass

        if random.random() > prob_addl_failure or not fail_instance:
            # don't cause more simultaneous failures
            if fail_instance:  # we should await mitigation
                logging.info("awaiting mitigation")
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
            logging.info("making repairs")
            pending_repairs.reverse()
            for repair in pending_repairs:
                repair.repair()
            pending_repairs.clear()

            verify_steady_state()

            # TODO: We should have a better way to abstract this.
            # After all repairs have been made, ceph should become healthy
            assert failure_ocs.await_ceph_healthy(ocs_namespace, mitigation_timeout)

            # Wait until it's time for next failure, monitoring steady-state
            # periodically
            logging.info("pausing before next failure")
            ss_last_check = 0.0
            while random.random() > (1/mttf):
                if time.time() > ss_last_check + steady_state_check_interval:
                    verify_steady_state()
                    ss_last_check = time.time()
                time.sleep(1)

if __name__ == '__main__':
    main()
