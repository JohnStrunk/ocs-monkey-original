#! /usr/bin/env python3
"""Measure the time to provision a new PV and start an associated pod."""

import random

import kubernetes.client as k8s
import pytest
from util import handle_api, start_and_waitfor_pod


def _provision_start_delete(namespace, sc_name):
    core_v1 = k8s.CoreV1Api()
    pvc_name = f"pvc-{random.randrange(999999999)}"
    pod_name = f"pod-{random.randrange(999999999)}"
    pvc = handle_api(core_v1.create_namespaced_persistent_volume_claim,
                     namespace=namespace["metadata"]["name"],
                     body={
                         "metadata": {
                             "name": pvc_name,
                             "namespace": namespace["metadata"]["name"]
                         },
                         "spec": {
                             "accessModes": ["ReadWriteOnce"],
                             "resources": {
                                 "requests": {
                                     "storage": "1Gi"
                                 }
                             },
                             "storageClassName": sc_name
                         }
                     })

    pod_dict = {
        "metadata": {
            "name": pod_name,
            "namespace": namespace["metadata"]["name"]
        },
        "spec": {
            "containers": [{
                "name": "busybox",
                "image": "busybox",
                "command": ["sleep", "99999"],
                "volumeMounts": [{
                    "name": "data",
                    "mountPath": "/mnt"
                }]
            }],
            "terminationGracePeriodSeconds": 0,
            "volumes": [{
                "name": "data",
                "persistentVolumeClaim": {
                    "claimName": pvc.metadata.name
                }
            }]
        }
    }
    pod = start_and_waitfor_pod(pod_dict)
    handle_api(core_v1.delete_namespaced_pod,
               namespace=pod.metadata.namespace,
               name=pod.metadata.name,
               body=k8s.V1DeleteOptions())
    handle_api(core_v1.delete_namespaced_persistent_volume_claim,
               namespace=pvc.metadata.namespace,
               name=pvc.metadata.name,
               body=k8s.V1DeleteOptions())


@pytest.mark.benchmark(min_rounds=10)
def test_provision_attach_time(benchmark,
                               unique_namespace,
                               storageclass_iterator):
    """Benchmark the time provision a PV and start a pod that uses it."""
    benchmark(_provision_start_delete, unique_namespace, storageclass_iterator)


if __name__ == '__main__':
    pytest.main([__file__])
