#!/usr/bin/env python3

import logging

import event
import osio
import kube

def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s - %(levelname)s - %(message)s")
    ns_name = "monkey"
    kube.create_namespace(ns_name)

    d = event.Dispatcher()
    d.add(osio.start(interarrival=10,
                     lifetime=300,
                     active=60,
                     idle=30))
    d.run()

if __name__ == '__main__':
    main()
