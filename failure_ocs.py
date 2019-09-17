"""
Failure types for OCS.
"""
import random
import time
from typing import Dict

import kubernetes
import kubernetes.client as k8s

from failure import Failure, FailureType, NoSafeFailures
import kube

def ceph_is_healthy(namespace: str) -> bool:
    crd = k8s.CustomObjectsApi()
    cephcluster = kube.call(crd.get_namespaced_custom_object,
                            group="ceph.rook.io",
                            version="v1",
                            plural="cephclusters",
                            namespace=namespace,
                            name=namespace)
    is_healthy: bool = cephcluster["status"]["ceph"]["health"] == "HEALTH_OK"
    return is_healthy

def await_ceph_healthy(namespace: str, timeout_seconds: float) -> bool:
    crd = k8s.CustomObjectsApi()
    is_healthy = False
    deadline = time.time() + timeout_seconds
    while not is_healthy and deadline > time.time():
        is_healthy = ceph_is_healthy(namespace)
    return is_healthy

class DeletePod(Failure):
    def __init__(self, pod: kube.MANIFEST):
        self._namespace = pod["metadata"]["namespace"]
        self._name = pod["metadata"]["name"]

    def invoke(self) -> None:
        core_v1 = k8s.CoreV1Api()
        kube.call(core_v1.delete_namespaced_pod,
                  namespace=self._namespace,
                  name=self._name,
                  grace_period_seconds=0,
                  body=k8s.V1DeleteOptions())

    def mitigated(self, timeout_seconds: float = 0) -> bool:
        timeout: Dict[str, float] = {}
        if timeout_seconds:
            timeout = {"timeout_seconds": timeout_seconds}

        # We consider the failure to be mitigated when the killed pod is
        # recreated and enters the running state.
        # BUG: This is broken. The pod will come back w/ a different name, and Running is true even when pod is being deleted!
        core_v1 = k8s.CoreV1Api()
        watch = kubernetes.watch.Watch()
        for event in watch.stream(
                func=core_v1.list_namespaced_pod,
                namespace=self._namespace,
                field_selector=f"metadata.name={self._name}",
                *timeout):
            if event["object"].status.phase == "Running":
                watch.stop()

        return True

    def __str__(self) -> str:
        return f'F(delete pod: {self._namespace}/{self._name})'


class DeletePodType(FailureType):
    def __init__(self, namespace: str, labels: Dict[str, str]):
        self._labels = labels
        self._namespace = namespace

    def get(self) -> Failure:
        selector = ','.join([f'{key}={val}' for (key, val) in self._labels.items()])
        core_v1 = k8s.CoreV1Api()
        pods = kube.call(core_v1.list_namespaced_pod,
                         namespace=self._namespace,
                         label_selector=selector)
        if not pods["items"]:
            raise NoSafeFailures(f'No pods matched: {selector}')

        random.shuffle(pods["items"])
        for pod in pods["items"]:
            failure = DeletePod(pod)
            # Only return failures that are survivable
            if len(pods["items"]) >= 3 and ceph_is_healthy(self._namespace):
                return failure
        raise NoSafeFailures(f'No pods are safe to kill')

    def __str__(self) -> str:
        return f'FT(delete pod: ns:{self._namespace} selector:{self._labels})'
