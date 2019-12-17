#!/usr/bin/env python3
"""Chaos monkey randomized fault injector."""

# pylint: disable=duplicate-code
import argparse
import logging
import os
import random
import time
from typing import List, Optional

import failure
import failure_ocs
import util

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
        except failure.NoSafeFailures:
            pass
    raise failure.NoSafeFailures

def await_mitigation(instance: failure.Failure,
                     timeout: float) -> bool:
    """Wait for a failure to be mitigated."""
    logging.info("awaiting mitigation")
    time_remaining = timeout
    sleep_time = 10
    while time_remaining > 0 and not instance.mitigated():
        verify_steady_state()
        time.sleep(sleep_time)
        time_remaining -= sleep_time
    # Make sure the SUT has recovered (and not timed out)
    return instance.mitigated()

def await_next_failure(mttf: float, check_interval: float) -> None:
    """Pause until the next failure."""
    logging.info("pausing before next failure")
    ss_last_check = 0.0
    while random.random() > (1/mttf):
        if time.time() > ss_last_check + check_interval:
            verify_steady_state()
            ss_last_check = time.time()
        time.sleep(1)

def main() -> None:
    """Inject randomized faults."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--additional-failure",
                        default=0.25,
                        type=float,
                        help="Probability of having an additional simultaneous failure [0,1).")
    parser.add_argument("--check-interval",
                        default=30,
                        type=float,
                        help="Steady-state check interval (sec)")
    parser.add_argument("--cephcluster-name",
                        default="openshift-storage-cephcluster",
                        type=str,
                        help="Name of the cephcluster object")
    parser.add_argument("-l", "--log-dir",
                        default=os.getcwd(),
                        type=str,
                        help="Path to use for log files")
    parser.add_argument("--mitigation-timeout",
                        default=15 * 60,
                        type=float,
                        help="Failure mitigation timeout (sec).")
    parser.add_argument("--mttf",
                        default=150,
                        type=float,
                        help="Mean time to failure (sec).")
    parser.add_argument("--ocs-namespace",
                        default="openshift-storage",
                        type=str,
                        help="Namespace where the OCS components are running")
    cli_args = parser.parse_args()

    assert (cli_args.additional_failure >= 0 and cli_args.additional_failure < 1), \
           "Additional failure probability must be in the range [0,1)"
    assert cli_args.mttf > 0, "mttf must be greater than 0"
    assert cli_args.mitigation_timeout > 0, "mitigation timeout must be greater than 0"
    assert cli_args.check_interval > 0, "steady-state check interval must be greater than 0"

    log_dir = os.path.join(cli_args.log_dir, f'ocs-monkey-chaos-{RUN_ID}')
    util.setup_logging(log_dir)

    logging.info("starting execution-- run id: %d", RUN_ID)
    logging.info("program arguments: %s", cli_args)
    logging.info("log directory: %s", log_dir)

    cephcluster = failure_ocs.CephCluster(cli_args.ocs_namespace,
                                          cli_args.cephcluster_name)

    # Assemble list of potential FailureTypes to induce
    failure_types: List[failure.FailureType] = [
        # CSI driver component pods
        failure_ocs.DeletePodType(namespace=cli_args.ocs_namespace,
                                  labels={"app": "csi-rbdplugin"},
                                  cluster=cephcluster),
        failure_ocs.DeletePodType(namespace=cli_args.ocs_namespace,
                                  labels={"app": "csi-rbdplugin-provisioner"},
                                  cluster=cephcluster),
        # ceph component pods
        failure_ocs.DeletePodType(namespace=cli_args.ocs_namespace,
                                  labels={"app": "rook-ceph-mon"},
                                  cluster=cephcluster),
        failure_ocs.DeletePodType(namespace=cli_args.ocs_namespace,
                                  labels={"app": "rook-ceph-osd"},
                                  cluster=cephcluster),
        # operator component pods
        failure_ocs.DeletePodType(namespace=cli_args.ocs_namespace,
                                  labels={"app": "rook-ceph-operator"},
                                  cluster=cephcluster),
        failure_ocs.DeletePodType(namespace=cli_args.ocs_namespace,
                                  labels={"name": "ocs-operator"},
                                  cluster=cephcluster),
    ]

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

        if random.random() > cli_args.additional_failure or not fail_instance:
            # don't cause more simultaneous failures
            if fail_instance:
                # This shouldn't be an assert... but what should we do?
                assert await_mitigation(fail_instance, cli_args.mitigation_timeout)

            verify_steady_state()

            # Repair the infrastructure from all the failures, starting w/ most
            # recent and working back.
            logging.info("making repairs")
            pending_repairs.reverse()
            for repair in pending_repairs:
                repair.repair()
            pending_repairs.clear()

            verify_steady_state()

            # After all repairs have been made, ceph should become healthy
            logging.info("waiting for ceph cluster to be healthy")
            assert cephcluster.is_healthy(cli_args.mitigation_timeout)

            # Wait until it's time for next failure, monitoring steady-state
            # periodically
            await_next_failure(cli_args.mttf, cli_args.check_interval)

if __name__ == '__main__':
    main()
