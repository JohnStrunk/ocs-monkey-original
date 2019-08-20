#!/usr/bin/env python3
"""Starts the randomized workload generator."""

import argparse
import logging
import os
import subprocess
import random
import time

import event
import log_gather
import osio
import kube

CLI_ARGS: argparse.Namespace
RUN_ID = random.randrange(999999999)

# pylint: disable=too-few-public-methods
class MustGather(log_gather.Collector):
    """Log collector that runs must-gather."""

    def __init__(self) -> None:
        """Create a log-collector using must-gather."""
        super().__init__("must-gather")
    def gather(self, path: str) -> bool:
        """Run must-gather and notify of success."""
        mg_dir = os.path.join(path, 'must-gather')
        completed = subprocess.run(f'{CLI_ARGS.oc} adm must-gather'
                                   f' --dest-dir {mg_dir}', shell=True)
        return completed.returncode == 0

class OcsMustGather(log_gather.Collector):
    """Log collector that runs ocs-must-gather."""

    def __init__(self) -> None:
        """Create a log-collector using ocs-must-gather."""
        super().__init__("OCS must-gather")
    def gather(self, path: str) -> bool:
        """Run must-gather and notify of success."""
        mg_dir = os.path.join(path, 'ocs-must-gather')
        completed = subprocess.run(f'{CLI_ARGS.oc} adm must-gather'
                                   f' --image=quay.io/ocs-dev/ocs-must-gather'
                                   f' --dest-dir {mg_dir}', shell=True)
        return completed.returncode == 0

class OcsImageVersions(log_gather.Collector):
    """Grab the images & tags from the OCS namespace."""

    def __init__(self, ocs_namespace: str) -> None:
        """Create a log-collector that scrapes images tags."""
        self._ns = ocs_namespace
        super().__init__("OCS image versions")
    def gather(self, path: str) -> bool:
        """Scrape the names of the pod images."""
        completed = subprocess.run(f'{CLI_ARGS.oc} -n {self._ns} get po -oyaml'
                                   ' | grep -E "(image:|imageID:)" | sort -u '
                                   f'> {path}/ocs_images.log', shell=True)
        return completed.returncode == 0

def main() -> None:
    """Run the workload."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--log-dir",
                        default=os.getcwd(),
                        type=str,
                        help="Path to use for log files")
    parser.add_argument("-m", "--accessmode",
                        default="ReadWriteOnce",
                        type=str, choices=["ReadWriteOnce", "ReadWriteMany"],
                        help="StorageClassName for the workload's PVCs")
    parser.add_argument("-n", "--namespace",
                        default="ocs-monkey",
                        type=str,
                        help="Namespace to use for the workload")
    parser.add_argument("--oc",
                        default="oc",
                        type=str,
                        help="Path/executable for the oc command")
    parser.add_argument("--ocs-namespace",
                        default="rook-ceph",
                        type=str,
                        help="Namespace where the OCS components are running")
    parser.add_argument("-s", "--storageclass",
                        default="csi-rbd",
                        type=str,
                        help="StorageClassName for the workload's PVCs")
    parser.add_argument("-z", "--sleep-on-error",
                        action="store_true",
                        help="On error, sleep forever instead of exit")
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
    formatter = \
        logging.Formatter("%(asctime)s %(name)s - %(levelname)s - %(message)s")
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logging.info("starting execution-- run id: %d", RUN_ID)
    logging.info("program arguments: %s", CLI_ARGS)
    logging.info("log directory: %s", log_dir)

    # register log collector(s)
    log_gather.add(OcsMustGather())
    log_gather.add(MustGather())
    log_gather.add(OcsImageVersions(CLI_ARGS.ocs_namespace))

    kube.create_namespace(CLI_ARGS.namespace, existing_ok=True)

    dispatch = event.Dispatcher()
    dispatch.add(*osio.resume(CLI_ARGS.namespace))
    dispatch.add(osio.start(namespace=CLI_ARGS.namespace,
                            storage_class=CLI_ARGS.storageclass,
                            access_mode=CLI_ARGS.accessmode,
                            interarrival=10,
                            lifetime=300,
                            active=60,
                            idle=30))
    try:
        dispatch.run()
    except osio.UnhealthyDeployment:
        logging.info("starting log collection")
        log_gather.gather(log_dir)
        logging.info("Controller stopped due to detected error")
        while CLI_ARGS.sleep_on_error:
            time.sleep(9999)

if __name__ == '__main__':
    main()
