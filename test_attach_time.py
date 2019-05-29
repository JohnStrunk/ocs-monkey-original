#! /usr/bin/env python3
"""Measure the time required to start a pod that uses a PV."""

import time

import kubernetes
import kubernetes.client as k8s
from kubernetes.client.rest import ApiException
import pytest


@pytest.fixture(scope="module")
def fixture_kubeconfig():
    """Load the kube configuration so we can contact the cluster."""
    kubernetes.config.load_kube_config()


@pytest.fixture
def fixture_namespace(request, fixture_kubeconfig):
    """
    Create a namespace in which to run a test.

    This will create a namespace with a random name and automatically delete it
    at the end of the test.

    Returns:
        V1Namespace object describing the namespace that has been created for
        this test.

    """
    core_v1 = k8s.CoreV1Api()
    ns_name = f"ns-{time.perf_counter_ns()}"
    namespace = handle_api(core_v1.create_namespace,
                           body={
                               "metadata": {
                                   "name": ns_name
                               }
                           })

    def teardown():
        handle_api(core_v1.delete_namespace,
                   name=namespace.metadata.name,
                   body=k8s.V1DeleteOptions())
    request.addfinalizer(teardown)
    return namespace


def handle_api(func, *args, **kwargs):
    """
    Call kubernetes.client APIs and handle Execptions.

    Params:
        func:  The API function
        codes: A dict of how to respond to exeception codes
        (other args are passed to func)

    Returns:
        The return value from calling func

    """
    fkwargs = kwargs.copy()
    codes = kwargs.get("codes")
    if codes is None:
        codes = {500: "retry"}
    else:
        del fkwargs["codes"]
    while True:
        try:
            result = func(*args, **fkwargs)
            break
        except ApiException as ex:
            action = codes.get(ex.status)
            if action == "ignore":
                return result
            if action == "retry":
                time.sleep(1)
                continue
            raise
    return result


def start_and_waitfor_pod(pod_dict):
    """
    Create a pod and wait for it to be Running.

    Params:
        pod_dict: A dict describing the pod to create

    Returns:
        A V1Pod that has achieved the "Running" status.phase

    """
    core_v1 = k8s.CoreV1Api()
    pod = handle_api(core_v1.create_namespaced_pod,
                     namespace=pod_dict["metadata"]["namespace"],
                     body=pod_dict)

    watch = kubernetes.watch.Watch()
    for event in watch.stream(
            func=core_v1.list_namespaced_pod,
            namespace=pod.metadata.namespace,
            field_selector=f"metadata.name={pod.metadata.name}"):
        if event["object"].status.phase == "Running":
            watch.stop()
    return pod


def test_can_create_namespace(fixture_kubeconfig):
    """Test whether we can create a namespace."""
    core_v1 = k8s.CoreV1Api()
    ns_name = "my-namespace"
    namespace = handle_api(core_v1.create_namespace,
                           body={
                               "metadata": {
                                   "name": ns_name
                               }
                           })
    assert namespace.metadata.name == ns_name

    handle_api(core_v1.delete_namespace,
               name=namespace.metadata.name,
               body=k8s.V1DeleteOptions())


def test_attach_times(benchmark, fixture_namespace):
    """Benchmark the time required to start a pod w/ an attached PVC."""
    core_v1 = k8s.CoreV1Api()

    namespace = fixture_namespace

    pvc = handle_api(core_v1.create_namespaced_persistent_volume_claim,
                     namespace=namespace.metadata.name,
                     body={
                         "metadata": {
                             "name": "mypvc",
                             "namespace": namespace.metadata.name
                         },
                         "spec": {
                             "accessModes": ["ReadWriteOnce"],
                             "resources": {
                                 "requests": {
                                     "storage": "1Gi"
                                 }
                             },
                             "storageClassName": "csi-rbd"
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
            "namespace": namespace.metadata.name
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
