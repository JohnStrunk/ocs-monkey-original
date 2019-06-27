#!/usr/bin/env python3

import logging

import event
import osio
import kube

logging.basicConfig(level=logging.INFO)

def main():
    ns_name = "monkey"
    kube.create_namespace(ns_name)

    d = event.Dispatcher()
    # d.add(event.Periodic(interval=2, action=hello))
    # d.add(event.OneShot(when=time.time()+7, action=bam))
    # d.add(event.Periodic(interval=1, action=the_beat))
    d.add(osio.ExponentialDeployment(interarrival=10,
                                     lifetime=150,
                                     active=12,
                                     idle=20))
    d.run()

if __name__ == '__main__':
    main()
