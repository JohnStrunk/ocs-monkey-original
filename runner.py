#!/usr/bin/env python3
"""Run the randomized workload."""


import logging

import event
import osio
import kube

def main() -> None:
    """Run the workload."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s - %(levelname)s - %(message)s")
    ns_name = "monkey"
    kube.create_namespace(ns_name)

    dispatcher = event.Dispatcher()
    dispatcher.add(osio.start(interarrival=10,
                              lifetime=300,
                              active=60,
                              idle=30))
    dispatcher.run()

if __name__ == '__main__':
    main()
