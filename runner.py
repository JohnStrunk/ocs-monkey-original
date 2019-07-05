#!/usr/bin/env python3
"""Starts the randomized workload generator."""

import logging

import event
import osio
import kube

def main() -> None:
    """Run the workload."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s - %(levelname)s - %(message)s")
    ns_name = "monkey"
    sc_name = "rbd-csi"
    access_mode = "ReadWriteOnce"
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
