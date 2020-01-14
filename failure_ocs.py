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

#   status:
#     ceph:
#       details:
#         OSD_NEARFULL:
#           message: 1 nearfull osd(s)
#           severity: HEALTH_WARN
#         PG_BACKFILL_FULL:
#           message: 'Low space hindering backfill (add storage if this doesn''t resolve
#             itself): 1 pg backfill_toofull'
#           severity: HEALTH_WARN
#         POOL_NEARFULL:
#           message: 3 pool(s) nearfull
#           severity: HEALTH_WARN
#       health: HEALTH_WARN
#       lastChanged: "2019-12-04T19:29:27Z"
#       lastChecked: "2019-12-04T20:20:04Z"
#       previousHealth: HEALTH_OK
#     state: Created

class CephCluster:
    """Methods for interacting with the CephCluster object."""
    def __init__(self, namespace: str, name: str):
        self._ns = namespace
        self._name = name

    def _get_cephcluster(self) -> kube.MANIFEST:
        crd = k8s.CustomObjectsApi()
        return kube.call(crd.get_namespaced_custom_object,
                         group="ceph.rook.io",
                         version="v1",
                         plural="cephclusters",
                         namespace=self._ns,
                         name=self._name)

    def _is_healthy(self) -> bool:
        ceph = self._get_cephcluster()
        if ceph.get("status") is None:
            return False
        if ceph["status"].get("ceph") is None:
            return False
        healthy: bool = ceph["status"]["ceph"]["health"] == "HEALTH_OK"
        return healthy

    def is_healthy(self, timeout_seconds: float = 0) -> bool:
        """Wait until the Ceph cluster is healthy."""
        is_healthy = self._is_healthy()
        deadline = time.time() + timeout_seconds
        while not is_healthy and deadline > time.time():
            time.sleep(1)
            is_healthy = self.is_healthy()
        return is_healthy

    def problems(self) -> Dict[str, Dict[str, str]]:
        """
        Get the current list of problems w/ the ceph cluster.

        The cephcluster's .status.ceph.details (when it exists) describes the
        set of problems with the cluster. This function returns the list of
        current problems from that portion of the tree.

        Example:
            status:
              ceph:
                details:
                  OSD_NEARFULL:
                    message: 1 nearfull osd(s)
                    severity: HEALTH_WARN
                  PG_BACKFILL_FULL:
                    message: 'Low space hindering backfill (add storage if
                        this doesn''t resolve itself): 1 pg backfill_toofull'
                    severity: HEALTH_WARN
                  POOL_NEARFULL:
                    message: 3 pool(s) nearfull
                    severity: HEALTH_WARN
                health: HEALTH_WARN

        p = cluster.problems()
        p.keys() -> ["OSD_NEARFULL", "PG_BACKFILL_FULL", "POOL_NEARFULL"]
        p["OSD_NEARFULL"]["severity"] -> "HEALTH_WARN"
        """
        ceph = self._get_cephcluster()
        if ceph.get("status") is None:
            return {}
        if ceph["status"].get("ceph") is None:
            return {}
        if ceph["status"]["ceph"].get("details") is None:
            return {}
        problems: Dict[str, Dict[str, str]] = ceph["status"]["ceph"]["health"]
        return problems


class DeletePod(Failure):
    """A Failure that deletes a specific pod."""
    def __init__(self, deployment: kube.MANIFEST, pod: kube.MANIFEST):
        self._namespace = pod["metadata"]["namespace"]
        self._name = pod["metadata"]["name"]
        self._deployment = deployment["metadata"]["name"]

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

        # We consider the failure to be mitigated when the deployment is fully
        # ready.
        mitigated = False
        apps_v1 = k8s.AppsV1Api()
        watch = kubernetes.watch.Watch()
        for event in watch.stream(
                func=apps_v1.list_namespaced_deployment,
                namespace=self._namespace,
                field_selector=f"metadata.name={self._deployment}",
                *timeout):
            if event["object"].status.ready_replicas == event["object"].spec.replicas:
                mitigated = True
                watch.stop()

        return mitigated

    def __str__(self) -> str:
        return f'F(delete pod: {self._namespace}/{self._name} in deployment: {self._deployment})'


class DeletePodType(FailureType):
    """Deletes pods from a Deployment matching a label selector."""
    def __init__(self, namespace: str, labels: Dict[str, str], cluster: CephCluster):
        self._labels = labels
        self._namespace = namespace
        self._cluster = cluster

    def get(self) -> Failure:
        # This is overly restrictive. We should be looking at
        # self._cluster.problems() and taking into account the type of failure.
        if not self._cluster.is_healthy():
            raise NoSafeFailures("ceph cluster is not healthy")

        selector = ','.join([f'{key}={val}' for (key, val) in
                             self._labels.items()])
        apps_v1 = k8s.AppsV1Api()
        deployments = kube.call(apps_v1.list_namespaced_deployment,
                                namespace=self._namespace,
                                label_selector=selector)
        if not deployments["items"]:
            raise NoSafeFailures(f'No deployments matched selector: {selector}')

        # If any of the selected Deployments are degraded, stop. This is because
        # each component has separate Deployments per replica. E.g., MONs are 3
        # separate deployments.
        for deployment in deployments["items"]:
            if deployment["spec"]["replicas"] != deployment["status"].get("ready_replicas"):
                raise NoSafeFailures('No pods are safe to kill')

        random.shuffle(deployments["items"])
        deployment = deployments["items"][0]
        pod_selector = ','.join([f'{key}={val}' for (key, val) in
                                 deployment["spec"]["selector"]["match_labels"].items()])

        core_v1 = k8s.CoreV1Api()
        pods = kube.call(core_v1.list_namespaced_pod,
                         namespace=self._namespace,
                         label_selector=pod_selector)
        if not pods["items"]:
            raise NoSafeFailures(f'No pods maatched selector: {pod_selector}')

        random.shuffle(pods["items"])
        return DeletePod(deployment, pods["items"][0])

    def __str__(self) -> str:
        return f'FT(delete pod: ns:{self._namespace} selector:{self._labels})'
