#! /usr/bin/env python3
"""Measure the time required to start a pod that uses a PV."""

import kubernetes.client as k8s
import pytest
from util import handle_api, start_and_waitfor_pod


@pytest.mark.benchmark(min_rounds=10)
def test_attach_time(benchmark, unique_namespace, storageclass_iterator):
    """Benchmark the time required to start a pod w/ an attached PVC."""
    core_v1 = k8s.CoreV1Api()

    namespace = unique_namespace

    pvc = handle_api(core_v1.create_namespaced_persistent_volume_claim,
                     namespace=namespace["metadata"]["name"],
                     body={
                         "metadata": {
                             "name": "mypvc",
                             "namespace": namespace["metadata"]["name"]
                         },
                         "spec": {
                             "accessModes": ["ReadWriteOnce"],
                             "resources": {
                                 "requests": {
                                     "storage": "1Gi"
                                 }
                             },
                             "storageClassName": storageclass_iterator
                         }
                     })

    def start_and_delete(pod_dict):
        out_pod = start_and_waitfor_pod(pod_dict)
        handle_api(core_v1.delete_namespaced_pod,
                   namespace=out_pod.metadata.namespace,
                   name=out_pod.metadata.name,
                   body=k8s.V1DeleteOptions())

    pod = {
        "metadata": {
            "name": "mypod",
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
    benchmark(start_and_delete, pod)

    handle_api(core_v1.delete_namespaced_persistent_volume_claim,
               namespace=pvc.metadata.namespace,
               name=pvc.metadata.name,
               body=k8s.V1DeleteOptions())


if __name__ == '__main__':
    pytest.main([__file__])
