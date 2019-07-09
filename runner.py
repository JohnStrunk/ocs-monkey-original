#!/usr/bin/env python3
"""Starts the randomized workload generator."""

import argparse
import logging

import event
import osio
import kube

def main() -> None:
    """Run the workload."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--namespace",
                        default="ocs-monkey",
                        type=str,
                        help="Namespace to use for the workload")
    parser.add_argument("-s", "--storageclass",
                        default="rbd-csi",
                        type=str,
                        help="StorageClassName for the workload's PVCs")
    parser.add_argument("-m", "--accessmode",
                        default="ReadWriteOnce",
                        type=str, choices=["ReadWriteOnce", "ReadWriteMany"],
                        help="StorageClassName for the workload's PVCs")
    args = parser.parse_args()

    ns_name = args.namespace
    sc_name = args.storageclass
    access_mode = args.accessmode

    kube.create_namespace(ns_name, existing_ok=True)

    dispatch = event.Dispatcher()
    dispatch.add(osio.start(namespace=ns_name,
                            storage_class=sc_name,
                            access_mode=access_mode,
                            interarrival=10,
                            lifetime=300,
                            active=60,
                            idle=30))
    dispatch.run()

if __name__ == '__main__':
    main()
